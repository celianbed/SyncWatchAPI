# api/api/stats.py
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.api.dependances import utilisateur_courant
from api.db.database import get_db
from api.models import (Episode, Film, SuivreSerie, Utilisateur,
                        VisionnerEpisode, VisionnerFilm)
from api.schemas.stats import PeriodeStats, StatsGlobales

router = APIRouter()

_TRONCATURES = {"jour": "day", "semaine": "week", "mois": "month"}


@router.get("", response_model=StatsGlobales)
def stats_globales(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    uid = utilisateur.id_utilisateur

    episodes_vus = db.scalar(select(func.count()).select_from(VisionnerEpisode)
                             .where(VisionnerEpisode.id_utilisateur == uid))
    minutes_episodes = db.scalar(
        select(func.coalesce(func.sum(Episode.duree), 0))
        .select_from(VisionnerEpisode)
        .join(Episode, VisionnerEpisode.id_episode == Episode.id_episode)
        .where(VisionnerEpisode.id_utilisateur == uid))

    # films : chaque visionnage compte dans le temps, mais un film revu reste un seul film "vu"
    films_vus = db.scalar(select(func.count(func.distinct(VisionnerFilm.id_film)))
                          .where(VisionnerFilm.id_utilisateur == uid))
    minutes_films = db.scalar(
        select(func.coalesce(func.sum(Film.duree), 0))
        .select_from(VisionnerFilm)
        .join(Film, VisionnerFilm.id_film == Film.id_film)
        .where(VisionnerFilm.id_utilisateur == uid))

    series_suivies = db.scalar(select(func.count()).select_from(SuivreSerie)
                               .where(SuivreSerie.id_utilisateur == uid))
    series_terminees = db.scalar(select(func.count()).select_from(SuivreSerie)
                                 .where(SuivreSerie.id_utilisateur == uid,
                                        SuivreSerie.statut_suivi == "terminee"))

    return StatsGlobales(
        episodes_vus=episodes_vus, films_vus=films_vus,
        series_suivies=series_suivies, series_terminees=series_terminees,
        minutes_episodes=minutes_episodes, minutes_films=minutes_films,
        minutes_totales=minutes_episodes + minutes_films)


@router.get("/historique", response_model=list[PeriodeStats])
def historique(
    periode: Literal["jour", "semaine", "mois"] = "mois",
    debut: date | None = None,
    fin: date | None = None,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Épisodes vus et minutes par tranche de temps (bornes debut/fin optionnelles)."""
    tranche = func.date_trunc(_TRONCATURES[periode],
                              VisionnerEpisode.date_visionnage).label("periode")
    requete = (
        select(tranche,
               func.count().label("episodes_vus"),
               func.coalesce(func.sum(Episode.duree), 0).label("minutes"))
        .select_from(VisionnerEpisode)
        .join(Episode, VisionnerEpisode.id_episode == Episode.id_episode)
        .where(VisionnerEpisode.id_utilisateur == utilisateur.id_utilisateur)
        .group_by(tranche)
        .order_by(tranche))
    if debut is not None:
        requete = requete.where(VisionnerEpisode.date_visionnage >= debut)
    if fin is not None:
        requete = requete.where(VisionnerEpisode.date_visionnage < fin)
    return [PeriodeStats(periode=ligne.periode, episodes_vus=ligne.episodes_vus,
                         minutes=ligne.minutes)
            for ligne in db.execute(requete)]
