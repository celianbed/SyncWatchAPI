# tests/test_utilisateurs.py
from sqlalchemy import func, select

from core.securite import verifier_mot_de_passe
from models import Appareil, SuivreSerie, Utilisateur
from tests.conftest import DONNEES_INSCRIPTION
from tests.faux_tmdb import REF_FILM, REF_SERIE


def test_inscription_valide(inscrire, db):
    reponse = inscrire()
    assert reponse.status_code == 202
    # réponse volontairement générique : aucune donnée de compte n'en sort
    corps = reponse.json()
    assert "mot_de_passe" not in corps and "id_utilisateur" not in corps
    # le compte est bien créé en base
    assert db.scalar(select(Utilisateur).where(
        Utilisateur.pseudo == "celian")) is not None


def test_mot_de_passe_hache_en_base(inscrire, db):
    inscrire()
    utilisateur = db.scalar(select(Utilisateur).where(Utilisateur.pseudo == "celian"))
    assert utilisateur.mot_de_passe != DONNEES_INSCRIPTION["mot_de_passe"]
    assert verifier_mot_de_passe(DONNEES_INSCRIPTION["mot_de_passe"], utilisateur.mot_de_passe)


def test_mail_en_double_ne_revele_rien(inscrire, db, envoyeur):
    """Anti-énumération : réponse identique à une inscription normale."""
    premiere = inscrire()
    envoyeur.messages.clear()
    seconde = inscrire(pseudo="autre")

    # même code et même corps que la 1re : impossible de deviner que l'adresse existe
    assert seconde.status_code == premiere.status_code == 202
    assert seconde.json() == premiere.json()
    # aucun compte en double n'a été créé
    assert db.scalar(select(func.count()).select_from(Utilisateur).where(
        Utilisateur.adresse_mail == DONNEES_INSCRIPTION["adresse_mail"])) == 1
    # c'est le vrai propriétaire qui est prévenu par mail
    assert len(envoyeur.messages) == 1
    assert envoyeur.messages[0][0] == DONNEES_INSCRIPTION["adresse_mail"]
    assert "déjà" in envoyeur.messages[0][2]


def test_pseudo_caracteres_interdits(inscrire):
    """Un pseudo ne doit pas pouvoir porter de balise (injection dans les mails/pages)."""
    reponse = inscrire(pseudo="<img src=x onerror=a>")
    assert reponse.status_code == 422


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


def test_lecture_par_id(client, jeton):
    """Profil d'un autre utilisateur : accessible aux connectés, SANS adresse mail."""
    id_utilisateur = client.get("/utilisateurs/moi",
                                headers=_entete(jeton)).json()["id_utilisateur"]
    reponse = client.get(f"/utilisateurs/{id_utilisateur}", headers=_entete(jeton))
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["pseudo"] == "celian"
    # fuite de données : l'adresse mail ne doit jamais sortir sur ce profil
    assert "adresse_mail" not in corps


def test_lecture_par_id_sans_jeton(client):
    """Endpoint fermé aux anonymes : empêche l'aspiration des profils."""
    assert client.get("/utilisateurs/1").status_code == 401


def test_lecture_id_inconnu(client, jeton):
    assert client.get("/utilisateurs/999999",
                      headers=_entete(jeton)).status_code == 404


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


# --- Profil : favoris & films vus (carrousels) ---

def test_mes_favoris(client, jeton):
    client.post(f"/films/{REF_FILM}/suivre", headers=_entete(jeton),
                json={"favori": True})
    client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton),
                json={"favori": True})
    reponse = client.get("/utilisateurs/moi/favoris", headers=_entete(jeton))
    assert reponse.status_code == 200
    corps = reponse.json()
    assert {r["type"] for r in corps} == {"serie", "film"}


def test_mes_favoris_exclut_non_favoris(client, jeton):
    # suivi sans favori → n'apparaît pas dans les favoris
    client.post(f"/films/{REF_FILM}/suivre", headers=_entete(jeton))
    reponse = client.get("/utilisateurs/moi/favoris", headers=_entete(jeton))
    assert reponse.json() == []


def test_mes_films_vus(client, jeton):
    client.post(f"/films/{REF_FILM}/vu", headers=_entete(jeton))
    reponse = client.get("/utilisateurs/moi/films-vus", headers=_entete(jeton))
    assert reponse.status_code == 200
    corps = reponse.json()
    assert len(corps) == 1
    assert corps[0]["type"] == "film"


def test_mes_films_vus_vide(client, jeton):
    assert client.get("/utilisateurs/moi/films-vus",
                      headers=_entete(jeton)).json() == []


def test_profil_favoris_sans_jeton(client):
    assert client.get("/utilisateurs/moi/favoris").status_code == 401


# --- Suppression de compte (exigence App Store 5.1.1 v) ---

def test_supprimer_mon_compte(client, jeton, db):
    assert client.delete("/utilisateurs/moi", headers=_entete(jeton)).status_code == 204
    assert db.scalar(select(func.count()).select_from(Utilisateur)) == 0
    # le jeton d'accès ne vaut plus rien
    assert client.get("/utilisateurs/moi", headers=_entete(jeton)).status_code == 401


def test_suppression_emporte_toutes_les_donnees(client, jeton, db):
    client.post(f"/series/{REF_SERIE}/suivre", headers=_entete(jeton))
    client.post("/appareils", headers=_entete(jeton),
                json={"jeton_notif": "fcm-a-oublier", "plateforme": "ios"})

    client.delete("/utilisateurs/moi", headers=_entete(jeton))

    # tout ce qui pendait au compte part en cascade
    assert db.scalar(select(func.count()).select_from(SuivreSerie)) == 0
    assert db.scalar(select(func.count()).select_from(Appareil)) == 0


def test_suppression_exige_un_jeton(client):
    assert client.delete("/utilisateurs/moi").status_code == 401
