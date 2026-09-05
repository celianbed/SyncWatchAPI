# tests/test_cache.py — tests unitaires du composant d'accès au cache clé/valeur.
#
# Aucun Redis n'est nécessaire : le client est remplacé par une doublure, comme
# le transport httpx l'est pour le client TMDB (cf. test_tmdb_client.py), et les
# coroutines sont lancées par asyncio.run — même patron que le reste des tests.
#
# L'essentiel porte sur le **mode dégradé** : le contrat du composant est de ne
# jamais faire échouer une requête, quoi qu'il arrive côté Redis.
import asyncio
import json

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from services.cache import PREFIXE, Cache

PANNES = [
    RedisConnectionError("connexion refusée"),
    RedisTimeoutError("délai dépassé"),
    OSError("réseau indisponible"),
]


class FauxClientRedis:
    """Client Redis minimal en mémoire : mémorise la dernière durée demandée."""

    def __init__(self):
        self.donnees: dict[str, str] = {}
        self.dernier_ex: int | None = None

    async def get(self, cle):
        return self.donnees.get(cle)

    async def set(self, cle, valeur, ex=None):
        self.donnees[cle] = valeur
        self.dernier_ex = ex

    async def aclose(self):
        pass


class ClientEnPanne:
    """Client dont chaque opération échoue, comme un Redis injoignable."""

    def __init__(self, erreur):
        self.erreur = erreur

    async def get(self, cle):
        raise self.erreur

    async def set(self, cle, valeur, ex=None):
        raise self.erreur

    async def aclose(self):
        pass


# --- cache désactivé (REDIS_URL vide) : développement local, CI, tests ---------


def test_cache_sans_url_est_inactif():
    cache = Cache("")
    assert cache.actif is False

    async def scenario():
        avant = await cache.lire("peu importe")
        # une écriture ne doit pas lever : l'appelant n'a pas à savoir si le
        # cache existe, il appelle de la même façon dans tous les cas
        await cache.ecrire("peu importe", {"a": 1}, 60)
        return avant, await cache.lire("peu importe")

    assert asyncio.run(scenario()) == (None, None)


# --- fonctionnement nominal ---------------------------------------------------


def test_ecriture_puis_lecture():
    cache = Cache(client=FauxClientRedis())

    async def scenario():
        await cache.ecrire("titres", [{"id": 1, "titre": "Les Chroniques"}], 60)
        return await cache.lire("titres")

    assert asyncio.run(scenario()) == [{"id": 1, "titre": "Les Chroniques"}]


def test_cle_absente_renvoie_none():
    cache = Cache(client=FauxClientRedis())
    assert asyncio.run(cache.lire("jamais ecrite")) is None


def test_les_cles_sont_prefixees_et_versionnees():
    """Le préfixe isole SyncWatch d'un Redis partagé et permet d'invalider tout
    le cache en changeant la version, sans purge manuelle."""
    client = FauxClientRedis()
    asyncio.run(Cache(client=client).ecrire("tendances", [1, 2], 60))
    assert list(client.donnees) == [PREFIXE + "tendances"]


def test_la_duree_est_transmise_a_redis():
    client = FauxClientRedis()
    asyncio.run(Cache(client=client).ecrire("tendances", [1, 2], 3600))
    assert client.dernier_ex == 3600


def test_valeurs_json_courantes_font_l_aller_retour():
    """Les types réellement stockés par l'application : dicts imbriqués, listes,
    None, nombres et booléens."""
    client = FauxClientRedis()
    cache = Cache(client=client)
    valeur = {"results": [{"id": 1, "note": 8.4, "vu": True, "titre": None}]}

    async def scenario():
        await cache.ecrire("multi", valeur, 60)
        return await cache.lire("multi")

    assert asyncio.run(scenario()) == valeur
    # rangé sérialisé, pas en objet Python
    assert json.loads(client.donnees[PREFIXE + "multi"]) == valeur


# --- mode dégradé : c'est le cœur du contrat ----------------------------------


@pytest.mark.parametrize("erreur", PANNES, ids=["connexion", "timeout", "reseau"])
def test_lecture_sur_redis_en_panne_renvoie_none(erreur):
    """Redis injoignable = défaut de cache, jamais une erreur remontée à l'appelant."""
    cache = Cache(client=ClientEnPanne(erreur))
    assert asyncio.run(cache.lire("tendances")) is None


@pytest.mark.parametrize("erreur", PANNES, ids=["connexion", "timeout", "reseau"])
def test_ecriture_sur_redis_en_panne_ne_leve_pas(erreur):
    cache = Cache(client=ClientEnPanne(erreur))
    asyncio.run(cache.ecrire("tendances", [1, 2], 60))  # ne doit pas lever


def test_valeur_illisible_est_ignoree():
    """Valeur corrompue, ou écrite par une version antérieure du format."""
    client = FauxClientRedis()
    client.donnees[PREFIXE + "tendances"] = "{ceci n'est pas du JSON"
    assert asyncio.run(Cache(client=client).lire("tendances")) is None


def test_valeur_non_serialisable_ne_leve_pas():
    """Un objet non JSON est un bug d'appel : journalisé, jamais propagé."""
    client = FauxClientRedis()

    class Inserialisable:
        pass

    asyncio.run(Cache(client=client).ecrire("bidon", Inserialisable(), 60))
    assert client.donnees == {}  # rien n'a été rangé
