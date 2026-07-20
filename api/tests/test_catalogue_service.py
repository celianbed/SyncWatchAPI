# api/tests/test_catalogue_service.py
import asyncio
from datetime import datetime, timedelta

from sqlalchemy import func, select

from api.models import Episode, Saison, Serie
from api.services import catalogue_service
from api.tests.faux_tmdb import REF_SERIE, SERIE_DETAIL, FauxClientTMDB


def test_upsert_deux_fois_une_seule_ligne(db):
    catalogue_service.upsert_serie(db, SERIE_DETAIL)
    catalogue_service.upsert_serie(db, {**SERIE_DETAIL, "name": "Titre corrigé"})

    series = db.scalars(select(Serie)).all()
    assert len(series) == 1
    assert series[0].titre == "Titre corrigé"
    assert {g.libelle for g in series[0].genres} == {"Drame", "Science-Fiction & Fantastique"}


def test_cache_frais_pas_de_nouvel_appel(db):
    faux = FauxClientTMDB()
    premiere = asyncio.run(catalogue_service.obtenir_serie(db, faux, REF_SERIE))
    seconde = asyncio.run(catalogue_service.obtenir_serie(db, faux, REF_SERIE))

    assert faux.compteurs["get_serie"] == 1
    assert seconde.id_serie == premiere.id_serie


def test_cache_perime_rafraichi(db):
    faux = FauxClientTMDB()
    serie = asyncio.run(catalogue_service.obtenir_serie(db, faux, REF_SERIE))
    serie.date_maj_cache = datetime.now() - timedelta(hours=999)
    db.commit()

    asyncio.run(catalogue_service.obtenir_serie(db, faux, REF_SERIE))
    assert faux.compteurs["get_serie"] == 2


def test_reference_inconnue(db):
    faux = FauxClientTMDB()
    assert asyncio.run(catalogue_service.obtenir_serie(db, faux, 999999)) is None


def test_synchronisation_saisons_episodes(db):
    faux = FauxClientTMDB()
    serie = asyncio.run(catalogue_service.obtenir_serie(db, faux, REF_SERIE))
    asyncio.run(catalogue_service.synchroniser_episodes(db, faux, serie))

    assert db.scalar(select(func.count()).select_from(Saison)) == 2
    assert db.scalar(select(func.count()).select_from(Episode)) == 4
    episode = db.scalar(select(Episode).where(Episode.reference_tmdb == 2002))
    assert episode.date_diffusion is None  # "" TMDB -> NULL


def test_synchronisation_idempotente(db):
    faux = FauxClientTMDB()
    serie = asyncio.run(catalogue_service.obtenir_serie(db, faux, REF_SERIE))
    asyncio.run(catalogue_service.synchroniser_episodes(db, faux, serie))
    asyncio.run(catalogue_service.synchroniser_episodes(db, faux, serie))

    assert db.scalar(select(func.count()).select_from(Saison)) == 2
    assert db.scalar(select(func.count()).select_from(Episode)) == 4
