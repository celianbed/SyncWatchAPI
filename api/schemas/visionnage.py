# api/schemas/visionnage.py
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class EpisodeVu(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_episode: int
    date_visionnage: datetime
    nombre_revisionnage: int


class SaisonVue(BaseModel):
    episodes_marques: int


class FilmVu(BaseModel):
    id_film: int
    date_visionnage: datetime
    nombre_visionnages: int


class ProchainEpisode(BaseModel):
    id_episode: int
    num_saison: int
    num_episode: int
    titre: str | None
    synopsis: str | None
    duree: int | None
    date_diffusion: date | None
    vignette: str | None
    deja_diffuse: bool

    @classmethod
    def depuis_episode(cls, episode, num_saison: int) -> "ProchainEpisode":
        return cls(
            id_episode=episode.id_episode, num_saison=num_saison,
            num_episode=episode.num_episode, titre=episode.titre,
            synopsis=episode.synopsis, duree=episode.duree,
            date_diffusion=episode.date_diffusion, vignette=episode.vignette,
            deja_diffuse=episode.date_diffusion is not None
            and episode.date_diffusion <= date.today())


class SerieResume(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_serie: int
    reference_tmdb: int
    titre: str
    affiche: str | None


class AccueilEntree(BaseModel):
    """Une série à jour de visionnage n'apparaît pas dans l'accueil."""

    serie: SerieResume
    episode: ProchainEpisode


class CalendrierEntree(BaseModel):
    """Une diffusion à venir d'une série suivie (même forme que l'accueil)."""

    serie: SerieResume
    episode: ProchainEpisode
