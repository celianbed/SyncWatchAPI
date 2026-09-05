# api/decouverte.py
from fastapi import APIRouter, Depends, Query

from api.dependances import cache_partage, client_tmdb, utilisateur_courant
from models import Utilisateur
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
):
    """Feed de bandes-annonces (façon Reels) des titres en tendance — paginé."""
    return await decouverte_service.feed_extraits(tmdb, cache, page)
