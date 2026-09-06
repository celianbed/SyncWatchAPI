# tests/test_validation.py — les refus de validation doivent être lisibles.
#
# Un 422 renvoyait la liste technique de FastAPI dans `detail` ; l'app, qui
# n'affiche `detail` que si c'est une chaîne, se rabattait sur « Une erreur est
# survenue (422). » — impossible pour la personne de savoir quoi corriger.
import pytest


def _detail(reponse):
    corps = reponse.json()
    assert isinstance(corps["detail"], str), "l'app n'affiche `detail` que si c'est une chaîne"
    return corps["detail"]


def test_pseudo_interdit_dit_ce_qui_est_permis(inscrire):
    reponse = inscrire(pseudo="<img src=x onerror=a>")
    assert reponse.status_code == 422
    detail = _detail(reponse)
    assert "pseudo" in detail.lower()
    assert "lettres" in detail and "chiffres" in detail


def test_pseudo_trop_court_donne_la_longueur(inscrire):
    detail = _detail(inscrire(pseudo="ab"))
    assert "3 caractères" in detail


def test_mail_invalide_le_dit_en_francais(inscrire):
    detail = _detail(inscrire(adresse_mail="pas-un-mail"))
    assert detail == "L'adresse mail n'est pas valide."


def test_mot_de_passe_trop_court_donne_la_longueur(inscrire):
    detail = _detail(inscrire(mot_de_passe="court"))
    assert "8 caractères" in detail


def test_mot_de_passe_trop_long_reprend_notre_message(inscrire):
    # 40 caractères accentués = 80 octets : au-delà de la limite bcrypt
    detail = _detail(inscrire(mot_de_passe="é" * 40))
    assert "72 octets" in detail


def test_champ_manquant(client):
    reponse = client.post("/utilisateurs", json={"pseudo": "kenan"})
    assert reponse.status_code == 422
    detail = _detail(reponse)
    assert "obligatoire" in detail


def test_deux_erreurs_sont_reunies_en_une_phrase(inscrire):
    detail = _detail(inscrire(pseudo="ab", mot_de_passe="court"))
    assert "3 caractères" in detail and "8 caractères" in detail


@pytest.mark.parametrize("pseudo", ["Kenan Turhan", "kenan_00", "jean-luc", "l.é.o", "Zoé"])
def test_pseudos_valides_acceptes(inscrire, pseudo):
    # les accents passent : le motif s'appuie sur \w, qui est Unicode en Python.
    # L'app doit refléter exactement cette règle, sans quoi elle bloquerait des
    # pseudos que l'API accepte (et l'inverse).
    reponse = inscrire(pseudo=pseudo)
    assert reponse.status_code == 202, (
        _detail(reponse) if reponse.status_code == 422 else reponse.text)
