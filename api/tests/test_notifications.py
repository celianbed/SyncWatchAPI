# api/tests/test_notifications.py
from datetime import date

import pytest
from sqlalchemy import func, select

from api.models import Appareil, Episode
from api.services import notification_service
from api.tests.faux_tmdb import REF_SERIE


def _entete(jeton):
    return {"Authorization": f"Bearer {jeton}"}


class FauxPousseur:
    def __init__(self):
        self.envois = []

    def envoyer(self, jetons, titre, corps):
        self.envois.append((jetons, titre, corps))


@pytest.fixture()
def diffusion_du_jour(client, jeton, db):
    """Série suivie + appareil enregistré + un épisode diffusé aujourd'hui (S02E02)."""
    client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton))
    client.post("/appareils", headers=_entete(jeton),
                json={"jeton_notif": "fcm-jeton-1", "plateforme": "android"})
    episode = db.scalar(select(Episode).where(Episode.reference_tmdb == 2002))
    episode.date_diffusion = date.today()
    db.commit()
    return episode


def test_enregistrer_appareil(client, jeton):
    reponse = client.post("/appareils", headers=_entete(jeton),
                          json={"jeton_notif": "fcm-abc", "plateforme": "android"})
    assert reponse.status_code == 201
    assert reponse.json()["plateforme"] == "android"


def test_meme_jeton_reattribue(client, jeton, inscrire, db):
    client.post("/appareils", headers=_entete(jeton),
                json={"jeton_notif": "fcm-partage", "plateforme": "android"})

    inscrire(adresse_mail="autre@example.com", pseudo="autre")
    jeton2 = client.post("/auth/connexion", data={
        "username": "autre", "password": "motdepasse123"}).json()["access_token"]
    client.post("/appareils", headers=_entete(jeton2),
                json={"jeton_notif": "fcm-partage", "plateforme": "android"})

    # un seul appareil, rattaché au dernier compte connecté
    assert db.scalar(select(func.count()).select_from(Appareil)) == 1
    appareil = db.scalar(select(Appareil))
    assert appareil.utilisateur.pseudo == "autre"


def test_plateforme_invalide(client, jeton):
    reponse = client.post("/appareils", headers=_entete(jeton),
                          json={"jeton_notif": "x", "plateforme": "windows"})
    assert reponse.status_code == 422


def test_supprimer_appareil(client, jeton):
    id_appareil = client.post("/appareils", headers=_entete(jeton),
                              json={"jeton_notif": "fcm-abc",
                                    "plateforme": "ios"}).json()["id_appareil"]
    assert client.delete(f"/appareils/{id_appareil}",
                         headers=_entete(jeton)).status_code == 204
    assert client.delete(f"/appareils/{id_appareil}",
                         headers=_entete(jeton)).status_code == 404


def test_scan_cree_notification_et_pousse(client, jeton, db, diffusion_du_jour):
    pousseur = FauxPousseur()
    creees = notification_service.scanner_diffusions_du_jour(db, pousseur)
    assert creees == 1

    jetons, _, corps = pousseur.envois[0]
    assert jetons == ["fcm-jeton-1"]
    assert "Les Chroniques" in corps and "S02E02" in corps

    notifications = client.get("/notifications", headers=_entete(jeton)).json()
    assert len(notifications) == 1
    assert notifications[0]["type"] == "nouvel_episode"
    assert notifications[0]["lue"] is False
    assert notifications[0]["id_episode"] == diffusion_du_jour.id_episode


def test_scan_idempotent(client, jeton, db, diffusion_du_jour):
    assert notification_service.scanner_diffusions_du_jour(db) == 1
    assert notification_service.scanner_diffusions_du_jour(db) == 0
    assert len(client.get("/notifications", headers=_entete(jeton)).json()) == 1


def test_scan_ignore_suivi_abandonne(client, jeton, db, diffusion_du_jour):
    client.patch(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton),
                 json={"statut_suivi": "abandonnee"})
    assert notification_service.scanner_diffusions_du_jour(db) == 0


def test_marquer_lue_et_filtrer(client, jeton, db, diffusion_du_jour):
    notification_service.scanner_diffusions_du_jour(db)
    id_notification = client.get("/notifications",
                                 headers=_entete(jeton)).json()[0]["id_notification"]

    reponse = client.patch(f"/notifications/{id_notification}/lue", headers=_entete(jeton))
    assert reponse.status_code == 200
    assert reponse.json()["lue"] is True
    assert client.get("/notifications", params={"lue": False},
                      headers=_entete(jeton)).json() == []


def test_notification_dautrui_introuvable(client, jeton, inscrire, db, diffusion_du_jour):
    notification_service.scanner_diffusions_du_jour(db)
    id_notification = client.get("/notifications",
                                 headers=_entete(jeton)).json()[0]["id_notification"]

    inscrire(adresse_mail="autre@example.com", pseudo="autre")
    jeton2 = client.post("/auth/connexion", data={
        "username": "autre", "password": "motdepasse123"}).json()["access_token"]
    assert client.patch(f"/notifications/{id_notification}/lue",
                        headers=_entete(jeton2)).status_code == 404


def test_notifications_sans_jeton(client):
    assert client.get("/notifications").status_code == 401
    assert client.post("/appareils",
                       json={"jeton_notif": "x", "plateforme": "web"}).status_code == 401
