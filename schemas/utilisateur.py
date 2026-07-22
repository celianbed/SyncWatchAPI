# schemas/utilisateur.py
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UtilisateurCreation(BaseModel):
    adresse_mail: EmailStr
    pseudo: str = Field(min_length=3, max_length=30)
    mot_de_passe: str = Field(min_length=8)

    @field_validator("mot_de_passe")
    @classmethod
    def verifier_limite_bcrypt(cls, v: str) -> str:
        # bcrypt refuse les mots de passe de plus de 72 octets (pas caractères :
        # les accents comptent double en UTF-8)
        if len(v.encode("utf-8")) > 72:
            raise ValueError("mot de passe trop long (limite bcrypt : 72 octets)")
        return v


class DemandeVerification(BaseModel):
    """Renvoi du mail de confirmation à une adresse donnée."""

    adresse_mail: EmailStr


class DemandeReinitialisation(BaseModel):
    """Demande d'un lien de réinitialisation de mot de passe."""

    adresse_mail: EmailStr


class ConnexionGoogle(BaseModel):
    """id_token Google (obtenu par l'app via google_sign_in) à vérifier côté API."""

    id_token: str = Field(min_length=1)


class UtilisateurMaj(BaseModel):
    """Mise à jour partielle du profil — les champs absents restent inchangés."""

    pseudo: str | None = Field(default=None, min_length=3, max_length=30)
    # URL d'image ; null explicite = retirer l'avatar
    avatar: str | None = Field(default=None, max_length=500)


class UtilisateurPublic(BaseModel):
    """Représentation renvoyée par l'API — jamais le mot de passe."""

    model_config = ConfigDict(from_attributes=True)

    id_utilisateur: int
    adresse_mail: EmailStr
    pseudo: str
    avatar: str | None
    date_inscription: datetime
    statut_compte: str
    est_verifie: bool
