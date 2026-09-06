# api/avis.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.communs import du_proprietaire_ou_404, get_ou_404
from api.dependances import utilisateur_courant
from db.database import get_db
from models import (Abonnement, Avis, Episode, Film, Saison, Serie,
                    Utilisateur, VisionnerEpisode)
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
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Les avis d'une cible — exactement un filtre parmi les trois."""
    nom, valeur = _cible_unique(id_serie, id_film, id_episode)
    return db.scalars(select(Avis).where(getattr(Avis, nom) == valeur)
                      .order_by(Avis.date_creation.desc())).all()


def _cible_unique(id_serie, id_film, id_episode) -> tuple[str, int]:
    """Valide qu'exactement un filtre de cible est fourni, et le renvoie."""
    actifs = {n: v for n, v in {"id_serie": id_serie, "id_film": id_film,
                                "id_episode": id_episode}.items() if v is not None}
    if len(actifs) != 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Un filtre exactement : id_serie, id_film ou id_episode.")
    return next(iter(actifs.items()))


# déclaré avant /{id_avis}, sinon "abonnements" serait capté comme un id
@router.get("/abonnements", response_model=list[AvisPublic])
def avis_de_mes_abonnements(
    id_serie: int | None = None,
    id_film: int | None = None,
    id_episode: int | None = None,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Avis d'une cible, limités aux personnes que l'utilisateur courant suit.

    Sur une série, le commentaire d'une personne plus avancée que vous est
    retiré : c'est le seul endroit d'où viennent les spoilers entre amis, et
    nous sommes les seuls à pouvoir le savoir, puisque nous suivons les
    épisodes un à un. La note reste visible — un chiffre ne divulgue rien.
    """
    nom, valeur = _cible_unique(id_serie, id_film, id_episode)
    suivis = select(Abonnement.id_suivi).where(
        Abonnement.id_suiveur == utilisateur.id_utilisateur)
    avis = db.scalars(
        select(Avis).where(getattr(Avis, nom) == valeur,
                           Avis.id_utilisateur.in_(suivis))
        .order_by(Avis.date_creation.desc())).all()

    if id_serie is None:
        # un film se voit d'un bloc, il n'y a pas de « plus avancé »
        return [AvisPublic.model_validate(a) for a in avis]

    return _masquer_les_plus_avances(db, utilisateur, id_serie, avis)


def _masquer_les_plus_avances(
    db: Session, utilisateur: Utilisateur, id_serie: int, avis: list[Avis]
) -> list[AvisPublic]:
    """Retire le commentaire des auteurs ayant vu plus d'épisodes que vous."""
    vus = dict(db.execute(
        select(VisionnerEpisode.id_utilisateur, func.count())
        .join(Episode, Episode.id_episode == VisionnerEpisode.id_episode)
        .join(Saison, Saison.id_saison == Episode.id_saison)
        .where(Saison.id_serie == id_serie)
        .group_by(VisionnerEpisode.id_utilisateur)).all())
    les_miens = vus.get(utilisateur.id_utilisateur, 0)

    resultat = []
    for a in avis:
        public = AvisPublic.model_validate(a)
        if a.commentaire and vus.get(a.id_utilisateur, 0) > les_miens:
            public.commentaire = None
            public.masque = True
        resultat.append(public)
    return resultat


# déclaré avant /{id_avis}, sinon "moi" serait capté comme un id
@router.get("/moi", response_model=list[AvisPublic])
def mes_avis(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    return db.scalars(select(Avis).where(Avis.id_utilisateur == utilisateur.id_utilisateur)
                      .order_by(Avis.date_creation.desc())).all()


@router.get("/{id_avis}", response_model=AvisPublic)
def lire_avis(
    id_avis: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Lecture réservée aux comptes connectés : sans jeton, les identifiants étant
    séquentiels, on pourrait aspirer tous les avis et les pseudos de leurs auteurs."""
    return get_ou_404(db, Avis, id_avis, "Avis introuvable.")


@router.patch("/{id_avis}", response_model=AvisPublic)
def modifier_avis(
    id_avis: int,
    donnees: AvisMaj,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    avis = du_proprietaire_ou_404(db, Avis, id_avis, utilisateur, "Avis introuvable.")
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
    avis = du_proprietaire_ou_404(db, Avis, id_avis, utilisateur, "Avis introuvable.")
    db.delete(avis)
    db.commit()
