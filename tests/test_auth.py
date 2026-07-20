# tests/test_auth.py
from datetime import datetime, timedelta, timezone

from jose import jwt
from sqlalchemy import select

from core.config import settings
from models import Utilisateur
from tests.conftest import DONNEES_INSCRIPTION


def se_connecter(client, username, password=DONNEES_INSCRIPTION["mot_de_passe"]):
    return client.post("/auth/connexion", data={"username": username, "password": password})


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
