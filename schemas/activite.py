# schemas/activite.py
from datetime import datetime

from pydantic import BaseModel


class ActeurActivite(BaseModel):
    id_utilisateur: int
    pseudo: str
    avatar: str | None


class EvenementActivite(BaseModel):
    """Un évènement du fil d'activité des personnes suivies."""

    type: str  # "avis" | "film_vu" | "serie_suivie"
    date: datetime
    acteur: ActeurActivite
    titre: str
    type_cible: str  # "serie" | "film"
    reference_tmdb: int | None
    note: int | None = None  # renseigné pour les avis notés
