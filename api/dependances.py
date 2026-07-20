# api/dependances.py
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from core.securite import decoder_jeton_acces
from db.database import get_db
from models import Utilisateur
from services.tmdb_client import ClientTMDB

schema_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/connexion")


def client_tmdb(request: Request) -> ClientTMDB:
    """Client TMDB partagé, créé au démarrage de l'app (voir lifespan dans main.py)."""
    return request.app.state.tmdb


def utilisateur_courant(
    jeton: str = Depends(schema_oauth2), db: Session = Depends(get_db)
) -> Utilisateur:
    """Résout le jeton Bearer en utilisateur ; 401 sinon."""
    id_utilisateur = decoder_jeton_acces(jeton)
    if id_utilisateur is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Jeton invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"})
    utilisateur = db.get(Utilisateur, id_utilisateur)
    if utilisateur is None or utilisateur.statut_compte != "actif":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Compte introuvable ou inactif",
            headers={"WWW-Authenticate": "Bearer"})
    return utilisateur
