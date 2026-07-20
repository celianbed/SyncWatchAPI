# api/tests/test_tmdb_client.py — le vrai client, sur un transport httpx simulé
import asyncio

import httpx
import pytest

from api.services.tmdb_client import ClientTMDB


def _client_capture(reponse: httpx.Response):
    """ClientTMDB branché sur un transport simulé + liste des requêtes émises."""
    requetes = []

    def gestionnaire(requete):
        requetes.append(requete)
        return reponse

    return ClientTMDB(transport=httpx.MockTransport(gestionnaire)), requetes


def test_authentification_et_langue():
    async def scenario():
        client, requetes = _client_capture(httpx.Response(200, json={}))
        await client.get_serie(42)
        await client.fermer()
        return requetes[0]

    requete = asyncio.run(scenario())
    assert requete.headers["Authorization"].startswith("Bearer ")
    assert requete.url.params["language"] == "fr-FR"
    assert requete.url.path.endswith("/tv/42")


def test_parametres_de_recherche():
    async def scenario():
        client, requetes = _client_capture(httpx.Response(200, json={"results": []}))
        await client.search_multi("dune")
        await client.fermer()
        return requetes[0]

    params = asyncio.run(scenario()).url.params
    assert params["query"] == "dune"
    assert params["include_adult"] == "false"


def test_chemin_des_tendances():
    async def scenario():
        client, requetes = _client_capture(httpx.Response(200, json={"results": []}))
        await client.tendances()
        await client.fermer()
        return requetes[0]

    assert asyncio.run(scenario()).url.path.endswith("/trending/all/week")


def test_ressource_inconnue_renvoie_none():
    async def scenario():
        client, _ = _client_capture(httpx.Response(404, json={"status_code": 34}))
        resultat = await client.get_film(1)
        await client.fermer()
        return resultat

    assert asyncio.run(scenario()) is None


def test_erreur_serveur_leve_une_exception():
    async def scenario():
        client, _ = _client_capture(httpx.Response(500))
        try:
            await client.get_saison(42, 1)
        finally:
            await client.fermer()

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(scenario())


def test_rate_limit_reessaye_puis_reussit():
    appels = {"n": 0}

    def gestionnaire(requete):
        appels["n"] += 1
        if appels["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"id": 1})

    async def scenario():
        client = ClientTMDB(transport=httpx.MockTransport(gestionnaire))
        resultat = await client.get_film(1)
        await client.fermer()
        return resultat

    assert asyncio.run(scenario()) == {"id": 1}
    assert appels["n"] == 3


def test_rate_limit_persistant_finit_par_lever():
    def gestionnaire(requete):
        return httpx.Response(429, headers={"Retry-After": "0"})

    async def scenario():
        client = ClientTMDB(transport=httpx.MockTransport(gestionnaire))
        try:
            await client.get_film(1)
        finally:
            await client.fermer()

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(scenario())
