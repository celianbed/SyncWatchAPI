# tests/test_taches.py
from datetime import date

import pytest
from sqlalchemy import select

from core.config import settings
from models import Episode
from tests import faux_tmdb
from tests.faux_tmdb import REF_SERIE


def _entete(jeton):
    return {"Authorization": f"Bearer {jeton}"}


@pytest.fixture()
def secret_configure(monkeypatch):
    monkeypatch.setattr(settings, "CRON_SECRET", "secret-de-test")
    return {"X-Cron-Secret": "secret-de-test"}


def test_secret_non_configure(client, monkeypatch):
    monkeypatch.setattr(settings, "CRON_SECRET", "")
    reponse = client.post("/taches/scan-diffusions",
                          headers={"X-Cron-Secret": "peu-importe"})
    assert reponse.status_code == 503


def test_mauvais_secret(client, secret_configure):
    assert client.post("/taches/scan-diffusions",
                       headers={"X-Cron-Secret": "faux"}).status_code == 403
    assert client.post("/taches/scan-diffusions").status_code == 403


def test_pipeline_complet(client, jeton, db, secret_configure, monkeypatch):
    """TMDB annonce S02E02 pour aujourd'hui : la resync met le cache à jour,
    le scan crée la notification."""
    client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton))
    client.post("/appareils", headers=_entete(jeton),
                json={"jeton_notif": "fcm-1", "plateforme": "android"})
    # dans le cache, S02E02 n'a pas de date ; côté TMDB elle vient de tomber
    monkeypatch.setitem(faux_tmdb.SAISONS[2]["episodes"][1],
                        "air_date", date.today().isoformat())

    reponse = client.post("/taches/scan-diffusions", headers=secret_configure)
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["series_resynchronisees"] == 1
    assert corps["notifications_creees"] == 1

    # le cache reflète bien la nouvelle date
    episode = db.scalar(select(Episode).where(Episode.reference_tmdb == 2002))
    assert episode.date_diffusion == date.today()

    notifications = client.get("/notifications", headers=_entete(jeton)).json()
    assert len(notifications) == 1
    assert "S02E02" in notifications[0]["contenu"]

    # rejouer le pipeline le même jour ne crée pas de doublon
    corps = client.post("/taches/scan-diffusions", headers=secret_configure).json()
    assert corps["notifications_creees"] == 0


def test_sans_serie_suivie(client, secret_configure):
    corps = client.post("/taches/scan-diffusions", headers=secret_configure).json()
    assert corps == {"series_resynchronisees": 0, "notifications_creees": 0}
