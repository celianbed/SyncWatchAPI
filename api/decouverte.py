# api/decouverte.py
from fastapi import APIRouter, Depends, Query

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.dependances import cache_partage, client_tmdb, utilisateur_courant
from db.database import get_db
from models import Film, Serie, SuivreFilm, SuivreSerie, Utilisateur
from schemas.decouverte import ExtraitFeed
from services import decouverte_service
from services.cache import Cache
from services.tmdb_client import ClientTMDB

router = APIRouter()


@router.get("/extraits", response_model=list[ExtraitFeed])
async def extraits(
    page: int = Query(1, ge=1, le=500, description="Page du feed infini (tendances TMDB)"),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    tmdb: ClientTMDB = Depends(client_tmdb),
    cache: Cache = Depends(cache_partage),
    db: Session = Depends(get_db),
):
    """Feed de bandes-annonces (façon Reels) des titres en tendance — paginé.

    Les titres déjà suivis sont écartés : proposer en découverte une série
    qu'on suit déjà rate la cible.
    """
    return await decouverte_service.feed_extraits(
        tmdb, cache, page, _deja_suivis(db, utilisateur.id_utilisateur))


def _deja_suivis(db: Session, id_utilisateur: int) -> set[tuple[str, int]]:
    """(type, référence TMDB) de tout ce que la personne suit déjà."""
    series = db.scalars(
        select(Serie.reference_tmdb)
        .join(SuivreSerie, SuivreSerie.id_serie == Serie.id_serie)
        .where(SuivreSerie.id_utilisateur == id_utilisateur))
    films = db.scalars(
        select(Film.reference_tmdb)
        .join(SuivreFilm, SuivreFilm.id_film == Film.id_film)
        .where(SuivreFilm.id_utilisateur == id_utilisateur))
    return {("serie", r) for r in series} | {("film", r) for r in films}
