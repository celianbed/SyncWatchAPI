# api/core/securite.py
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from api.core.config import settings


def hacher_mot_de_passe(mot_de_passe: str) -> str:
    return bcrypt.hashpw(mot_de_passe.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verifier_mot_de_passe(mot_de_passe: str, hash_stocke: str) -> bool:
    return bcrypt.checkpw(mot_de_passe.encode("utf-8"), hash_stocke.encode("utf-8"))


def creer_jeton_acces(id_utilisateur: int) -> str:
    expiration = datetime.now(timezone.utc) + timedelta(minutes=settings.DUREE_JETON_MINUTES)
    # "sub" doit être une chaîne (spec JWT)
    charge = {"sub": str(id_utilisateur), "exp": expiration}
    return jwt.encode(charge, settings.SECRET_KEY, algorithm=settings.ALGORITHME_JWT)


def decoder_jeton_acces(jeton: str) -> int | None:
    """Renvoie l'id utilisateur porté par le jeton, ou None s'il est invalide/expiré."""
    try:
        charge = jwt.decode(jeton, settings.SECRET_KEY, algorithms=[settings.ALGORITHME_JWT])
        return int(charge["sub"])
    except (JWTError, KeyError, ValueError):
        return None
