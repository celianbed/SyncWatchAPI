# api/stats.py
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import func, literal, select, union_all
from sqlalchemy.orm import Session

from api.dependances import utilisateur_courant
from db.database import get_db
from models import (Episode, Film, SuivreSerie, Utilisateur,
                        VisionnerEpisode, VisionnerFilm)
from schemas.stats import PeriodeStats, StatsGlobales

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
    """Visionnages (épisodes + films) et minutes par tranche de temps."""
    uid = utilisateur.id_utilisateur

    # on unifie épisodes et films dans une même colonne (date, durée, est_film)
    episodes = (
        select(VisionnerEpisode.date_visionnage.label("date_v"),
               Episode.duree.label("duree"),
               literal(False).label("est_film"))
        .join(Episode, VisionnerEpisode.id_episode == Episode.id_episode)
        .where(VisionnerEpisode.id_utilisateur == uid))
    films = (
        select(VisionnerFilm.date_visionnage.label("date_v"),
               Film.duree.label("duree"),
               literal(True).label("est_film"))
        .join(Film, VisionnerFilm.id_film == Film.id_film)
        .where(VisionnerFilm.id_utilisateur == uid))
    if debut is not None:
        episodes = episodes.where(VisionnerEpisode.date_visionnage >= debut)
        films = films.where(VisionnerFilm.date_visionnage >= debut)
    if fin is not None:
        episodes = episodes.where(VisionnerEpisode.date_visionnage < fin)
        films = films.where(VisionnerFilm.date_visionnage < fin)

    v = union_all(episodes, films).subquery()
    tranche = func.date_trunc(_TRONCATURES[periode], v.c.date_v).label("periode")
    requete = (
        select(tranche,
               func.count().filter(v.c.est_film.is_(False)).label("episodes_vus"),
               func.count().filter(v.c.est_film.is_(True)).label("films_vus"),
               func.coalesce(func.sum(v.c.duree), 0).label("minutes"))
        .group_by(tranche)
        .order_by(tranche))
    return [PeriodeStats(periode=ligne.periode, episodes_vus=ligne.episodes_vus,
                         films_vus=ligne.films_vus, minutes=ligne.minutes)
            for ligne in db.execute(requete)]
