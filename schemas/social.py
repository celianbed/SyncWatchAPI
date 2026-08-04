# schemas/social.py
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class RecommandationCreation(BaseModel):
    """Recommander un titre à un ami."""

    reference_tmdb: int
    type: Literal["serie", "film"]


class ResumeUtilisateur(BaseModel):
    """Ligne d'utilisateur dans une liste (recherche, abonnés, abonnements)."""

    id_utilisateur: int
    pseudo: str
    avatar: str | None
    nb_series: int
    nb_films: int
    est_abonne: bool  # l'utilisateur courant suit celui-ci
    me_suit: bool     # celui-ci suit l'utilisateur courant
    est_ami: bool     # suivi mutuel


class ProgressionAmi(BaseModel):
    """Où en est une personne suivie sur une série commune (anti-spoiler)."""

    id_utilisateur: int
    pseudo: str
    avatar: str | None
    episodes_vus: int
    total_episodes: int
    prochain_code: str | None  # « S03E05 » ; None si la série est finie


class Compatibilite(BaseModel):
    """Score de compatibilité de goûts entre l'utilisateur courant et un autre."""

    pourcentage: int  # 0..100
    titres_communs: int
    base: str  # "notes" (concordance des notes) | "titres" (recouvrement) | "aucune"


class AvisProfil(BaseModel):
    """Un avis affiché sur le profil public : titre de la cible + note (sans commentaire)."""

    id_avis: int
    titre: str
    type: str  # "serie" | "film" | "episode"
    reference_tmdb: int | None  # pour ouvrir la fiche au tap
    note: int | None
    date_creation: datetime


class ProfilPublic(BaseModel):
    """Profil public détaillé d'un utilisateur (jamais l'adresse mail)."""

    id_utilisateur: int
    pseudo: str
    avatar: str | None
    date_inscription: datetime
    nb_abonnes: int
    nb_abonnements: int
    nb_series: int
    est_abonne: bool
    me_suit: bool
    est_ami: bool
