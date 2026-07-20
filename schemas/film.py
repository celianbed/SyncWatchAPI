# schemas/film.py
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from schemas.serie import GenrePublic


class FilmPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_film: int
    reference_tmdb: int
    titre: str
    titre_original: str | None
    synopsis: str | None
    affiche: str | None
    duree: int | None
    date_sortie: date | None
    note_moyenne_tmdb: float | None
    date_maj_cache: datetime
    genres: list[GenrePublic]
