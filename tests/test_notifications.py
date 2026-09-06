# tests/test_notifications.py
import pytest
from sqlalchemy import func, select

from models import Appareil, Episode
from services import notification_service
from tests.faux_tmdb import REF_SERIE


def _entete(jeton):
    return {"Authorization": f"Bearer {jeton}"}


class FauxPousseur:
    """Doublure du canal push. `perimes` = jetons que le service déclarerait morts."""

    def __init__(self, perimes=()):
        self.envois = []
        self.perimes = list(perimes)

    def envoyer(self, jetons, titre, corps, donnees=None, badge=None):
        self.envois.append((jetons, titre, corps, donnees, badge))
        return [j for j in jetons if j in self.perimes]


@pytest.fixture()
def diffusion_du_jour(client, jeton, db, aujourdhui):
    """Série suivie + appareil enregistré + un épisode diffusé aujourd'hui (S02E02)."""
    client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton))
    client.post("/appareils", headers=_entete(jeton),
                json={"jeton_notif": "fcm-jeton-1", "plateforme": "android"})
    episode = db.scalar(select(Episode).where(Episode.reference_tmdb == 2002))
    episode.date_diffusion = aujourdhui  # date Postgres (voir fixture) → non flaky
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

    jetons, _, corps, donnees, badge = pousseur.envois[0]
    assert jetons == ["fcm-jeton-1"]
    assert "Les Chroniques" in corps and "S02E02" in corps
    # payload de navigation : ouvre la fiche série au tap
    assert donnees == {"reference_tmdb": REF_SERIE, "cible": "serie"}
    assert badge == 1  # pastille iOS = notifications non lues

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


def test_notification_porte_la_cible(client, jeton, db, diffusion_du_jour):
    # une notif d'épisode doit pointer vers la fiche série (reference_tmdb + cible)
    notification_service.scanner_diffusions_du_jour(db)
    notif = client.get("/notifications", headers=_entete(jeton)).json()[0]
    assert notif["cible"] == "serie"
    assert notif["reference_tmdb"] == REF_SERIE


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


def test_scan_retire_les_jetons_perimes(client, jeton, db, diffusion_du_jour):
    # FCM répond « jeton inconnu » (app désinstallée) : l'appareil doit disparaître
    pousseur = FauxPousseur(perimes=["fcm-jeton-1"])
    notification_service.scanner_diffusions_du_jour(db, pousseur)
    assert db.scalar(select(func.count()).select_from(Appareil)) == 0


def test_scan_garde_les_jetons_valides(client, jeton, db, diffusion_du_jour):
    notification_service.scanner_diffusions_du_jour(db, FauxPousseur())
    assert db.scalar(select(func.count()).select_from(Appareil)) == 1


def _creer_notifs(db, client, jeton, nombre):
    """N notifications système pour le compte courant, sans passer par le scan."""
    from models import Notification, Utilisateur
    from sqlalchemy import select as _select
    uid = db.scalar(_select(Utilisateur.id_utilisateur).where(
        Utilisateur.pseudo == "celian"))
    for i in range(nombre):
        db.add(Notification(id_utilisateur=uid, type="systeme", contenu=f"message {i}"))
    db.commit()


def test_liste_bornee_par_defaut(client, jeton, db):
    _creer_notifs(db, client, jeton, 60)
    assert len(client.get("/notifications", headers=_entete(jeton)).json()) == 50


def test_limite_ajustable_et_plafonnee(client, jeton, db):
    _creer_notifs(db, client, jeton, 60)
    assert len(client.get("/notifications", headers=_entete(jeton),
                          params={"limite": 10}).json()) == 10
    # au-delà du plafond, la requête est refusée plutôt que servie
    assert client.get("/notifications", headers=_entete(jeton),
                      params={"limite": 500}).status_code == 422


def test_compteur_non_lues_ignore_la_limite(client, jeton, db):
    """La pastille doit rester juste au-delà de la limite de la liste."""
    _creer_notifs(db, client, jeton, 60)
    reponse = client.get("/notifications/nombre-non-lues", headers=_entete(jeton))
    assert reponse.status_code == 200
    assert reponse.json()["nombre"] == 60


def test_compteur_suit_les_lectures(client, jeton, db, diffusion_du_jour):
    notification_service.scanner_diffusions_du_jour(db)
    notifs = client.get("/notifications", headers=_entete(jeton)).json()
    client.patch(f"/notifications/{notifs[0]['id_notification']}/lue",
                 headers=_entete(jeton))
    assert client.get("/notifications/nombre-non-lues",
                      headers=_entete(jeton)).json()["nombre"] == 0


def test_cible_resolue_pour_toute_la_liste(client, jeton, db, diffusion_du_jour):
    """La résolution par lot doit donner le même résultat que l'ancienne, une par une."""
    notification_service.scanner_diffusions_du_jour(db)
    _creer_notifs(db, client, jeton, 3)  # notifications sans cible, mélangées
    notifs = client.get("/notifications", headers=_entete(jeton)).json()

    avec_cible = [n for n in notifs if n["reference_tmdb"] is not None]
    assert len(avec_cible) == 1
    assert avec_cible[0]["cible"] == "serie"
    assert all(n["cible"] is None for n in notifs if n["reference_tmdb"] is None)


# --- Séries terminées : une nouvelle saison doit les réveiller ---

def _statut(client, jeton, statut):
    client.patch(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton),
                 json={"statut_suivi": statut})


def test_serie_terminee_notifiee_et_remise_en_cours(client, jeton, db,
                                                    diffusion_du_jour):
    """Une série finie ne l'est plus quand un épisode sort : sans ça, l'utilisateur
    n'apprenait jamais l'arrivée d'une nouvelle saison."""
    _statut(client, jeton, "terminee")

    assert notification_service.scanner_diffusions_du_jour(db) == 1

    notifs = client.get("/notifications", headers=_entete(jeton)).json()
    assert any(n["type"] == "nouvel_episode" for n in notifs)

    from models import Serie, SuivreSerie
    statut = db.scalar(
        select(SuivreSerie.statut_suivi)
        .join(Serie, Serie.id_serie == SuivreSerie.id_serie)
        .where(Serie.reference_tmdb == REF_SERIE))
    assert statut == "en_cours"


def test_serie_terminee_remonte_dans_l_accueil_apres_notification(
        client, jeton, db, diffusion_du_jour):
    """La notification doit mener quelque part : « terminée » est exclu de l'accueil."""
    _statut(client, jeton, "terminee")
    assert client.get("/accueil", headers=_entete(jeton)).json() == []

    notification_service.scanner_diffusions_du_jour(db)

    assert len(client.get("/accueil", headers=_entete(jeton)).json()) == 1


def test_serie_abandonnee_reste_silencieuse(client, jeton, db, diffusion_du_jour):
    """Un abandon est explicite : on ne revient pas dessus."""
    _statut(client, jeton, "abandonnee")
    assert notification_service.scanner_diffusions_du_jour(db) == 0


def test_serie_en_pause_nest_pas_notifiee(client, jeton, db, diffusion_du_jour):
    """Une mise en pause est un retrait volontaire, qu'on respecte."""
    _statut(client, jeton, "en_pause")
    assert notification_service.scanner_diffusions_du_jour(db) == 0
