# api/schemas/suivi.py
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

StatutSuivi = Literal["a_voir", "en_cours", "terminee", "abandonnee", "en_pause"]


class SuiviCreation(BaseModel):
    statut_suivi: StatutSuivi = "a_voir"
    favori: bool = False


class SuiviMaj(BaseModel):
    """PATCH du suivi : seuls les champs fournis sont modifiés."""

    statut_suivi: StatutSuivi | None = None
    favori: bool | None = None


class SuiviPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_serie: int
    statut_suivi: StatutSuivi
    favori: bool
    date_ajout: datetime


StatutFilm = Literal["a_voir", "vu"]


class SuiviFilmCreation(BaseModel):
    statut: StatutFilm = "a_voir"
    favori: bool = False


class SuiviFilmPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_film: int
    statut: StatutFilm
    favori: bool
