# tests/test_legal.py — pages légales publiques.
# Elles conditionnent la fiche App Store : une URL absente, en erreur ou vide de
# l'identité de l'éditeur est un motif de rejet, et un manquement légal.
import pytest

from core.config import settings

PAGES = ["/mentions-legales", "/confidentialite"]


@pytest.fixture()
def editeur_configure(monkeypatch):
    monkeypatch.setattr(settings, "EDITEUR_NOM", "Jean Exemple")
    monkeypatch.setattr(settings, "EDITEUR_ADRESSE", "1 rue du Test, 75000 Paris")
    monkeypatch.setattr(settings, "EDITEUR_SIRET", "12345678900012")
    monkeypatch.setattr(settings, "CONTACT_EMAIL", "contact@example.com")


@pytest.mark.parametrize("chemin", PAGES)
def test_page_publique_et_sans_jeton(client, chemin):
    reponse = client.get(chemin)
    assert reponse.status_code == 200
    assert reponse.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize("chemin", PAGES)
def test_identite_affichee(client, chemin, editeur_configure):
    corps = client.get(chemin).text
    assert "Jean Exemple" in corps
    assert "contact@example.com" in corps


def test_mentions_portent_siret_et_adresse(client, editeur_configure):
    corps = client.get("/mentions-legales").text
    assert "12345678900012" in corps
    assert "1 rue du Test, 75000 Paris" in corps


@pytest.mark.parametrize("chemin", PAGES)
def test_identite_manquante_bien_visible(client, chemin, monkeypatch):
    # une identité oubliée doit sauter aux yeux sur la page, pas laisser un blanc
    for champ in ("EDITEUR_NOM", "EDITEUR_ADRESSE", "EDITEUR_SIRET", "CONTACT_EMAIL"):
        monkeypatch.setattr(settings, champ, "")
    assert "— à compléter —" in client.get(chemin).text


def test_attribution_tmdb(client):
    # exigée par les conditions d'utilisation de l'API TMDB, au mot près
    assert ("This product uses the TMDB API but is not endorsed or certified by TMDB"
            in client.get("/mentions-legales").text)


def test_confidentialite_decrit_la_suppression_de_compte(client):
    # le reviewer App Store cherche ce chemin, et le RGPD l'exige
    corps = client.get("/confidentialite").text
    assert "Supprimer mon compte" in corps
    assert "immédiat et définitif" in corps


def test_confidentialite_annonce_les_droits_et_la_cnil(client):
    corps = client.get("/confidentialite").text
    assert "cnil.fr" in corps
    for droit in ("rectification", "effacement", "portabilité", "opposition"):
        assert droit in corps


def test_les_deux_pages_se_citent(client):
    # App Store Connect demande une URL de confidentialité : elle doit être trouvable
    assert "/confidentialite" in client.get("/mentions-legales").text
    assert "/mentions-legales" in client.get("/confidentialite").text
