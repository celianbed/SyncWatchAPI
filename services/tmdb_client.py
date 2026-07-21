# services/tmdb_client.py
import asyncio

import httpx

from core.config import settings

MAX_TENTATIVES = 3  # sur rate limit (429)


class ClientTMDB:
    """Client asynchrone pour l'API TMDB v3 (jeton d'accès en lecture v4)."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        # .strip() : un espace / retour à la ligne collé au jeton produit un header
        # illégal (httpx.LocalProtocolError). Sans jeton, on n'envoie pas d'en-tête
        # Authorization vide (« Bearer ») — TMDB renverra alors un 401 explicite.
        jeton = settings.TMDB_API_TOKEN.strip()
        entetes = {"Authorization": f"Bearer {jeton}"} if jeton else {}
        self._http = httpx.AsyncClient(
            base_url=settings.TMDB_URL_BASE,
            headers=entetes,
            params={"language": settings.TMDB_LANGUE},
            timeout=10.0,
            transport=transport,
        )

    async def fermer(self) -> None:
        await self._http.aclose()

    async def _get(self, chemin: str, **params) -> dict | None:
        """GET sur l'API ; None si la ressource n'existe pas (404).

        Sur 429, attend le délai annoncé par Retry-After puis réessaye
        (MAX_TENTATIVES au total) avant de laisser filer l'exception.
        """
        for tentative in range(MAX_TENTATIVES):
            reponse = await self._http.get(chemin, params=params)
            # dernière tentative : le 429 tombe dans raise_for_status comme les autres erreurs
            if reponse.status_code == 429 and tentative < MAX_TENTATIVES - 1:
                await asyncio.sleep(float(reponse.headers.get("Retry-After", "1")))
                continue
            if reponse.status_code == 404:
                return None
            reponse.raise_for_status()
            return reponse.json()
        return None  # jamais atteint : la dernière tentative retourne ou lève

    async def search_multi(self, requete: str) -> dict | None:
        """Recherche séries + films (+ personnes, à filtrer) en un seul appel."""
        return await self._get("/search/multi", query=requete, include_adult=False)

    async def tendances(self) -> dict | None:
        """Séries + films (+ personnes, à filtrer) en tendance sur la semaine."""
        return await self._get("/trending/all/week")

    async def series_a_l_antenne(self) -> dict | None:
        """Séries avec un épisode diffusé ces prochains jours."""
        return await self._get("/tv/on_the_air")

    async def films_a_l_affiche(self) -> dict | None:
        """Films actuellement en salles."""
        return await self._get("/movie/now_playing")

    async def plateformes(self, media: str, tmdb_id: int) -> dict | None:
        """Offres de visionnage par pays (media = "tv" ou "movie").

        Données JustWatch relayées par TMDB : l'attribution est obligatoire.
        """
        return await self._get(f"/{media}/{tmdb_id}/watch/providers")

    async def similaires(self, media: str, tmdb_id: int) -> dict | None:
        """Recommandations TMDB pour un titre (media = "tv" ou "movie")."""
        return await self._get(f"/{media}/{tmdb_id}/recommendations")

    async def get_serie(self, tmdb_id: int, append: str | None = None) -> dict | None:
        """Fiche série ; `append` = append_to_response pour limiter les allers-retours."""
        params = {"append_to_response": append} if append else {}
        return await self._get(f"/tv/{tmdb_id}", **params)

    async def get_saison(self, tmdb_id: int, num_saison: int) -> dict | None:
        """Détail d'une saison, avec tous ses épisodes."""
        return await self._get(f"/tv/{tmdb_id}/season/{num_saison}")

    async def get_film(self, tmdb_id: int) -> dict | None:
        return await self._get(f"/movie/{tmdb_id}")
