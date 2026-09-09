# tests/test_avis.py
import pytest
from sqlalchemy import select

from models import Episode, Utilisateur
from tests.faux_tmdb import REF_FILM, REF_SERIE


def _entete(jeton):
    return {"Authorization": f"Bearer {jeton}"}


@pytest.fixture()
def cibles(client, jeton, db):
    """Série suivie + film en cache : renvoie des ids internes valides pour un avis."""
    id_serie = client.post(f"/series/{REF_SERIE}/suivre",
                           headers=_entete(jeton)).json()["id_serie"]
    id_film = client.get(f"/films/{REF_FILM}",
                         headers=_entete(jeton)).json()["id_film"]
    id_episode = db.scalar(select(Episode.id_episode).order_by(Episode.id_episode))
    return {"id_serie": id_serie, "id_film": id_film, "id_episode": id_episode}


@pytest.fixture()
def jeton2(client, inscrire):
    inscrire(adresse_mail="autre@example.com", pseudo="autre")
    reponse = client.post("/auth/connexion",
                          data={"username": "autre", "password": "motdepasse123"})
    return reponse.json()["access_token"]


def test_creer_avis_serie(client, jeton, cibles):
    reponse = client.post("/avis", headers=_entete(jeton),
                          json={"id_serie": cibles["id_serie"], "note": 8,
                                "commentaire": "Très bonne série."})
    assert reponse.status_code == 201
    corps = reponse.json()
    assert corps["note"] == 8
    assert corps["utilisateur"]["pseudo"] == "celian"
    assert corps["id_film"] is None
    assert corps["date_modification"] is None


def test_creer_avis_episode_note_seule(client, jeton, cibles):
    reponse = client.post("/avis", headers=_entete(jeton),
                          json={"id_episode": cibles["id_episode"], "note": 6})
    assert reponse.status_code == 201


def test_arc_exclusif_deux_cibles(client, jeton, cibles):
    reponse = client.post("/avis", headers=_entete(jeton),
                          json={"id_serie": cibles["id_serie"],
                                "id_film": cibles["id_film"], "note": 5})
    assert reponse.status_code == 422


def test_arc_exclusif_aucune_cible(client, jeton):
    assert client.post("/avis", headers=_entete(jeton),
                       json={"note": 5}).status_code == 422


def test_ni_note_ni_commentaire(client, jeton, cibles):
    reponse = client.post("/avis", headers=_entete(jeton),
                          json={"id_serie": cibles["id_serie"], "commentaire": "   "})
    assert reponse.status_code == 422


def test_note_hors_bornes(client, jeton, cibles):
    for note in (0, 11):
        reponse = client.post("/avis", headers=_entete(jeton),
                              json={"id_serie": cibles["id_serie"], "note": note})
        assert reponse.status_code == 422


def test_cible_inexistante(client, jeton):
    reponse = client.post("/avis", headers=_entete(jeton),
                          json={"id_serie": 999999, "note": 5})
    assert reponse.status_code == 404


def test_creer_sans_jeton(client):
    assert client.post("/avis", json={"id_serie": 1, "note": 5}).status_code == 401


def test_lister_par_cible(client, jeton, jeton2, cibles):
    client.post("/avis", headers=_entete(jeton),
                json={"id_serie": cibles["id_serie"], "note": 8})
    client.post("/avis", headers=_entete(jeton2),
                json={"id_serie": cibles["id_serie"], "note": 4})
    client.post("/avis", headers=_entete(jeton),
                json={"id_film": cibles["id_film"], "note": 9})

    reponse = client.get("/avis", headers=_entete(jeton),
                         params={"id_serie": cibles["id_serie"]})
    assert reponse.status_code == 200
    assert len(reponse.json()) == 2
    assert {a["utilisateur"]["pseudo"] for a in reponse.json()} == {"celian", "autre"}


def test_lister_filtre_obligatoire(client, jeton, cibles):
    assert client.get("/avis", headers=_entete(jeton)).status_code == 422
    assert client.get("/avis", headers=_entete(jeton),
                      params={"id_serie": cibles["id_serie"],
                              "id_film": cibles["id_film"]}).status_code == 422


def test_lecture_des_avis_reservee_aux_connectes(client, jeton, cibles):
    """Sans jeton, les identifiants étant séquentiels, on aspirerait tous les avis
    et les pseudos de leurs auteurs à coups de curl."""
    id_avis = client.post("/avis", headers=_entete(jeton),
                          json={"id_serie": cibles["id_serie"], "note": 8}).json()["id_avis"]

    assert client.get("/avis", params={"id_serie": cibles["id_serie"]}).status_code == 401
    assert client.get(f"/avis/{id_avis}").status_code == 401
    # avec un jeton, la lecture reste possible
    assert client.get(f"/avis/{id_avis}", headers=_entete(jeton)).status_code == 200


def test_mes_avis(client, jeton, jeton2, cibles):
    client.post("/avis", headers=_entete(jeton),
                json={"id_serie": cibles["id_serie"], "note": 8})
    client.post("/avis", headers=_entete(jeton2),
                json={"id_serie": cibles["id_serie"], "note": 4})

    miens = client.get("/avis/moi", headers=_entete(jeton)).json()
    assert len(miens) == 1
    assert miens[0]["note"] == 8


def test_modifier_avis(client, jeton, cibles):
    id_avis = client.post("/avis", headers=_entete(jeton),
                          json={"id_serie": cibles["id_serie"], "note": 8,
                                "commentaire": "Bien."}).json()["id_avis"]
    reponse = client.patch(f"/avis/{id_avis}", headers=_entete(jeton), json={"note": 9})
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["note"] == 9
    assert corps["commentaire"] == "Bien."  # champ non fourni : inchangé
    assert corps["date_modification"] is not None


def test_modifier_ne_peut_pas_tout_vider(client, jeton, cibles):
    id_avis = client.post("/avis", headers=_entete(jeton),
                          json={"id_serie": cibles["id_serie"],
                                "note": 8}).json()["id_avis"]
    reponse = client.patch(f"/avis/{id_avis}", headers=_entete(jeton),
                           json={"note": None})
    assert reponse.status_code == 422


def test_modifier_avis_dautrui(client, jeton, jeton2, cibles):
    id_avis = client.post("/avis", headers=_entete(jeton),
                          json={"id_serie": cibles["id_serie"],
                                "note": 8}).json()["id_avis"]
    reponse = client.patch(f"/avis/{id_avis}", headers=_entete(jeton2), json={"note": 1})
    # 404 (et non 403) : ne pas révéler l'existence de l'avis d'autrui
    assert reponse.status_code == 404


def test_supprimer_avis(client, jeton, cibles):
    id_avis = client.post("/avis", headers=_entete(jeton),
                          json={"id_serie": cibles["id_serie"],
                                "note": 8}).json()["id_avis"]
    assert client.delete(f"/avis/{id_avis}", headers=_entete(jeton)).status_code == 204
    assert client.get(f"/avis/{id_avis}", headers=_entete(jeton)).status_code == 404


def test_supprimer_avis_dautrui(client, jeton, jeton2, cibles):
    id_avis = client.post("/avis", headers=_entete(jeton),
                          json={"id_serie": cibles["id_serie"],
                                "note": 8}).json()["id_avis"]
    assert client.delete(f"/avis/{id_avis}", headers=_entete(jeton2)).status_code == 404


def _voir(client, jeton, ids_episodes):
    for id_episode in ids_episodes:
        client.post(f"/episodes/{id_episode}/vu", headers=_entete(jeton))


@pytest.fixture()
def duo(client, db, jeton, jeton2, cibles):
    """Je suis « autre », et la série est en cache : renvoie de quoi doser
    la progression de chacun."""
    id_autre = db.scalar(select(Utilisateur.id_utilisateur).where(
        Utilisateur.pseudo == "autre"))
    client.post(f"/utilisateurs/{id_autre}/abonner", headers=_entete(jeton))
    saisons = client.get(f"/series/{REF_SERIE}/saisons",
                         headers=_entete(jeton)).json()
    episodes = [e["id_episode"] for s in saisons for e in s["episodes"]]
    return {"episodes": episodes, "id_serie": cibles["id_serie"],
            "id_film": cibles["id_film"]}


def test_avis_dun_ami_plus_avance_est_masque(client, jeton, jeton2, duo):
    """Le seul endroit d'où viennent les spoilers entre amis : l'avis de série
    d'une personne qui a vu plus d'épisodes que vous."""
    _voir(client, jeton2, duo["episodes"])      # « autre » a tout vu
    _voir(client, jeton, duo["episodes"][:1])   # moi, un seul épisode

    client.post("/avis", headers=_entete(jeton2),
                json={"id_serie": duo["id_serie"], "note": 9,
                      "commentaire": "La fin est incroyable."})

    avis = client.get("/avis/abonnements", headers=_entete(jeton),
                      params={"id_serie": duo["id_serie"]}).json()
    assert len(avis) == 1
    assert avis[0]["masque"] is True
    assert avis[0]["commentaire"] is None
    assert avis[0]["note"] == 9, "un chiffre ne divulgue rien : la note reste"


def test_avis_dun_ami_moins_avance_reste_lisible(client, jeton, jeton2, duo):
    _voir(client, jeton2, duo["episodes"][:1])
    _voir(client, jeton, duo["episodes"])

    client.post("/avis", headers=_entete(jeton2),
                json={"id_serie": duo["id_serie"], "note": 7,
                      "commentaire": "Bon début."})

    avis = client.get("/avis/abonnements", headers=_entete(jeton),
                      params={"id_serie": duo["id_serie"]}).json()
    assert avis[0]["masque"] is False
    assert avis[0]["commentaire"] == "Bon début."


def test_avis_sans_commentaire_nest_pas_dit_masque(client, jeton, jeton2, duo):
    # une note seule n'a rien à cacher : la signaler masquée serait mensonger
    _voir(client, jeton2, duo["episodes"])

    client.post("/avis", headers=_entete(jeton2),
                json={"id_serie": duo["id_serie"], "note": 9})

    avis = client.get("/avis/abonnements", headers=_entete(jeton),
                      params={"id_serie": duo["id_serie"]}).json()
    assert avis[0]["masque"] is False


def test_avis_de_film_jamais_masque(client, jeton, jeton2, duo):
    # un film se voit d'un bloc : « plus avancé » n'a pas de sens
    client.post("/avis", headers=_entete(jeton2),
                json={"id_film": duo["id_film"], "note": 8,
                      "commentaire": "Excellent."})

    avis = client.get("/avis/abonnements", headers=_entete(jeton),
                      params={"id_film": duo["id_film"]}).json()
    assert avis[0]["masque"] is False
    assert avis[0]["commentaire"] == "Excellent."


def test_commentaire_trop_long_refuse(client, jeton, cibles):
    # la colonne est un Text sans limite : sans borne au schéma, rien
    # n'empêchait de déposer plusieurs mégaoctets
    reponse = client.post("/avis", headers=_entete(jeton),
                          json={"id_serie": cibles["id_serie"],
                                "commentaire": "a" * 2001})
    assert reponse.status_code == 422
    assert "2000" in reponse.json()["detail"]


def test_commentaire_a_la_limite_accepte(client, jeton, cibles):
    reponse = client.post("/avis", headers=_entete(jeton),
                          json={"id_serie": cibles["id_serie"],
                                "commentaire": "a" * 2000})
    assert reponse.status_code == 201
