# tests/conftest.py
import sys
from pathlib import Path

# racine du dépôt, pour que les imports absolus (core, db, models, ...) fonctionnent
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from api.dependances import client_tmdb
from core.config import settings

settings.NOTIFICATIONS_PLANIFIEES = False  # pas de job APScheduler pendant les tests

from db.database import Base, get_db  # noqa: E402
from main import app  # noqa: E402
from tests.faux_tmdb import FauxClientTMDB  # noqa: E402

# base de test dédiée : même serveur Postgres, nom suffixé _test
URL_TEST = make_url(settings.DATABASE_URL).set(database="sync_watch_test")


@pytest.fixture(scope="session")
def moteur():
    """Crée la base de test (si absente) et son schéma, détruit le schéma à la fin."""
    moteur_admin = create_engine(URL_TEST.set(database="postgres"),
                                 isolation_level="AUTOCOMMIT")
    with moteur_admin.connect() as connexion:
        existe = connexion.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :nom"),
            {"nom": URL_TEST.database}).scalar()
        if not existe:
            connexion.execute(text(f'CREATE DATABASE "{URL_TEST.database}"'))
    moteur_admin.dispose()

    moteur = create_engine(URL_TEST)
    Base.metadata.create_all(moteur)
    yield moteur
    Base.metadata.drop_all(moteur)
    moteur.dispose()


@pytest.fixture()
def db(moteur):
    """Session liée à une transaction annulée en fin de test : la base reste vierge."""
    connexion = moteur.connect()
    transaction = connexion.begin()
    session = Session(bind=connexion, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connexion.close()


@pytest.fixture()
def tmdb_faux():
    """Doublure du client TMDB : réponses figées, aucun appel réseau."""
    return FauxClientTMDB()


@pytest.fixture()
def client(db, tmdb_faux):
    """Client HTTP de test branché sur la session transactionnelle ci-dessus."""
    def _get_db_test():
        yield db

    app.dependency_overrides[get_db] = _get_db_test
    app.dependency_overrides[client_tmdb] = lambda: tmdb_faux
    with TestClient(app) as client_test:
        yield client_test
    app.dependency_overrides.clear()


DONNEES_INSCRIPTION = {
    "adresse_mail": "celian@example.com",
    "pseudo": "celian",
    "mot_de_passe": "motdepasse123",
}


@pytest.fixture()
def inscrire(client):
    """Factory : inscrit un utilisateur (par défaut DONNEES_INSCRIPTION) et renvoie la réponse."""
    def _inscrire(**surcharges):
        return client.post("/utilisateurs", json={**DONNEES_INSCRIPTION, **surcharges})
    return _inscrire


@pytest.fixture()
def jeton(client, inscrire):
    """Utilisateur inscrit + connecté : renvoie son jeton d'accès."""
    inscrire()
    reponse = client.post("/auth/connexion", data={
        "username": DONNEES_INSCRIPTION["pseudo"],
        "password": DONNEES_INSCRIPTION["mot_de_passe"]})
    return reponse.json()["access_token"]
