# tests/test_decouverte.py
from services import decouverte_service
from tests.faux_tmdb import REF_FILM, REF_SERIE


def _entetes(jeton):
    return {"Authorization": f"Bearer {jeton}"}


def test_feed_extraits_liste_series_et_films(client, jeton):
    decouverte_service.vider_cache()
    reponse = client.get("/decouverte/extraits", headers=_entetes(jeton))
    assert reponse.status_code == 200
    items = reponse.json()

    # les tendances de test = 1 série + 1 film + 1 personne (ignorée)
    refs = {(i["type"], i["reference_tmdb"]) for i in items}
    assert refs == {("serie", REF_SERIE), ("film", REF_FILM)}


def test_feed_choisit_le_trailer_youtube_vf(client, jeton):
    decouverte_service.vider_cache()
    items = client.get("/decouverte/extraits", headers=_entetes(jeton)).json()
    # Trailer VF YouTube préféré au Teaser EN et à la vidéo Vimeo
    assert all(i["cle_youtube"] == "cle_fr" for i in items)


def test_feed_extraits_exige_authentification(client):
    decouverte_service.vider_cache()
    assert client.get("/decouverte/extraits").status_code == 401


def test_selection_ignore_les_videos_non_youtube():
    videos = [
        {"site": "Vimeo", "key": "v1", "type": "Trailer", "official": True},
        {"site": "YouTube", "key": "y1", "type": "Clip", "official": False},
    ]
    assert decouverte_service._meilleure_cle_youtube(videos) == "y1"
    assert decouverte_service._meilleure_cle_youtube([]) is None
