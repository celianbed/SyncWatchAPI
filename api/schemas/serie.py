# api/schemas/serie.py
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class GenrePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_genre: int
    libelle: str


class SeriePublique(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_serie: int
    reference_tmdb: int
    titre: str
    titre_original: str | None
    synopsis: str | None
    affiche: str | None
    image_de_fond: str | None
    statut_diffusion: str | None
    date_premiere_diffusion: date | None
    note_moyenne_tmdb: float | None
    date_maj_cache: datetime
    genres: list[GenrePublic]


class EpisodeDansSaison(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_episode: int
    num_episode: int
    titre: str | None
    synopsis: str | None
    duree: int | None
    date_diffusion: date | None
    vignette: str | None


class SaisonAvecEpisodes(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_saison: int
    num_saison: int
    titre: str | None
    affiche: str | None
    date_diffusion: date | None
    episodes: list[EpisodeDansSaison]
