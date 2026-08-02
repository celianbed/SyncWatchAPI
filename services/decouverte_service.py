# services/decouverte_service.py
# Feed « extraits » (façon Reels) : les titres en tendance de la semaine,
# accompagnés de leur meilleure bande-annonce YouTube.
import asyncio
import time

from services.tmdb_client import ClientTMDB

# Cache mémoire : les tendances bougent lentement, et surtout on évite de
# rappeler TMDB (1 appel trending + 1 appel vidéos par titre) à chaque ouverture
# de l'écran. En mono-worker, ce cache process suffit largement.
_DUREE_CACHE_S = 3 * 3600
_NB_MAX = 15  # nombre de titres gardés dans le feed (borne les appels vidéos)

_cache: dict = {"expire": 0.0, "items": []}


def vider_cache() -> None:
    """Réinitialise le cache (utilisé par les tests)."""
    _cache["expire"] = 0.0
    _cache["items"] = []


def _annee(date_str: str | None) -> int | None:
    return int(date_str[:4]) if date_str and len(date_str) >= 4 else None


def _meilleure_cle_youtube(videos: list[dict]) -> str | None:
    """Meilleure bande-annonce : Trailer > Teaser > Clip, officiel d'abord, VF avant VO."""
    candidats = [v for v in videos if v.get("site") == "YouTube" and v.get("key")]

    def score(v: dict) -> tuple:
        type_rang = {"Trailer": 0, "Teaser": 1, "Clip": 2}.get(v.get("type"), 3)
        non_officiel = 0 if v.get("official") else 1
        pas_fr = 0 if v.get("iso_639_1") == "fr" else 1
        return (type_rang, non_officiel, pas_fr)

    candidats.sort(key=score)
    return candidats[0]["key"] if candidats else None


async def _extrait_pour(tmdb: ClientTMDB, brut: dict) -> dict | None:
    """Entrée du feed pour un résultat de tendances, ou None si pas de trailer."""
    media_type = brut.get("media_type")
    if media_type == "tv":
        type_, media = "serie", "tv"
        titre, date_ = brut.get("name") or "", brut.get("first_air_date")
    elif media_type == "movie":
        type_, media = "film", "movie"
        titre, date_ = brut.get("title") or "", brut.get("release_date")
    else:
        return None  # personnes ignorées

    if not brut.get("poster_path"):
        return None

    cle = _meilleure_cle_youtube(await tmdb.videos(media, brut["id"]))
    if cle is None:
        return None  # sans bande-annonce, pas d'intérêt dans le feed

    return {
        "reference_tmdb": brut["id"],
        "type": type_,
        "titre": titre,
        "affiche": brut.get("poster_path"),
        "image_de_fond": brut.get("backdrop_path"),
        "apercu": brut.get("overview") or None,
        "annee": _annee(date_),
        "note_moyenne": brut.get("vote_average"),
        "cle_youtube": cle,
    }


async def feed_extraits(tmdb: ClientTMDB) -> list[dict]:
    """Feed de bandes-annonces des titres en tendance cette semaine (avec cache)."""
    if _cache["items"] and time.monotonic() < _cache["expire"]:
        return _cache["items"]

    # on part d'un peu plus de titres que la cible : certains n'ont pas de trailer
    tendances = (await tmdb.tendances() or {}).get("results", [])[: _NB_MAX * 2]
    # vidéos récupérées en parallèle : les temps d'attente réseau se recouvrent
    extraits = await asyncio.gather(*(_extrait_pour(tmdb, b) for b in tendances))
    items = [e for e in extraits if e is not None][:_NB_MAX]

    _cache["items"] = items
    _cache["expire"] = time.monotonic() + _DUREE_CACHE_S
    return items
