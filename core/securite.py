# core/securite.py
import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from core.config import settings


def hacher_mot_de_passe(mot_de_passe: str) -> str:
    return bcrypt.hashpw(mot_de_passe.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verifier_mot_de_passe(mot_de_passe: str, hash_stocke: str | None) -> bool:
    # hash None = compte sans mot de passe (créé via Google) : la connexion par
    # mot de passe échoue toujours pour ces comptes.
    if not hash_stocke:
        return False
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
        # un jeton de vérification (type dédié) ne doit pas servir de jeton d'accès
        if charge.get("type") not in (None, "access"):
            return None
        return int(charge["sub"])
    except (JWTError, KeyError, ValueError):
        return None


def creer_jeton_verification(id_utilisateur: int) -> str:
    """Jeton à usage unique porté par le lien de confirmation d'adresse mail."""
    expiration = datetime.now(timezone.utc) + timedelta(hours=settings.DUREE_JETON_VERIF_HEURES)
    charge = {"sub": str(id_utilisateur), "exp": expiration, "type": "verification"}
    return jwt.encode(charge, settings.SECRET_KEY, algorithm=settings.ALGORITHME_JWT)


def decoder_jeton_verification(jeton: str) -> int | None:
    """Renvoie l'id à vérifier porté par le jeton, ou None s'il est invalide/expiré/du mauvais type."""
    try:
        charge = jwt.decode(jeton, settings.SECRET_KEY, algorithms=[settings.ALGORITHME_JWT])
        if charge.get("type") != "verification":
            return None
        return int(charge["sub"])
    except (JWTError, KeyError, ValueError):
        return None


def empreinte_mot_de_passe(hash_mdp: str) -> str:
    """Empreinte courte du hash courant. Insérée dans le jeton de reset : dès que le
    mot de passe change, l'empreinte change → le jeton devient invalide (usage unique)."""
    return hashlib.sha256(hash_mdp.encode("utf-8")).hexdigest()[:16]


def creer_jeton_reset(id_utilisateur: int, hash_mdp: str) -> str:
    """Jeton porté par le lien « mot de passe oublié » : court et à usage unique."""
    expiration = datetime.now(timezone.utc) + timedelta(minutes=settings.DUREE_JETON_RESET_MINUTES)
    charge = {"sub": str(id_utilisateur), "exp": expiration,
              "type": "reset", "emp": empreinte_mot_de_passe(hash_mdp)}
    return jwt.encode(charge, settings.SECRET_KEY, algorithm=settings.ALGORITHME_JWT)


def decoder_jeton_reset(jeton: str) -> tuple[int, str] | None:
    """Renvoie (id, empreinte) porté par le jeton, ou None s'il est invalide/expiré/du mauvais type."""
    try:
        charge = jwt.decode(jeton, settings.SECRET_KEY, algorithms=[settings.ALGORITHME_JWT])
        if charge.get("type") != "reset":
            return None
        return int(charge["sub"]), charge.get("emp", "")
    except (JWTError, KeyError, ValueError):
        return None
