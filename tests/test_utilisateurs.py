# tests/test_utilisateurs.py
from sqlalchemy import select

from core.securite import verifier_mot_de_passe
from models import Utilisateur
from tests.conftest import DONNEES_INSCRIPTION


def test_inscription_valide(inscrire):
    reponse = inscrire()
    assert reponse.status_code == 201
    corps = reponse.json()
    assert corps["pseudo"] == "celian"
    assert corps["statut_compte"] == "actif"
    assert "mot_de_passe" not in corps


def test_mot_de_passe_hache_en_base(inscrire, db):
    inscrire()
    utilisateur = db.scalar(select(Utilisateur).where(Utilisateur.pseudo == "celian"))
    assert utilisateur.mot_de_passe != DONNEES_INSCRIPTION["mot_de_passe"]
    assert verifier_mot_de_passe(DONNEES_INSCRIPTION["mot_de_passe"], utilisateur.mot_de_passe)


def test_mail_en_double(inscrire):
    inscrire()
    reponse = inscrire(pseudo="autre")
    assert reponse.status_code == 409
    assert "mail" in reponse.json()["detail"]


def test_pseudo_en_double(inscrire):
    inscrire()
    reponse = inscrire(adresse_mail="autre@example.com")
    assert reponse.status_code == 409
    assert "pseudo" in reponse.json()["detail"]


def test_mail_invalide(inscrire):
    assert inscrire(adresse_mail="pas-un-mail").status_code == 422


def test_mot_de_passe_trop_court(inscrire):
    assert inscrire(mot_de_passe="court").status_code == 422


def test_mot_de_passe_depasse_72_octets(inscrire):
    # 40 caractères accentués = 80 octets en UTF-8 : au-delà de la limite bcrypt
    assert inscrire(mot_de_passe="é" * 40).status_code == 422


def test_lecture_par_id(inscrire, client):
    id_utilisateur = inscrire().json()["id_utilisateur"]
    reponse = client.get(f"/utilisateurs/{id_utilisateur}")
    assert reponse.status_code == 200
    assert reponse.json()["pseudo"] == "celian"


def test_lecture_id_inconnu(client):
    assert client.get("/utilisateurs/999999").status_code == 404


def _entete(jeton):
    return {"Authorization": f"Bearer {jeton}"}


def test_modifier_profil(client, jeton):
    reponse = client.patch("/utilisateurs/moi", headers=_entete(jeton),
                           json={"pseudo": "nouveau", "avatar": "https://exemple.fr/a.png"})
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["pseudo"] == "nouveau"
    assert corps["avatar"] == "https://exemple.fr/a.png"


def test_modifier_profil_partiel(client, jeton):
    # seul l'avatar change : le pseudo reste celui de l'inscription
    reponse = client.patch("/utilisateurs/moi", headers=_entete(jeton),
                           json={"avatar": "https://exemple.fr/a.png"})
    assert reponse.status_code == 200
    assert reponse.json()["pseudo"] == "celian"


def test_retirer_avatar(client, jeton):
    client.patch("/utilisateurs/moi", headers=_entete(jeton),
                 json={"avatar": "https://exemple.fr/a.png"})
    reponse = client.patch("/utilisateurs/moi", headers=_entete(jeton),
                           json={"avatar": None})
    assert reponse.status_code == 200
    assert reponse.json()["avatar"] is None


def test_modifier_pseudo_deja_pris(client, jeton, inscrire):
    inscrire(adresse_mail="autre@example.com", pseudo="autre")
    reponse = client.patch("/utilisateurs/moi", headers=_entete(jeton),
                           json={"pseudo": "autre"})
    assert reponse.status_code == 409
    assert "pseudo" in reponse.json()["detail"]


def test_modifier_pseudo_trop_court(client, jeton):
    assert client.patch("/utilisateurs/moi", headers=_entete(jeton),
                        json={"pseudo": "ab"}).status_code == 422


def test_modifier_profil_sans_jeton(client):
    assert client.patch("/utilisateurs/moi",
                        json={"pseudo": "intrus"}).status_code == 401
