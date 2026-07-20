# api/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.securite import creer_jeton_acces, verifier_mot_de_passe
from db.database import get_db
from models import Utilisateur
from schemas.jeton import Jeton

router = APIRouter()


@router.post("/connexion", response_model=Jeton)
def connexion(
    identifiants: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """Connexion par adresse mail ou pseudo (champ `username` de la spec OAuth2)."""
    utilisateur = db.scalar(select(Utilisateur).where(
        (Utilisateur.adresse_mail == identifiants.username)
        | (Utilisateur.pseudo == identifiants.username)))
    if utilisateur is None or not verifier_mot_de_passe(
            identifiants.password, utilisateur.mot_de_passe):
        # message unique : ne pas révéler si le compte existe
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Identifiants incorrects",
            headers={"WWW-Authenticate": "Bearer"})
    if utilisateur.statut_compte != "actif":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Compte suspendu ou supprimé")

    utilisateur.date_derniere_connexion = func.now()
    db.commit()
    return Jeton(access_token=creer_jeton_acces(utilisateur.id_utilisateur))
