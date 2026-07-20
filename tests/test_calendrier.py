# tests/test_calendrier.py
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from models import Episode
from tests.faux_tmdb import REF_SERIE


def _entete(jeton):
    return {"Authorization": f"Bearer {jeton}"}


@pytest.fixture()
def diffusion_a_venir(client, jeton, db):
    """Série suivie + S02E02 diffusé dans 3 jours (les autres épisodes sont passés)."""
    client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton))
    episode = db.scalar(select(Episode).where(Episode.reference_tmdb == 2002))
    episode.date_diffusion = date.today() + timedelta(days=3)
    db.commit()
    return episode


def test_calendrier_diffusion_a_venir(client, jeton, diffusion_a_venir):
    reponse = client.get("/calendrier", headers=_entete(jeton))
    assert reponse.status_code == 200
    entrees = reponse.json()

    # seul l'épisode à venir apparaît, pas les diffusions passées
    assert len(entrees) == 1
    assert entrees[0]["serie"]["titre"] == "Les Chroniques"
    assert entrees[0]["episode"]["num_saison"] == 2
    assert entrees[0]["episode"]["num_episode"] == 2
    assert entrees[0]["episode"]["deja_diffuse"] is False
    assert entrees[0]["episode"]["date_diffusion"] == str(date.today() + timedelta(days=3))


def test_calendrier_fenetre_trop_courte(client, jeton, diffusion_a_venir):
    # l'épisode est à +3 jours : hors d'une fenêtre de 2 jours
    reponse = client.get("/calendrier", params={"jours": 2}, headers=_entete(jeton))
    assert reponse.status_code == 200
    assert reponse.json() == []


def test_calendrier_serie_non_suivie(client, jeton, db):
    # épisode à venir mais série jamais suivie : rien à afficher
    episode = db.scalar(select(Episode).where(Episode.reference_tmdb == 2002))
    if episode is not None:
        episode.date_diffusion = date.today() + timedelta(days=3)
        db.commit()
    reponse = client.get("/calendrier", headers=_entete(jeton))
    assert reponse.status_code == 200
    assert reponse.json() == []


def test_calendrier_suivi_abandonne(client, jeton, diffusion_a_venir):
    client.patch(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton),
                 json={"statut_suivi": "abandonnee"})
    assert client.get("/calendrier", headers=_entete(jeton)).json() == []


def test_calendrier_fenetre_invalide(client, jeton):
    assert client.get("/calendrier", params={"jours": 0},
                      headers=_entete(jeton)).status_code == 422
    assert client.get("/calendrier", params={"jours": 90},
                      headers=_entete(jeton)).status_code == 422


def test_calendrier_sans_jeton(client):
    assert client.get("/calendrier").status_code == 401
