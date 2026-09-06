# services/decouverte_service.py
# Feed « extraits » (façon Reels) : les titres en tendance de la semaine,
# accompagnés d'une bande-annonce YouTube **intégrable**.
import asyncio

import httpx

from core.config import settings
from services.cache import Cache
from services.tmdb_client import ClientTMDB

# Cache par page : les tendances bougent lentement, et reconstruire une page
# coûte cher (1 appel tendances + 1 appel vidéos par titre + 1 appel YouTube).
# Stocké dans Redis, donc partagé entre workers et conservé au redémarrage.
_DUREE_CACHE_S = 3 * 3600

_URL_YOUTUBE_API = "https://www.googleapis.com/youtube/v3/videos"


def _annee(date_str: str | None) -> int | None:
    return int(date_str[:4]) if date_str and len(date_str) >= 4 else None


def candidats_youtube(videos: list[dict]) -> list[str]:
    """Clés YouTube d'un titre, classées par pertinence : Trailer > Teaser > Clip,
    officiel d'abord, VF avant VO. Doublons et vidéos non-YouTube écartés."""
    candidats = [v for v in videos if v.get("site") == "YouTube" and v.get("key")]

    def score(v: dict) -> tuple:
        type_rang = {"Trailer": 0, "Teaser": 1, "Clip": 2}.get(v.get("type"), 3)
        non_officiel = 0 if v.get("official") else 1
        pas_fr = 0 if v.get("iso_639_1") == "fr" else 1
        return (type_rang, non_officiel, pas_fr)

    candidats.sort(key=score)
    vues, cles = set(), []
    for v in candidats:
        if v["key"] not in vues:
            vues.add(v["key"])
            cles.append(v["key"])
    return cles


def _base_titre(brut: dict) -> dict | None:
    """Champs communs d'une entrée du feed (sans la clé vidéo), ou None si le
    titre n'est pas exploitable (personne, ou pas d'affiche)."""
    media_type = brut.get("media_type")
    if media_type == "tv":
        type_, media = "serie", "tv"
        titre, date_ = brut.get("name") or "", brut.get("first_air_date")
    elif media_type == "movie":
        type_, media = "film", "movie"
        titre, date_ = brut.get("title") or "", brut.get("release_date")
    else:
        return None
    if not brut.get("poster_path"):
        return None
    return {
        "reference_tmdb": brut["id"],
        "type": type_,
        "_media": media,  # interne, retiré avant la réponse
        "titre": titre,
        "affiche": brut.get("poster_path"),
        "image_de_fond": brut.get("backdrop_path"),
        "apercu": brut.get("overview") or None,
        "annee": _annee(date_),
        "note_moyenne": brut.get("vote_average"),
    }


async def _titre_avec_candidats(
    tmdb: ClientTMDB, brut: dict
) -> tuple[dict, list[str]] | None:
    """(infos du titre, clés candidates) ou None si rien d'exploitable."""
    base = _base_titre(brut)
    if base is None:
        return None
    candidats = candidats_youtube(await tmdb.videos(base.pop("_media"),
                                                     base["reference_tmdb"]))
    if not candidats:
        return None
    return base, candidats


def _parser_integrables(items: list[dict]) -> set[str]:
    """Clés réellement intégrables et publiques (réponse YouTube Data API)."""
    return {
        item["id"]
        for item in items
        if item.get("status", {}).get("embeddable")
        and item.get("status", {}).get("privacyStatus") == "public"
    }


async def _cles_integrables(cles: list[str]) -> set[str]:
    """Sous-ensemble des clés dont l'intégration est autorisée (YouTube Data API).

    Sans YOUTUBE_API_KEY, ou en cas d'erreur API, on ne filtre pas (toutes
    gardées) : le repli côté app couvre alors les vidéos non lisibles.
    """
    if not settings.YOUTUBE_API_KEY or not cles:
        return set(cles)
    integrables: set[str] = set()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            for i in range(0, len(cles), 50):  # l'API accepte 50 ids par appel
                lot = cles[i:i + 50]
                reponse = await client.get(_URL_YOUTUBE_API, params={
                    "part": "status",
                    "id": ",".join(lot),
                    "key": settings.YOUTUBE_API_KEY,
                    "fields": "items(id,status(embeddable,privacyStatus))",
                })
                reponse.raise_for_status()
                integrables |= _parser_integrables(reponse.json().get("items", []))
    except httpx.HTTPError:
        return set(cles)  # API indisponible : ne pas bloquer le feed
    return integrables


# En dessous de ce nombre d'extraits, on va chercher la page suivante : écarter
# les titres déjà suivis peut vider une page, et un feed vide n'a rien à montrer.
MINIMUM_PAR_PAGE = 5
PAGES_MAX_PARCOURUES = 3


async def feed_extraits(tmdb: ClientTMDB, cache: Cache, page: int = 1,
                        deja_suivis: set[tuple[str, int]] | None = None) -> list[dict]:
    """Bandes-annonces intégrables des titres en tendance, à partir de `page`.

    `deja_suivis` — (type, référence TMDB) — est écarté : un feed de découverte
    qui propose ce qu'on suit déjà rate sa cible. Le filtrage a lieu après la
    lecture du cache, qui reste donc partagé entre tous les utilisateurs.
    """
    retenus: list[dict] = []
    for decalage in range(PAGES_MAX_PARCOURUES):
        bruts = await _page_brute(tmdb, cache, page + decalage)
        if not bruts:
            break
        retenus += [
            item for item in bruts
            if not deja_suivis
            or (item["type"], item["reference_tmdb"]) not in deja_suivis
        ]
        if len(retenus) >= MINIMUM_PAR_PAGE:
            break
    return retenus


async def _page_brute(tmdb: ClientTMDB, cache: Cache, page: int) -> list[dict]:
    """Une page de tendances, sans filtrage — mise en cache telle quelle."""
    cle_cache = f"extraits:{page}"
    items = await cache.lire(cle_cache)
    if items is not None:
        return items

    tendances = (await tmdb.tendances(page) or {}).get("results", [])
    # vidéos récupérées en parallèle : les temps d'attente réseau se recouvrent
    resultats = await asyncio.gather(
        *(_titre_avec_candidats(tmdb, b) for b in tendances))
    titres = [r for r in resultats if r is not None]

    # un seul appel Data API pour vérifier l'intégration de toutes les clés
    toutes_cles = [cle for _, candidats in titres for cle in candidats]
    integrables = await _cles_integrables(toutes_cles)

    items = []
    for base, candidats in titres:
        # meilleure clé du titre parmi celles réellement intégrables
        cle = next((c for c in candidats if c in integrables), None)
        if cle is not None:
            items.append({**base, "cle_youtube": cle})

    await cache.ecrire(cle_cache, items, _DUREE_CACHE_S)
    return items
