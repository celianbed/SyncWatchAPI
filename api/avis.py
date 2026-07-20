# api/avis.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.dependances import utilisateur_courant
from db.database import get_db
from models import Avis, Episode, Film, Serie, Utilisateur
from schemas.avis import AvisCreation, AvisMaj, AvisPublic

router = APIRouter()


def _verifier_cible(db: Session, donnees: AvisCreation) -> None:
    """La cible (interne, donc déjà en cache) doit exister."""
    cible = (
        (Serie, donnees.id_serie) if donnees.id_serie is not None
        else (Film, donnees.id_film) if donnees.id_film is not None
        else (Episode, donnees.id_episode)
    )
    if db.get(*cible) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cible de l'avis introuvable.")


def _avis_du_proprietaire(db: Session, id_avis: int, utilisateur: Utilisateur) -> Avis:
    avis = db.get(Avis, id_avis)
    if avis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Avis introuvable.")
    if avis.id_utilisateur != utilisateur.id_utilisateur:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cet avis ne vous appartient pas.")
    return avis


@router.post("", response_model=AvisPublic, status_code=status.HTTP_201_CREATED)
def creer_avis(
    donnees: AvisCreation,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    _verifier_cible(db, donnees)
    avis = Avis(id_utilisateur=utilisateur.id_utilisateur, **donnees.model_dump())
    db.add(avis)
    db.commit()
    db.refresh(avis)
    return avis


@router.get("", response_model=list[AvisPublic])
def lister_avis(
    id_serie: int | None = None,
    id_film: int | None = None,
    id_episode: int | None = None,
    db: Session = Depends(get_db),
):
    """Les avis d'une cible — exactement un filtre parmi les trois."""
    filtres = {"id_serie": id_serie, "id_film": id_film, "id_episode": id_episode}
    actifs = {nom: valeur for nom, valeur in filtres.items() if valeur is not None}
    if len(actifs) != 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Un filtre exactement : id_serie, id_film ou id_episode.")
    nom, valeur = next(iter(actifs.items()))
    return db.scalars(select(Avis).where(getattr(Avis, nom) == valeur)
                      .order_by(Avis.date_creation.desc())).all()


# déclaré avant /{id_avis}, sinon "moi" serait capté comme un id
@router.get("/moi", response_model=list[AvisPublic])
def mes_avis(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    return db.scalars(select(Avis).where(Avis.id_utilisateur == utilisateur.id_utilisateur)
                      .order_by(Avis.date_creation.desc())).all()


@router.get("/{id_avis}", response_model=AvisPublic)
def lire_avis(id_avis: int, db: Session = Depends(get_db)):
    avis = db.get(Avis, id_avis)
    if avis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Avis introuvable.")
    return avis


@router.patch("/{id_avis}", response_model=AvisPublic)
def modifier_avis(
    id_avis: int,
    donnees: AvisMaj,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    avis = _avis_du_proprietaire(db, id_avis, utilisateur)
    for champ in donnees.model_fields_set:  # null explicite = effacer le champ
        setattr(avis, champ, getattr(donnees, champ))
    if avis.note is None and not (avis.commentaire or "").strip():
        db.rollback()  # ne pas laisser la mutation en suspens dans la session
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "L'avis doit garder une note ou un commentaire.")
    db.commit()
    db.refresh(avis)
    return avis


@router.delete("/{id_avis}", status_code=status.HTTP_204_NO_CONTENT)
def supprimer_avis(
    id_avis: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    avis = _avis_du_proprietaire(db, id_avis, utilisateur)
    db.delete(avis)
    db.commit()
