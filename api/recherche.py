# api/recherche.py
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.dependances import client_tmdb, utilisateur_courant
from core.limitation import LIMITE_RECHERCHE, limiteur
from db.database import get_db
from models import Utilisateur
from schemas.recherche import ResultatRecherche
from schemas.social import ResumeUtilisateur
from services import social_service
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
@limiteur.limit(LIMITE_RECHERCHE)  # public + coûte un appel TMDB
async def rechercher(
    request: Request,
    q: str = Query(min_length=1, description="Titre de série ou de film"),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Recherche TMDB en direct (séries + films) — les personnes sont ignorées."""
    return _mapper_multi(await tmdb.search_multi(q))


@router.get("/utilisateurs", response_model=list[ResumeUtilisateur])
@limiteur.limit(LIMITE_RECHERCHE)
def rechercher_utilisateurs(
    request: Request,
    q: str = Query(min_length=1, description="Pseudo à rechercher"),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Recherche d'utilisateurs par pseudo (soi-même exclu)."""
    users = db.scalars(
        select(Utilisateur).where(
            Utilisateur.pseudo.ilike(f"%{q.strip()}%"),
            Utilisateur.id_utilisateur != utilisateur.id_utilisateur,
            Utilisateur.statut_compte == "actif")
        .order_by(Utilisateur.pseudo).limit(20)).all()
    return social_service.resumes(db, utilisateur.id_utilisateur, list(users))


@router.get("/tendances", response_model=list[ResultatRecherche])
@limiteur.limit(LIMITE_RECHERCHE)
async def tendances(request: Request, tmdb: ClientTMDB = Depends(client_tmdb)):
    """Séries et films en tendance cette semaine — alimente l'écran découverte."""
    return _mapper_multi(await tmdb.tendances())


@router.get("/nouveautes", response_model=list[ResultatRecherche])
@limiteur.limit(LIMITE_RECHERCHE)
async def nouveautes(
    request: Request,
    type: Literal["serie", "film"] = Query(
        description="serie = à l'antenne cette semaine, film = en salles"),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Nouveautés du moment : séries à l'antenne ou films à l'affiche."""
    donnees = await (tmdb.series_a_l_antenne() if type == "serie"
                     else tmdb.films_a_l_affiche())
    return [ResultatRecherche.depuis_tmdb(brut, type)
            for brut in (donnees or {}).get("results", [])]
