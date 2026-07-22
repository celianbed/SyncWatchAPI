# tests/test_auth.py
import re
from datetime import datetime, timedelta, timezone

from jose import jwt
from sqlalchemy import select

from core.config import settings
from models import Utilisateur
from tests.conftest import DONNEES_INSCRIPTION


def se_connecter(client, username, password=DONNEES_INSCRIPTION["mot_de_passe"]):
    return client.post("/auth/connexion", data={"username": username, "password": password})


def jeton_du_dernier_mail(envoyeur):
    """Extrait le jeton de vérification du lien contenu dans le dernier mail envoyé."""
    _, _, corps_texte, _ = envoyeur.messages[-1]
    return re.search(r"jeton=([^\s&]+)", corps_texte).group(1)


def test_connexion_par_mail(client, inscrire):
    inscrire()
    reponse = se_connecter(client, DONNEES_INSCRIPTION["adresse_mail"])
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["token_type"] == "bearer"
    assert corps["access_token"]


def test_connexion_par_pseudo(client, inscrire):
    inscrire()
    assert se_connecter(client, DONNEES_INSCRIPTION["pseudo"]).status_code == 200


def test_mauvais_mot_de_passe(client, inscrire):
    inscrire()
    reponse = se_connecter(client, DONNEES_INSCRIPTION["pseudo"], "mauvais-mdp")
    assert reponse.status_code == 401


def test_compte_inconnu_meme_message(client, inscrire):
    """Le message ne doit pas révéler si le compte existe ou non."""
    inscrire()
    mauvais_mdp = se_connecter(client, DONNEES_INSCRIPTION["pseudo"], "mauvais-mdp")
    inconnu = se_connecter(client, "inconnu@example.com")
    assert inconnu.status_code == 401
    assert inconnu.json()["detail"] == mauvais_mdp.json()["detail"]


def test_compte_suspendu_refuse(client, inscrire, db):
    inscrire()
    utilisateur = db.scalar(select(Utilisateur).where(Utilisateur.pseudo == "celian"))
    utilisateur.statut_compte = "suspendu"
    db.commit()
    assert se_connecter(client, DONNEES_INSCRIPTION["pseudo"]).status_code == 403


def test_date_derniere_connexion_mise_a_jour(client, inscrire, db):
    inscrire()
    se_connecter(client, DONNEES_INSCRIPTION["pseudo"])
    utilisateur = db.scalar(select(Utilisateur).where(Utilisateur.pseudo == "celian"))
    db.refresh(utilisateur)
    assert utilisateur.date_derniere_connexion is not None


def test_moi_avec_jeton(client, jeton):
    reponse = client.get("/utilisateurs/moi", headers={"Authorization": f"Bearer {jeton}"})
    assert reponse.status_code == 200
    assert reponse.json()["pseudo"] == DONNEES_INSCRIPTION["pseudo"]


def test_moi_sans_jeton(client):
    assert client.get("/utilisateurs/moi").status_code == 401


def test_moi_jeton_bidon(client):
    reponse = client.get("/utilisateurs/moi",
                         headers={"Authorization": "Bearer n.importe.quoi"})
    assert reponse.status_code == 401


def test_moi_jeton_expire(client, inscrire):
    inscrire()
    jeton_expire = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.SECRET_KEY, algorithm=settings.ALGORITHME_JWT)
    reponse = client.get("/utilisateurs/moi",
                         headers={"Authorization": f"Bearer {jeton_expire}"})
    assert reponse.status_code == 401


def test_moi_compte_devenu_inactif(client, jeton, db):
    """Un jeton valide ne suffit pas si le compte a été suspendu entre-temps."""
    utilisateur = db.scalar(select(Utilisateur).where(
        Utilisateur.pseudo == DONNEES_INSCRIPTION["pseudo"]))
    utilisateur.statut_compte = "supprime"
    db.commit()
    reponse = client.get("/utilisateurs/moi", headers={"Authorization": f"Bearer {jeton}"})
    assert reponse.status_code == 401


# --- Vérification d'adresse mail ---

def test_inscription_envoie_mail_verification(client, inscrire, envoyeur):
    inscrire(verifier=False)
    assert len(envoyeur.messages) == 1
    destinataire, _, corps_texte, corps_html = envoyeur.messages[0]
    assert destinataire == DONNEES_INSCRIPTION["adresse_mail"]
    assert "/auth/verifier-email?jeton=" in corps_texte
    # l'email HTML contient un bouton pointant vers le lien de vérification
    assert corps_html is not None
    assert "Vérifier mon compte" in corps_html
    assert "/auth/verifier-email?jeton=" in corps_html


def test_connexion_refusee_si_non_verifie(client, inscrire):
    inscrire(verifier=False)
    reponse = se_connecter(client, DONNEES_INSCRIPTION["pseudo"])
    assert reponse.status_code == 403


def test_verifier_email_active_le_compte(client, inscrire, envoyeur):
    inscrire(verifier=False)
    jeton_verif = jeton_du_dernier_mail(envoyeur)

    reponse = client.get("/auth/verifier-email", params={"jeton": jeton_verif})
    assert reponse.status_code == 200
    # page HTML de confirmation
    assert "text/html" in reponse.headers["content-type"]
    assert "vérifiée" in reponse.text
    # le compte est désormais utilisable
    assert se_connecter(client, DONNEES_INSCRIPTION["pseudo"]).status_code == 200


def test_verifier_email_jeton_invalide(client):
    assert client.get("/auth/verifier-email", params={"jeton": "n.importe.quoi"}).status_code == 400


def test_verifier_email_refuse_un_jeton_dacces(client, jeton):
    """Un jeton d'accès (mauvais type) ne peut pas servir à vérifier un compte."""
    assert client.get("/auth/verifier-email", params={"jeton": jeton}).status_code == 400


def test_verifier_email_idempotent(client, inscrire, envoyeur):
    inscrire(verifier=False)
    jeton_verif = jeton_du_dernier_mail(envoyeur)
    assert client.get("/auth/verifier-email", params={"jeton": jeton_verif}).status_code == 200
    # rejouer le même lien ne provoque pas d'erreur (page de confirmation identique)
    reponse = client.get("/auth/verifier-email", params={"jeton": jeton_verif})
    assert reponse.status_code == 200
    assert "vérifiée" in reponse.text


def test_renvoyer_verification_envoie_un_nouveau_mail(client, inscrire, envoyeur):
    inscrire(verifier=False)
    envoyeur.messages.clear()
    reponse = client.post("/auth/renvoyer-verification",
                          json={"adresse_mail": DONNEES_INSCRIPTION["adresse_mail"]})
    assert reponse.status_code == 202
    assert len(envoyeur.messages) == 1


def test_renvoyer_verification_compte_inconnu_ne_revele_rien(client, envoyeur):
    reponse = client.post("/auth/renvoyer-verification",
                          json={"adresse_mail": "inconnu@example.com"})
    assert reponse.status_code == 202  # même réponse qu'un compte existant
    assert envoyeur.messages == []     # mais aucun mail envoyé


def test_renvoyer_verification_deja_verifie_pas_de_mail(client, inscrire, envoyeur):
    inscrire()  # vérifié par défaut
    envoyeur.messages.clear()
    reponse = client.post("/auth/renvoyer-verification",
                          json={"adresse_mail": DONNEES_INSCRIPTION["adresse_mail"]})
    assert reponse.status_code == 202
    assert envoyeur.messages == []


# --- Mot de passe oublié / réinitialisation ---

def demander_reset(client, mail=DONNEES_INSCRIPTION["adresse_mail"]):
    return client.post("/auth/mot-de-passe-oublie", json={"adresse_mail": mail})


def test_mot_de_passe_oublie_envoie_mail(client, inscrire, envoyeur):
    inscrire()
    envoyeur.messages.clear()
    reponse = demander_reset(client)
    assert reponse.status_code == 202
    assert len(envoyeur.messages) == 1
    _, _, corps_texte, corps_html = envoyeur.messages[0]
    assert "/auth/reinitialiser-mot-de-passe?jeton=" in corps_texte
    assert "Réinitialiser mon mot de passe" in corps_html


def test_mot_de_passe_oublie_compte_inconnu_ne_revele_rien(client, envoyeur):
    reponse = demander_reset(client, "inconnu@example.com")
    assert reponse.status_code == 202     # même réponse qu'un compte existant
    assert envoyeur.messages == []        # mais aucun mail envoyé


def test_reinitialiser_formulaire_jeton_valide(client, inscrire, envoyeur):
    inscrire()
    demander_reset(client)
    jeton = jeton_du_dernier_mail(envoyeur)
    reponse = client.get("/auth/reinitialiser-mot-de-passe", params={"jeton": jeton})
    assert reponse.status_code == 200
    assert "text/html" in reponse.headers["content-type"]
    assert 'name="mot_de_passe"' in reponse.text  # le formulaire est bien rendu


def test_reinitialiser_formulaire_jeton_invalide(client):
    assert client.get("/auth/reinitialiser-mot-de-passe",
                      params={"jeton": "bidon"}).status_code == 400


def test_reinitialiser_change_mot_de_passe(client, inscrire, envoyeur):
    inscrire()
    demander_reset(client)
    jeton = jeton_du_dernier_mail(envoyeur)
    reponse = client.post("/auth/reinitialiser-mot-de-passe", data={
        "jeton": jeton, "mot_de_passe": "nouveaumdp456", "confirmation": "nouveaumdp456"})
    assert reponse.status_code == 200
    assert "modifié" in reponse.text
    # le nouveau mot de passe fonctionne, l'ancien non
    assert se_connecter(client, DONNEES_INSCRIPTION["pseudo"], "nouveaumdp456").status_code == 200
    assert se_connecter(client, DONNEES_INSCRIPTION["pseudo"]).status_code == 401


def test_reinitialiser_confirmation_differente(client, inscrire, envoyeur):
    inscrire()
    demander_reset(client)
    jeton = jeton_du_dernier_mail(envoyeur)
    reponse = client.post("/auth/reinitialiser-mot-de-passe", data={
        "jeton": jeton, "mot_de_passe": "nouveaumdp456", "confirmation": "autremdp789"})
    assert reponse.status_code == 400
    # mot de passe inchangé : l'ancien fonctionne toujours
    assert se_connecter(client, DONNEES_INSCRIPTION["pseudo"]).status_code == 200


def test_reinitialiser_jeton_usage_unique(client, inscrire, envoyeur):
    inscrire()
    demander_reset(client)
    jeton = jeton_du_dernier_mail(envoyeur)
    ok = client.post("/auth/reinitialiser-mot-de-passe", data={
        "jeton": jeton, "mot_de_passe": "nouveaumdp456", "confirmation": "nouveaumdp456"})
    assert ok.status_code == 200
    # rejouer le même lien après changement de mot de passe → invalidé
    assert client.get("/auth/reinitialiser-mot-de-passe", params={"jeton": jeton}).status_code == 400
    rejoue = client.post("/auth/reinitialiser-mot-de-passe", data={
        "jeton": jeton, "mot_de_passe": "encoreautre999", "confirmation": "encoreautre999"})
    assert rejoue.status_code == 400


# --- Connexion Google ---

def _config_google(monkeypatch, payload):
    """Configure GOOGLE_CLIENT_ID + simule la vérification du id_token Google."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr("api.auth._verifier_token_google", lambda _t: payload)


def test_google_cree_un_compte(client, monkeypatch):
    _config_google(monkeypatch, {
        "email": "nouveau@example.com", "email_verified": True, "given_name": "Léa"})
    reponse = client.post("/auth/google", json={"id_token": "peu-importe"})
    assert reponse.status_code == 200
    assert reponse.json()["access_token"]


def test_google_compte_verifie_sans_mdp(client, db, monkeypatch):
    _config_google(monkeypatch, {
        "email": "lea@example.com", "email_verified": True, "given_name": "Léa"})
    client.post("/auth/google", json={"id_token": "x"})
    u = db.scalar(select(Utilisateur).where(Utilisateur.adresse_mail == "lea@example.com"))
    assert u is not None and u.est_verifie is True and u.mot_de_passe is None
    assert len(u.pseudo) >= 3


def test_google_lie_le_compte_existant(client, inscrire, db, monkeypatch):
    inscrire(verifier=False)  # compte au mot de passe, non vérifié
    id_avant = db.scalar(select(Utilisateur.id_utilisateur).where(
        Utilisateur.adresse_mail == DONNEES_INSCRIPTION["adresse_mail"]))
    _config_google(monkeypatch, {
        "email": DONNEES_INSCRIPTION["adresse_mail"], "email_verified": True,
        "given_name": "Celian"})
    assert client.post("/auth/google", json={"id_token": "x"}).status_code == 200
    comptes = db.scalars(select(Utilisateur).where(
        Utilisateur.adresse_mail == DONNEES_INSCRIPTION["adresse_mail"])).all()
    assert len(comptes) == 1                       # pas de doublon
    assert comptes[0].id_utilisateur == id_avant   # même compte
    assert comptes[0].est_verifie is True          # vérifié par Google


def test_google_token_invalide(client, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")

    def _lever(_t):
        raise ValueError("bad token")
    monkeypatch.setattr("api.auth._verifier_token_google", _lever)
    assert client.post("/auth/google", json={"id_token": "faux"}).status_code == 401


def test_google_email_non_verifie_refuse(client, monkeypatch):
    _config_google(monkeypatch, {"email": "x@example.com", "email_verified": False})
    assert client.post("/auth/google", json={"id_token": "x"}).status_code == 401


def test_google_non_configure(client, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")
    assert client.post("/auth/google", json={"id_token": "x"}).status_code == 503


def test_connexion_mdp_refusee_pour_compte_google(client, monkeypatch):
    # un compte Google (sans mot de passe) ne peut pas se connecter par mot de passe
    _config_google(monkeypatch, {
        "email": "social@example.com", "email_verified": True, "given_name": "Sam"})
    client.post("/auth/google", json={"id_token": "x"})
    reponse = se_connecter(client, "social@example.com", "nimportequoi")
    assert reponse.status_code == 401  # pas 500
