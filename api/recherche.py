# api/recherche.py
from typing import Literal

from fastapi import APIRouter, Depends, Query

from api.dependances import client_tmdb
from schemas.recherche import ResultatRecherche
from services.tmdb_client import ClientTMDB

router = APIRouter()


def _mapper_multi(donnees: dict | None) -> list[ResultatRecherche]:
    """Projette une liste TMDB « multi » — les personnes sont ignorées."""
    resultats = []
    for brut in (donnees or {}).get("results", []):
        if brut.get("media_type") == "tv":
            resultats.append(ResultatRecherche.depuis_tmdb(brut, "serie"))
        elif brut.get("media_type") == "movie":
            resultats.append(ResultatRecherche.depuis_tmdb(brut, "film"))
    return resultats


@router.get("", response_model=list[ResultatRecherche])
async def rechercher(
    q: str = Query(min_length=1, description="Titre de série ou de film"),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Recherche TMDB en direct (séries + films) — les personnes sont ignorées."""
    return _mapper_multi(await tmdb.search_multi(q))


@router.get("/tendances", response_model=list[ResultatRecherche])
async def tendances(tmdb: ClientTMDB = Depends(client_tmdb)):
    """Séries et films en tendance cette semaine — alimente l'écran découverte."""
    return _mapper_multi(await tmdb.tendances())


@router.get("/nouveautes", response_model=list[ResultatRecherche])
async def nouveautes(
    type: Literal["serie", "film"] = Query(
        description="serie = à l'antenne cette semaine, film = en salles"),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Nouveautés du moment : séries à l'antenne ou films à l'affiche."""
    donnees = await (tmdb.series_a_l_antenne() if type == "serie"
                     else tmdb.films_a_l_affiche())
    return [ResultatRecherche.depuis_tmdb(brut, type)
            for brut in (donnees or {}).get("results", [])]
