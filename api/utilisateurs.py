# api/utilisateurs.py
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.dependances import envoyeur_mail, utilisateur_courant
from core.securite import creer_jeton_verification, hacher_mot_de_passe
from db.database import get_db
from models import (Film, Serie, SuivreFilm, SuivreSerie, Utilisateur,
                       VisionnerFilm)
from schemas.recherche import ResultatRecherche
from schemas.utilisateur import (UtilisateurCreation, UtilisateurMaj,
                                     UtilisateurPublic)
from services.email_service import Envoyeur, envoyer_mail_verification

router = APIRouter()


@router.post("", response_model=UtilisateurPublic, status_code=status.HTTP_201_CREATED)
def inscrire(
    donnees: UtilisateurCreation,
    taches: BackgroundTasks,
    db: Session = Depends(get_db),
    envoyeur: Envoyeur = Depends(envoyeur_mail),
):
    if db.scalar(select(Utilisateur).where(Utilisateur.adresse_mail == donnees.adresse_mail)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette adresse mail est déjà utilisée.")
    if db.scalar(select(Utilisateur).where(Utilisateur.pseudo == donnees.pseudo)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce pseudo est déjà pris.")

    utilisateur = Utilisateur(
        adresse_mail=donnees.adresse_mail,
        pseudo=donnees.pseudo,
        mot_de_passe=hacher_mot_de_passe(donnees.mot_de_passe),
    )
    db.add(utilisateur)
    db.commit()
    db.refresh(utilisateur)

    # compte créé non vérifié : on envoie le lien de confirmation hors du chemin critique
    jeton = creer_jeton_verification(utilisateur.id_utilisateur)
    taches.add_task(envoyer_mail_verification, envoyeur,
                    utilisateur.adresse_mail, utilisateur.pseudo, jeton)
    return utilisateur


# déclaré avant /{id_utilisateur}, sinon "moi" serait capté comme un id
@router.get("/moi", response_model=UtilisateurPublic)
def moi(utilisateur: Utilisateur = Depends(utilisateur_courant)):
    return utilisateur


@router.patch("/moi", response_model=UtilisateurPublic)
def modifier_moi(
    donnees: UtilisateurMaj,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Met à jour le profil (pseudo, avatar) — champs absents inchangés."""
    champs = donnees.model_dump(exclude_unset=True)
    if champs.get("pseudo") is None:
        champs.pop("pseudo", None)  # le pseudo est obligatoire : null ignoré
    nouveau_pseudo = champs.get("pseudo")
    if (nouveau_pseudo and nouveau_pseudo != utilisateur.pseudo
            and db.scalar(select(Utilisateur).where(Utilisateur.pseudo == nouveau_pseudo))):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce pseudo est déjà pris.")
    for champ, valeur in champs.items():
        setattr(utilisateur, champ, valeur)
    db.commit()
    db.refresh(utilisateur)
    return utilisateur


# déclarés avant /{id_utilisateur} (deux segments : pas de collision, mais on groupe le "moi")
@router.get("/moi/favoris", response_model=list[ResultatRecherche])
def mes_favoris(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Séries et films marqués favoris — carrousel du profil."""
    uid = utilisateur.id_utilisateur
    series = db.scalars(
        select(Serie).join(SuivreSerie, SuivreSerie.id_serie == Serie.id_serie)
        .where(SuivreSerie.id_utilisateur == uid, SuivreSerie.favori.is_(True))
        .order_by(SuivreSerie.date_ajout.desc())).all()
    films = db.scalars(
        select(Film).join(SuivreFilm, SuivreFilm.id_film == Film.id_film)
        .where(SuivreFilm.id_utilisateur == uid, SuivreFilm.favori.is_(True))).all()
    return ([ResultatRecherche.depuis_serie(s) for s in series]
            + [ResultatRecherche.depuis_film(f) for f in films])


@router.get("/moi/films-vus", response_model=list[ResultatRecherche])
def mes_films_vus(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Films vus récemment (distincts, dernier visionnage d'abord) — carrousel du profil."""
    uid = utilisateur.id_utilisateur
    dernier = (
        select(VisionnerFilm.id_film,
               func.max(VisionnerFilm.date_visionnage).label("dernier"))
        .where(VisionnerFilm.id_utilisateur == uid)
        .group_by(VisionnerFilm.id_film).subquery())
    films = db.scalars(
        select(Film).join(dernier, Film.id_film == dernier.c.id_film)
        .order_by(dernier.c.dernier.desc()).limit(20)).all()
    return [ResultatRecherche.depuis_film(f) for f in films]


@router.get("/{id_utilisateur}", response_model=UtilisateurPublic)
def lire(id_utilisateur: int, db: Session = Depends(get_db)):
    utilisateur = db.get(Utilisateur, id_utilisateur)
    if utilisateur is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable.")
    return utilisateur
