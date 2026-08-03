# services/decouverte_service.py
# Feed « extraits » (façon Reels) : les titres en tendance de la semaine,
# accompagnés d'une bande-annonce YouTube **intégrable**.
import asyncio
import time

import httpx

from core.config import settings
from services.tmdb_client import ClientTMDB

# Cache mémoire par page : les tendances bougent lentement, et surtout on évite
# de rappeler TMDB (1 appel trending + 1 appel vidéos par titre) à chaque page.
_DUREE_CACHE_S = 3 * 3600

_URL_YOUTUBE_API = "https://www.googleapis.com/youtube/v3/videos"

_cache: dict[int, dict] = {}  # page -> {"expire": float, "items": list}


def vider_cache() -> None:
    """Réinitialise le cache (utilisé par les tests)."""
    _cache.clear()


def _annee(date_str: str | None) -> int | None:
    return int(date_str[:4]) if date_str and len(date_str) >= 4 else None


def _candidats_youtube(videos: list[dict]) -> list[str]:
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
    candidats = _candidats_youtube(await tmdb.videos(base.pop("_media"),
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


async def feed_extraits(tmdb: ClientTMDB, page: int = 1) -> list[dict]:
    """Une page de bandes-annonces intégrables des titres en tendance (avec cache).

    Alimente le feed infini : l'app demande page 1, 2, 3… puis reboucle.
    """
    entree = _cache.get(page)
    if entree is not None and time.monotonic() < entree["expire"]:
        return entree["items"]

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

    _cache[page] = {"expire": time.monotonic() + _DUREE_CACHE_S, "items": items}
    return items
