# services/cache.py — composant d'accès au magasin clé/valeur (Redis)
"""Cache partagé entre tous les workers et persistant aux redémarrages.

Remplace le dictionnaire en mémoire qui servait de cache au feed « extraits » :
celui-ci était propre à chaque process (deux workers = deux caches froids) et
disparaissait à chaque redémarrage — or le plan gratuit de Render endort le
service, donc il repartait vide à chaque réveil.

**Contrat de ce composant : il ne doit jamais faire échouer une requête.**
Redis absent, injoignable, lent, ou renvoyant une valeur illisible se traduit
par « rien en cache » — l'appelant recalcule, exactement comme si le cache
n'existait pas. C'est ce qui permet de tourner sans Redis (REDIS_URL vide, cas
des tests et du développement local) et de survivre à une panne du serveur de
cache sans indisponibilité de l'API.
"""
import json
import logging
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

journal = logging.getLogger(__name__)

# Préfixe versionné : incrémenter la version invalide tout le cache d'un coup,
# sans purge manuelle. Utile le jour où le format des valeurs stockées change.
PREFIXE = "syncwatch:v1:"

# Une opération de cache ne doit jamais coûter plus cher que le calcul qu'elle
# évite : au-delà d'une seconde, on abandonne et on recalcule.
DELAI_RESEAU_S = 1.0


class Cache:
    """Accès clé/valeur au cache. Les valeurs sont sérialisées en JSON."""

    def __init__(self, url: str = "", client=None):
        # `client` permet d'injecter une doublure dans les tests, comme le
        # paramètre `transport` de ClientTMDB.
        if client is not None:
            self._client = client
        elif url:
            self._client = redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=DELAI_RESEAU_S,
                socket_timeout=DELAI_RESEAU_S,
            )
        else:
            self._client = None  # cache désactivé : tout est un défaut de cache

    @property
    def actif(self) -> bool:
        return self._client is not None

    async def lire(self, cle: str) -> Any | None:
        """Valeur associée à la clé, ou None si absente/expirée/illisible."""
        if self._client is None:
            return None
        try:
            brut = await self._client.get(PREFIXE + cle)
        except (RedisError, OSError) as erreur:
            journal.warning("Cache injoignable en lecture (%s) : %s", cle, erreur)
            return None
        if brut is None:
            return None
        try:
            return json.loads(brut)
        except (json.JSONDecodeError, TypeError):
            # Valeur corrompue, ou écrite par une version antérieure du format :
            # on l'ignore plutôt que de propager l'erreur à l'appelant.
            journal.warning("Valeur de cache illisible (%s), ignorée", cle)
            return None

    async def ecrire(self, cle: str, valeur: Any, duree_s: int) -> None:
        """Range une valeur pour `duree_s` secondes. Échec silencieux par contrat."""
        if self._client is None:
            return
        try:
            await self._client.set(PREFIXE + cle, json.dumps(valeur), ex=duree_s)
        except (RedisError, OSError) as erreur:
            journal.warning("Cache injoignable en écriture (%s) : %s", cle, erreur)
        except (TypeError, ValueError) as erreur:
            # Valeur non sérialisable : c'est un bug d'appel, mais il ne doit pas
            # casser la réponse — on journalise et on continue sans cacher.
            journal.warning("Valeur non sérialisable pour le cache (%s) : %s", cle, erreur)

    async def fermer(self) -> None:
        if self._client is not None:
            await self._client.aclose()
