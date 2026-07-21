# tests/conftest.py
import sys
from pathlib import Path

# racine du dépôt, pour que les imports absolus (core, db, models, ...) fonctionnent
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from api.dependances import client_tmdb, envoyeur_mail
from core.config import settings

settings.NOTIFICATIONS_PLANIFIEES = False  # pas de job APScheduler pendant les tests

from db.database import Base, get_db  # noqa: E402
from main import app  # noqa: E402
from models import Utilisateur  # noqa: E402
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
def aujourdhui(db):
    """Date du jour selon Postgres (même source que les requêtes SQL) — évite les
    décalages avec l'heure locale, donc des tests non flaky quel que soit le fuseau."""
    return db.scalar(select(func.current_date()))


@pytest.fixture()
def tmdb_faux():
    """Doublure du client TMDB : réponses figées, aucun appel réseau."""
    return FauxClientTMDB()


class EnvoyeurMemoire:
    """Doublure de l'envoyeur d'email : capture les messages au lieu de les envoyer."""

    def __init__(self):
        self.messages = []  # liste de (destinataire, sujet, corps_texte, corps_html)

    def envoyer(self, destinataire, sujet, corps_texte, corps_html=None):
        self.messages.append((destinataire, sujet, corps_texte, corps_html))


@pytest.fixture()
def envoyeur():
    """Envoyeur d'email en mémoire, exposé pour inspecter les mails de vérification."""
    return EnvoyeurMemoire()


@pytest.fixture()
def client(db, tmdb_faux, envoyeur):
    """Client HTTP de test branché sur la session transactionnelle ci-dessus."""
    def _get_db_test():
        yield db

    app.dependency_overrides[get_db] = _get_db_test
    app.dependency_overrides[client_tmdb] = lambda: tmdb_faux
    app.dependency_overrides[envoyeur_mail] = lambda: envoyeur
    with TestClient(app) as client_test:
        yield client_test
    app.dependency_overrides.clear()


DONNEES_INSCRIPTION = {
    "adresse_mail": "celian@example.com",
    "pseudo": "celian",
    "mot_de_passe": "motdepasse123",
}


@pytest.fixture()
def inscrire(client, db):
    """Factory : inscrit un utilisateur (par défaut DONNEES_INSCRIPTION) et renvoie la réponse.

    Marque le compte comme vérifié par défaut (la plupart des tests veulent un
    utilisateur exploitable) ; passer `verifier=False` pour tester le flux de
    confirmation d'adresse mail.
    """
    def _inscrire(verifier=True, **surcharges):
        reponse = client.post("/utilisateurs", json={**DONNEES_INSCRIPTION, **surcharges})
        if verifier and reponse.status_code == 201:
            utilisateur = db.get(Utilisateur, reponse.json()["id_utilisateur"])
            utilisateur.est_verifie = True
            db.commit()
        return reponse
    return _inscrire


@pytest.fixture()
def jeton(client, inscrire):
    """Utilisateur inscrit + connecté : renvoie son jeton d'accès."""
    inscrire()
    reponse = client.post("/auth/connexion", data={
        "username": DONNEES_INSCRIPTION["pseudo"],
        "password": DONNEES_INSCRIPTION["mot_de_passe"]})
    return reponse.json()["access_token"]
