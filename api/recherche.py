# api/recherche.py
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.dependances import cache_partage, client_tmdb, utilisateur_courant
from core.limitation import LIMITE_RECHERCHE, limiteur
from db.database import get_db
from models import Utilisateur
from schemas.recherche import ResultatRecherche
from schemas.social import ResumeUtilisateur
from services import social_service
from services.cache import Cache
from services.tmdb_client import ClientTMDB

router = APIRouter()

# Durées de cache. Les résultats TMDB bougent lentement et sont identiques pour
# tous les utilisateurs : rien ici n'est personnel, donc rien de confidentiel
# ne transite par le cache.
DUREE_CACHE_RECHERCHE_S = 3600       # 1 h — les mêmes titres reviennent souvent
DUREE_CACHE_DECOUVERTE_S = 3 * 3600  # 3 h — tendances et nouveautés du moment


def _mapper_multi(donnees: dict | None) -> list[ResultatRecherche]:
    """Projette une liste TMDB « multi » — les personnes sont ignorées."""
    resultats = []
    for brut in (donnees or {}).get("results", []):
        if brut.get("media_type") == "tv":
            resultats.append(ResultatRecherche.depuis_tmdb(brut, "serie"))
        elif brut.get("media_type") == "movie":
            resultats.append(ResultatRecherche.depuis_tmdb(brut, "film"))
    return resultats


def _cle_recherche(q: str) -> str:
    """Clé de cache d'une recherche.

    Normalise la casse et les espaces : « Chroniques », « chroniques » et
    « chroniques  » désignent la même recherche et doivent partager une entrée.
    La longueur de `q` est bornée par la validation de la route, donc la clé
    produite l'est aussi.
    """
    return "recherche:" + " ".join(q.lower().split())


async def _via_cache(cache: Cache, cle: str, produire, duree_s: int):
    """Renvoie la valeur en cache, sinon appelle `produire()` et la range.

    Un résultat vide ou absent (TMDB muet, panne) n'est jamais mis en cache :
    on ne veut pas figer un échec pour plusieurs heures.
    """
    donnees = await cache.lire(cle)
    if donnees is not None:
        return donnees
    donnees = await produire()
    if donnees:
        await cache.ecrire(cle, donnees, duree_s)
    return donnees


@router.get("", response_model=list[ResultatRecherche])
@limiteur.limit(LIMITE_RECHERCHE)  # public + coûte un appel TMDB
async def rechercher(
    request: Request,
    q: str = Query(min_length=1, max_length=100,
                   description="Titre de série ou de film"),
    tmdb: ClientTMDB = Depends(client_tmdb),
    cache: Cache = Depends(cache_partage),
):
    """Recherche TMDB (séries + films) — les personnes sont ignorées."""
    donnees = await _via_cache(cache, _cle_recherche(q),
                               lambda: tmdb.search_multi(q),
                               DUREE_CACHE_RECHERCHE_S)
    return _mapper_multi(donnees)


@router.get("/utilisateurs", response_model=list[ResumeUtilisateur])
@limiteur.limit(LIMITE_RECHERCHE)
def rechercher_utilisateurs(
    request: Request,
    q: str = Query(min_length=1, max_length=30, description="Pseudo à rechercher"),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Recherche d'utilisateurs par pseudo (soi-même exclu).

    Volontairement non mise en cache : le résultat dépend de l'appelant
    (exclusion de soi, état des abonnements) et porte des données de comptes.
    """
    users = db.scalars(
        select(Utilisateur).where(
            Utilisateur.pseudo.ilike(f"%{q.strip()}%"),
            Utilisateur.id_utilisateur != utilisateur.id_utilisateur,
            Utilisateur.statut_compte == "actif")
        .order_by(Utilisateur.pseudo).limit(20)).all()
    return social_service.resumes(db, utilisateur.id_utilisateur, list(users))


@router.get("/tendances", response_model=list[ResultatRecherche])
@limiteur.limit(LIMITE_RECHERCHE)
async def tendances(
    request: Request,
    tmdb: ClientTMDB = Depends(client_tmdb),
    cache: Cache = Depends(cache_partage),
):
    """Séries et films en tendance cette semaine — alimente l'écran découverte."""
    donnees = await _via_cache(cache, "tendances", tmdb.tendances,
                               DUREE_CACHE_DECOUVERTE_S)
    return _mapper_multi(donnees)


@router.get("/nouveautes", response_model=list[ResultatRecherche])
@limiteur.limit(LIMITE_RECHERCHE)
async def nouveautes(
    request: Request,
    type: Literal["serie", "film"] = Query(
        description="serie = à l'antenne cette semaine, film = en salles"),
    tmdb: ClientTMDB = Depends(client_tmdb),
    cache: Cache = Depends(cache_partage),
):
    """Nouveautés du moment : séries à l'antenne ou films à l'affiche."""
    produire = (tmdb.series_a_l_antenne if type == "serie"
                else tmdb.films_a_l_affiche)
    # `type` est un Literal validé par FastAPI : la clé ne peut prendre que
    # deux valeurs, aucune entrée libre ne se retrouve dans le cache.
    donnees = await _via_cache(cache, f"nouveautes:{type}", produire,
                               DUREE_CACHE_DECOUVERTE_S)
    return [ResultatRecherche.depuis_tmdb(brut, type)
            for brut in (donnees or {}).get("results", [])]
