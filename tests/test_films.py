# tests/test_films.py
from sqlalchemy import select

from models import SuivreFilm
from tests.faux_tmdb import REF_FILM


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


def test_etat_film_pas_vu(client, jeton):
    # film jamais vu (pas encore en cache) → deja_vu false
    reponse = client.get(f"/films/{REF_FILM}/vu", headers=_entete(jeton))
    assert reponse.status_code == 200
    assert reponse.json() == {"deja_vu": False, "nombre_visionnages": 0,
                              "dans_a_voir": False}


def test_etat_film_vu(client, jeton):
    client.post(f"/films/{REF_FILM}/vu", headers=_entete(jeton))
    client.post(f"/films/{REF_FILM}/vu", headers=_entete(jeton))
    reponse = client.get(f"/films/{REF_FILM}/vu", headers=_entete(jeton))
    assert reponse.json() == {"deja_vu": True, "nombre_visionnages": 2,
                              "dans_a_voir": False}


def test_etat_film_sans_jeton(client):
    assert client.get(f"/films/{REF_FILM}/vu").status_code == 401


# --- État du bouton « À voir plus tard » ---

def test_etat_signale_le_film_mis_de_cote(client, jeton):
    """Sans cette information, le bouton ne pouvait pas refléter son état."""
    avant = client.get(f"/films/{REF_FILM}/vu", headers=_entete(jeton)).json()
    assert avant["dans_a_voir"] is False

    client.post(f"/films/{REF_FILM}/suivre", headers=_entete(jeton),
                json={"statut": "a_voir"})
    apres = client.get(f"/films/{REF_FILM}/vu", headers=_entete(jeton)).json()
    assert apres["dans_a_voir"] is True


def test_retirer_de_la_liste_remet_le_bouton_a_zero(client, jeton):
    """Un clic malencontreux doit pouvoir se défaire."""
    client.post(f"/films/{REF_FILM}/suivre", headers=_entete(jeton),
                json={"statut": "a_voir"})
    assert client.delete(f"/films/{REF_FILM}/suivre",
                         headers=_entete(jeton)).status_code == 204
    etat = client.get(f"/films/{REF_FILM}/vu", headers=_entete(jeton)).json()
    assert etat["dans_a_voir"] is False


def test_marquer_vu_sort_le_film_de_la_liste_a_voir(client, jeton):
    """Un film qu'on vient de voir n'est plus « à voir »."""
    client.post(f"/films/{REF_FILM}/suivre", headers=_entete(jeton),
                json={"statut": "a_voir"})
    client.post(f"/films/{REF_FILM}/vu", headers=_entete(jeton))
    etat = client.get(f"/films/{REF_FILM}/vu", headers=_entete(jeton)).json()
    assert etat["deja_vu"] is True
    assert etat["dans_a_voir"] is False
