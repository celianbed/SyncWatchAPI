# tests/test_decouverte.py
from services import decouverte_service
from tests.faux_tmdb import REF_FILM, REF_SERIE


def _entetes(jeton):
    return {"Authorization": f"Bearer {jeton}"}


def test_feed_extraits_liste_series_et_films(client, jeton):
    reponse = client.get("/decouverte/extraits", headers=_entetes(jeton))
    assert reponse.status_code == 200
    items = reponse.json()

    # les tendances de test = 1 série + 1 film + 1 personne (ignorée)
    refs = {(i["type"], i["reference_tmdb"]) for i in items}
    assert refs == {("serie", REF_SERIE), ("film", REF_FILM)}


def test_feed_choisit_le_trailer_youtube_vf(client, jeton):
    items = client.get("/decouverte/extraits", headers=_entetes(jeton)).json()
    # Trailer VF YouTube préféré au Teaser EN et à la vidéo Vimeo
    assert all(i["cle_youtube"] == "cle_fr" for i in items)


def test_feed_extraits_exige_authentification(client):
    assert client.get("/decouverte/extraits").status_code == 401


def test_candidats_classent_et_ignorent_non_youtube():
    videos = [
        {"site": "Vimeo", "key": "v1", "type": "Trailer", "official": True},
        {"site": "YouTube", "key": "y1", "type": "Clip", "official": False},
        {"site": "YouTube", "key": "y2", "type": "Trailer", "official": True},
    ]
    # Trailer officiel (y2) avant Clip (y1) ; Vimeo exclu
    assert decouverte_service.candidats_youtube(videos) == ["y2", "y1"]
    assert decouverte_service.candidats_youtube([]) == []


def test_parser_integrables_ne_garde_que_public_et_embeddable():
    items = [
        {"id": "a", "status": {"embeddable": True, "privacyStatus": "public"}},
        {"id": "b", "status": {"embeddable": False, "privacyStatus": "public"}},
        {"id": "c", "status": {"embeddable": True, "privacyStatus": "unlisted"}},
    ]
    assert decouverte_service._parser_integrables(items) == {"a"}


def _entete(jeton):
    return {"Authorization": f"Bearer {jeton}"}


def test_le_feed_ecarte_ce_qu_on_suit_deja(client, jeton):
    """Un feed de découverte qui propose une série déjà suivie rate sa cible."""
    avant = client.get("/decouverte/extraits", headers=_entete(jeton)).json()
    refs_avant = {(e["type"], e["reference_tmdb"]) for e in avant}
    assert ("serie", REF_SERIE) in refs_avant

    client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton))

    apres = client.get("/decouverte/extraits", headers=_entete(jeton)).json()
    refs_apres = {(e["type"], e["reference_tmdb"]) for e in apres}
    assert ("serie", REF_SERIE) not in refs_apres


def test_le_filtrage_ne_vide_pas_le_cache_partage(client, jeton, inscrire, db):
    """Le filtrage a lieu après lecture du cache : ce que je suis ne doit pas
    disparaître du feed des autres."""
    from models import Utilisateur
    from sqlalchemy import select

    client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton))
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    jeton_bob = client.post("/auth/connexion",
                            data={"username": "bob", "password": "motdepasse123"}
                            ).json()["access_token"]
    assert db.scalar(select(Utilisateur.id_utilisateur).where(
        Utilisateur.pseudo == "bob")) is not None

    refs = {(e["type"], e["reference_tmdb"])
            for e in client.get("/decouverte/extraits",
                                headers=_entete(jeton_bob)).json()}
    assert ("serie", REF_SERIE) in refs
