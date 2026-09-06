# tests/test_visionnage.py — épisodes/saisons vus, prochain épisode, accueil
import pytest
from sqlalchemy import select

from models import Episode, Saison
from tests.faux_tmdb import REF_SERIE


def _entete(jeton):
    return {"Authorization": f"Bearer {jeton}"}


@pytest.fixture()
def serie_suivie(client, jeton, db):
    """Série suivie (donc saisons + épisodes en cache) ; renvoie les ids utiles."""
    client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton))
    lignes = db.execute(
        select(Episode.id_episode, Saison.id_saison, Saison.num_saison, Episode.num_episode)
        .join(Saison, Episode.id_saison == Saison.id_saison)
        .order_by(Saison.num_saison, Episode.num_episode)).all()
    return {
        "episodes": [ligne.id_episode for ligne in lignes],  # S1E1, S1E2, S2E1, S2E2
        "saisons": sorted({ligne.id_saison for ligne in lignes}),
    }


def test_marquer_episode_vu(client, jeton, serie_suivie):
    reponse = client.post(f"/episodes/{serie_suivie['episodes'][0]}/vu",
                          headers=_entete(jeton))
    assert reponse.status_code == 201
    assert reponse.json()["nombre_revisionnage"] == 0


def test_revisionnage_compte(client, jeton, serie_suivie):
    id_episode = serie_suivie["episodes"][0]
    client.post(f"/episodes/{id_episode}/vu", headers=_entete(jeton))
    reponse = client.post(f"/episodes/{id_episode}/vu", headers=_entete(jeton))
    assert reponse.json()["nombre_revisionnage"] == 1


def test_episode_inconnu(client, jeton):
    assert client.post("/episodes/999999/vu", headers=_entete(jeton)).status_code == 404


def test_retirer_episode_vu(client, jeton, serie_suivie):
    id_episode = serie_suivie["episodes"][0]
    client.post(f"/episodes/{id_episode}/vu", headers=_entete(jeton))
    assert client.delete(f"/episodes/{id_episode}/vu",
                         headers=_entete(jeton)).status_code == 204
    assert client.delete(f"/episodes/{id_episode}/vu",
                         headers=_entete(jeton)).status_code == 404


def test_marquer_saison_vue(client, jeton, serie_suivie):
    id_saison_1 = serie_suivie["saisons"][0]
    reponse = client.post(f"/saisons/{id_saison_1}/vu", headers=_entete(jeton))
    assert reponse.status_code == 200
    assert reponse.json()["episodes_marques"] == 2

    # déjà tout vu : rien de nouveau à marquer
    reponse = client.post(f"/saisons/{id_saison_1}/vu", headers=_entete(jeton))
    assert reponse.json()["episodes_marques"] == 0


def test_saison_avec_episode_non_diffuse(client, jeton, serie_suivie):
    # S2E2 n'a pas de date de diffusion : seul S2E1 est marquable
    id_saison_2 = serie_suivie["saisons"][1]
    reponse = client.post(f"/saisons/{id_saison_2}/vu", headers=_entete(jeton))
    assert reponse.json()["episodes_marques"] == 1


def test_retirer_saison_vue(client, jeton, serie_suivie):
    id_saison_1 = serie_suivie["saisons"][0]
    client.post(f"/saisons/{id_saison_1}/vu", headers=_entete(jeton))

    reponse = client.delete(f"/saisons/{id_saison_1}/vu", headers=_entete(jeton))
    assert reponse.status_code == 200
    assert reponse.json()["episodes_retires"] == 2

    # idempotent : re-défaire ne retire plus rien, et n'est pas une erreur
    reponse = client.delete(f"/saisons/{id_saison_1}/vu", headers=_entete(jeton))
    assert reponse.json()["episodes_retires"] == 0

    saisons = client.get(f"/series/{REF_SERIE}/saisons", headers=_entete(jeton)).json()
    assert all(e["vu"] is False for e in saisons[0]["episodes"])


def test_retirer_saison_vue_ne_touche_pas_les_autres(client, jeton, serie_suivie):
    saison_1, saison_2 = serie_suivie["saisons"]
    client.post(f"/saisons/{saison_1}/vu", headers=_entete(jeton))
    client.post(f"/saisons/{saison_2}/vu", headers=_entete(jeton))

    client.delete(f"/saisons/{saison_2}/vu", headers=_entete(jeton))

    saisons = client.get(f"/series/{REF_SERIE}/saisons", headers=_entete(jeton)).json()
    assert [e["vu"] for e in saisons[0]["episodes"]] == [True, True]
    assert [e["vu"] for e in saisons[1]["episodes"]] == [False, False]


def test_retirer_saison_inconnue(client, jeton):
    assert client.delete("/saisons/999999/vu",
                         headers=_entete(jeton)).status_code == 404


def test_saisons_de_la_serie(client, jeton, serie_suivie):
    reponse = client.get(f"/series/{REF_SERIE}/saisons", headers=_entete(jeton))
    assert reponse.status_code == 200
    saisons = reponse.json()
    assert [s["num_saison"] for s in saisons] == [1, 2]
    assert [e["num_episode"] for e in saisons[0]["episodes"]] == [1, 2]
    assert all(e["vu"] is False for s in saisons for e in s["episodes"])


def test_saisons_portent_l_etat_vu_de_chacun(client, jeton, serie_suivie):
    # l'app en a besoin pour afficher une progression exacte : la déduction
    # « tout ce qui précède le prochain épisode est vu » devient fausse dès
    # qu'un épisode est dé-marqué au milieu.
    client.post(f"/episodes/{serie_suivie['episodes'][1]}/vu", headers=_entete(jeton))

    saisons = client.get(f"/series/{REF_SERIE}/saisons", headers=_entete(jeton)).json()
    assert [e["vu"] for e in saisons[0]["episodes"]] == [False, True]


def test_saisons_demandent_une_authentification(client, serie_suivie):
    assert client.get(f"/series/{REF_SERIE}/saisons").status_code == 401


def test_accueil(client, jeton, serie_suivie):
    reponse = client.get("/accueil", headers=_entete(jeton))
    assert reponse.status_code == 200
    entrees = reponse.json()
    assert len(entrees) == 1
    assert entrees[0]["serie"]["reference_tmdb"] == REF_SERIE
    episode = entrees[0]["episode"]
    assert (episode["num_saison"], episode["num_episode"]) == (1, 1)
    assert episode["deja_diffuse"] is True


def test_accueil_serie_a_jour(client, jeton, serie_suivie):
    # tout le diffusé est vu -> plus rien à proposer ce soir
    for id_saison in serie_suivie["saisons"]:
        client.post(f"/saisons/{id_saison}/vu", headers=_entete(jeton))
    assert client.get("/accueil", headers=_entete(jeton)).json() == []


def test_accueil_ignore_les_suivis_inactifs(client, jeton, serie_suivie):
    client.patch(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton),
                 json={"statut_suivi": "abandonnee"})
    assert client.get("/accueil", headers=_entete(jeton)).json() == []


def test_accueil_sans_jeton(client):
    assert client.get("/accueil").status_code == 401
