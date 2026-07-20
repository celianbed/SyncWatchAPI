# api/tests/test_films.py
from sqlalchemy import select

from api.models import SuivreFilm
from api.tests.faux_tmdb import REF_FILM


def _entete(jeton):
    return {"Authorization": f"Bearer {jeton}"}


def test_fiche_film(client):
    reponse = client.get(f"/films/{REF_FILM}")
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["titre"] == "Le Grand Film"
    assert corps["duree"] == 139
    assert corps["date_sortie"] == "1999-10-15"
    assert {g["libelle"] for g in corps["genres"]} == {"Drame"}


def test_fiche_film_servie_du_cache(client, tmdb_faux):
    client.get(f"/films/{REF_FILM}")
    client.get(f"/films/{REF_FILM}")
    assert tmdb_faux.compteurs["get_film"] == 1


def test_fiche_film_inconnu(client):
    assert client.get("/films/999999").status_code == 404


def test_suivre_film(client, jeton):
    reponse = client.post(f"/films/{REF_FILM}/suivre", headers=_entete(jeton))
    assert reponse.status_code == 201
    corps = reponse.json()
    assert corps["statut"] == "a_voir"
    assert corps["favori"] is False


def test_suivre_film_deux_fois(client, jeton):
    client.post(f"/films/{REF_FILM}/suivre", headers=_entete(jeton))
    assert client.post(f"/films/{REF_FILM}/suivre",
                       headers=_entete(jeton)).status_code == 409


def test_ne_plus_suivre_film(client, jeton):
    client.post(f"/films/{REF_FILM}/suivre", headers=_entete(jeton))
    assert client.delete(f"/films/{REF_FILM}/suivre",
                         headers=_entete(jeton)).status_code == 204
    assert client.delete(f"/films/{REF_FILM}/suivre",
                         headers=_entete(jeton)).status_code == 404


def test_film_vu_plusieurs_fois(client, jeton):
    premier = client.post(f"/films/{REF_FILM}/vu", headers=_entete(jeton))
    second = client.post(f"/films/{REF_FILM}/vu", headers=_entete(jeton))
    assert premier.status_code == second.status_code == 201
    assert premier.json()["nombre_visionnages"] == 1
    assert second.json()["nombre_visionnages"] == 2


def test_film_vu_met_le_suivi_a_jour(client, jeton, db):
    client.post(f"/films/{REF_FILM}/suivre", headers=_entete(jeton))
    client.post(f"/films/{REF_FILM}/vu", headers=_entete(jeton))
    suivi = db.scalar(select(SuivreFilm))
    assert suivi.statut == "vu"


def test_film_vu_sans_jeton(client):
    assert client.post(f"/films/{REF_FILM}/vu").status_code == 401
