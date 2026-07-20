# api/tests/test_fiche_extras.py — « Où regarder » et « Titres similaires »
from api.tests.faux_tmdb import REF_FILM, REF_SERIE


def test_plateformes_serie(client, tmdb_faux):
    reponse = client.get(f"/series/{REF_SERIE}/plateformes")
    assert reponse.status_code == 200
    corps = reponse.json()

    assert corps["abonnement"] == [{"nom": "Netflix", "logo": "/netflix.jpg"}]
    assert corps["gratuit"] == [{"nom": "TF1+", "logo": "/tf1.jpg"}]
    assert corps["achat"] == [{"nom": "Apple TV", "logo": "/atv.jpg"}]
    assert corps["location"] == []
    assert "themoviedb.org" in corps["lien"]
    assert tmdb_faux.compteurs["plateformes"] == 1


def test_plateformes_pays_sans_offre(client):
    reponse = client.get(f"/series/{REF_SERIE}/plateformes", params={"pays": "jp"})
    assert reponse.status_code == 200
    corps = reponse.json()

    # pays normalisé en majuscules, absent des offres : listes vides
    assert corps["abonnement"] == []
    assert corps["lien"] is None


def test_plateformes_film(client, tmdb_faux):
    reponse = client.get(f"/films/{REF_FILM}/plateformes")
    assert reponse.status_code == 200
    assert reponse.json()["abonnement"][0]["nom"] == "Netflix"


def test_similaires_serie(client, tmdb_faux):
    reponse = client.get(f"/series/{REF_SERIE}/similaires")
    assert reponse.status_code == 200
    resultats = reponse.json()

    assert len(resultats) == 1
    assert resultats[0]["type"] == "serie"
    assert resultats[0]["titre"] == "La Suite des Chroniques"
    assert tmdb_faux.compteurs["similaires"] == 1


def test_similaires_film(client):
    reponse = client.get(f"/films/{REF_FILM}/similaires")
    assert reponse.status_code == 200
    resultats = reponse.json()

    assert len(resultats) == 1
    assert resultats[0]["type"] == "film"
    assert resultats[0]["titre"] == "Le Film Suivant"
