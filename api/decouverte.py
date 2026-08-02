# api/decouverte.py
from fastapi import APIRouter, Depends

from api.dependances import client_tmdb, utilisateur_courant
from models import Utilisateur
from schemas.decouverte import ExtraitFeed
from services import decouverte_service
from services.tmdb_client import ClientTMDB

router = APIRouter()


@router.get("/extraits", response_model=list[ExtraitFeed])
async def extraits(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Feed de bandes-annonces (façon Reels) des titres en tendance cette semaine."""
    return await decouverte_service.feed_extraits(tmdb)
