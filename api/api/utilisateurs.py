# api/api/utilisateurs.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.api.dependances import utilisateur_courant
from api.core.securite import hacher_mot_de_passe
from api.db.database import get_db
from api.models import Utilisateur
from api.schemas.utilisateur import (UtilisateurCreation, UtilisateurMaj,
                                     UtilisateurPublic)

router = APIRouter()


@router.post("", response_model=UtilisateurPublic, status_code=status.HTTP_201_CREATED)
def inscrire(donnees: UtilisateurCreation, db: Session = Depends(get_db)):
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


@router.get("/{id_utilisateur}", response_model=UtilisateurPublic)
def lire(id_utilisateur: int, db: Session = Depends(get_db)):
    utilisateur = db.get(Utilisateur, id_utilisateur)
    if utilisateur is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable.")
    return utilisateur
