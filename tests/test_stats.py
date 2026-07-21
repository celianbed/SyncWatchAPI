# tests/test_stats.py
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from models import Saison
from tests.faux_tmdb import REF_FILM, REF_SERIE


def _entete(jeton):
    return {"Authorization": f"Bearer {jeton}"}


@pytest.fixture()
def historique_rempli(client, jeton, db):
    """Saison 1 vue (52 + 48 min) et un film vu deux fois (139 min)."""
    client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton))
    id_saison_1 = db.scalar(select(Saison.id_saison).where(Saison.num_saison == 1))
    client.post(f"/saisons/{id_saison_1}/vu", headers=_entete(jeton))
    client.post(f"/films/{REF_FILM}/vu", headers=_entete(jeton))
    client.post(f"/films/{REF_FILM}/vu", headers=_entete(jeton))


def test_stats_globales(client, jeton, historique_rempli):
    stats = client.get("/stats", headers=_entete(jeton)).json()
    assert stats["episodes_vus"] == 2
    assert stats["minutes_episodes"] == 52 + 48
    assert stats["films_vus"] == 1  # revu, mais un seul film distinct
    assert stats["minutes_films"] == 139 * 2  # chaque visionnage compte
    assert stats["minutes_totales"] == 100 + 278
    assert stats["series_suivies"] == 1
    assert stats["series_terminees"] == 0


def test_series_terminees(client, jeton, historique_rempli):
    client.patch(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton),
                 json={"statut_suivi": "terminee"})
    stats = client.get("/stats", headers=_entete(jeton)).json()
    assert stats["series_terminees"] == 1


def test_stats_compte_vierge(client, jeton):
    stats = client.get("/stats", headers=_entete(jeton)).json()
    assert stats == {"episodes_vus": 0, "films_vus": 0, "series_suivies": 0,
                     "series_terminees": 0, "minutes_episodes": 0,
                     "minutes_films": 0, "minutes_totales": 0}


def test_historique_par_jour(client, jeton, historique_rempli):
    tranches = client.get("/stats/historique", params={"periode": "jour"},
                          headers=_entete(jeton)).json()
    assert len(tranches) == 1  # tout vu aujourd'hui (épisodes + films même jour)
    assert tranches[0]["episodes_vus"] == 2
    assert tranches[0]["films_vus"] == 2       # 2 visionnages du film
    assert tranches[0]["minutes"] == 100 + 278  # épisodes (52+48) + films (139×2)


def test_historique_bornes(client, jeton, historique_rempli):
    hier = (date.today() - timedelta(days=1)).isoformat()
    tranches = client.get("/stats/historique", params={"periode": "jour", "fin": hier},
                          headers=_entete(jeton)).json()
    assert tranches == []


def test_stats_sans_jeton(client):
    assert client.get("/stats").status_code == 401
