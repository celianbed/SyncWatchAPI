# tests/test_series.py
from sqlalchemy import func, select

from models import Episode, Saison, SuivreSerie
from tests.faux_tmdb import REF_SERIE


def _entete(jeton):
    return {"Authorization": f"Bearer {jeton}"}


def test_fiche_serie(client_connecte):
    reponse = client_connecte.get(f"/series/{REF_SERIE}")
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["titre"] == "Les Chroniques"
    assert corps["reference_tmdb"] == REF_SERIE
    assert {g["libelle"] for g in corps["genres"]} == {"Drame", "Science-Fiction & Fantastique"}


def test_fiche_servie_du_cache(client_connecte, tmdb_faux):
    client_connecte.get(f"/series/{REF_SERIE}")
    client_connecte.get(f"/series/{REF_SERIE}")
    assert tmdb_faux.compteurs["get_serie"] == 1


def test_fiche_inconnue(client_connecte):
    assert client_connecte.get("/series/999999").status_code == 404


def test_suivre_sans_jeton(client):
    assert client.post(f"/series/{REF_SERIE}/suivre").status_code == 401


def test_suivre(client, jeton, db):
    reponse = client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton))
    assert reponse.status_code == 201
    corps = reponse.json()
    assert corps["statut_suivi"] == "a_voir"
    assert corps["favori"] is False

    # le suivi déclenche la mise en cache du détail : saisons + épisodes
    assert db.scalar(select(func.count()).select_from(Saison)) == 2
    assert db.scalar(select(func.count()).select_from(Episode)) == 4
    assert db.scalar(select(func.count()).select_from(SuivreSerie)) == 1


def test_suivre_deux_fois(client, jeton):
    client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton))
    reponse = client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton))
    assert reponse.status_code == 409


def test_suivre_avec_options(client, jeton):
    reponse = client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton),
                          json={"statut_suivi": "en_cours", "favori": True})
    assert reponse.status_code == 201
    corps = reponse.json()
    assert corps["statut_suivi"] == "en_cours"
    assert corps["favori"] is True


def test_suivre_statut_invalide(client, jeton):
    reponse = client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton),
                          json={"statut_suivi": "nimporte"})
    assert reponse.status_code == 422


def test_suivre_serie_inconnue(client, jeton):
    reponse = client.post("/series/999999/suivre", headers=_entete(jeton))
    assert reponse.status_code == 404


def test_modifier_suivi(client, jeton):
    client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton))
    reponse = client.patch(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton),
                           json={"statut_suivi": "terminee"})
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["statut_suivi"] == "terminee"
    assert corps["favori"] is False  # champ non fourni : inchangé


def test_modifier_suivi_inexistant(client, jeton):
    reponse = client.patch(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton),
                           json={"favori": True})
    assert reponse.status_code == 404


def test_ne_plus_suivre(client, jeton, db):
    client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton))
    assert client.delete(f"/series/{REF_SERIE}/suivre",
                         headers=_entete(jeton)).status_code == 204
    assert db.scalar(select(func.count()).select_from(SuivreSerie)) == 0
    # le cache catalogue, lui, est conservé
    assert db.scalar(select(func.count()).select_from(Episode)) == 4
    assert client.delete(f"/series/{REF_SERIE}/suivre",
                         headers=_entete(jeton)).status_code == 404
