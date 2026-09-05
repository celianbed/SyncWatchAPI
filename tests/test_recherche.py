# tests/test_recherche.py
from tests.faux_tmdb import REF_SERIE


def test_recherche_series_et_films(client):
    reponse = client.get("/search", params={"q": "chroniques"})
    assert reponse.status_code == 200
    resultats = reponse.json()

    # la personne des résultats TMDB est filtrée
    assert len(resultats) == 2
    assert {r["type"] for r in resultats} == {"serie", "film"}

    serie = next(r for r in resultats if r["type"] == "serie")
    assert serie["reference_tmdb"] == REF_SERIE
    assert serie["titre"] == "Les Chroniques"
    assert serie["date_sortie"] == "2020-01-10"


def test_recherche_sans_parametre(client):
    assert client.get("/search").status_code == 422


def test_recherche_vide(client):
    assert client.get("/search", params={"q": ""}).status_code == 422


def test_tendances(client, tmdb_faux):
    reponse = client.get("/search/tendances")
    assert reponse.status_code == 200
    resultats = reponse.json()

    # même projection que /search : les personnes sont filtrées
    assert len(resultats) == 2
    assert {r["type"] for r in resultats} == {"serie", "film"}
    assert tmdb_faux.compteurs["tendances"] == 1

    # l'image de fond TMDB est exposée pour la carte héro de l'accueil
    serie = next(r for r in resultats if r["type"] == "serie")
    assert serie["image_de_fond"] == "/fond.jpg"


def test_nouveautes_series(client, tmdb_faux):
    reponse = client.get("/search/nouveautes", params={"type": "serie"})
    assert reponse.status_code == 200
    resultats = reponse.json()

    assert len(resultats) == 1
    assert resultats[0]["type"] == "serie"
    assert resultats[0]["titre"] == "Les Chroniques"
    assert tmdb_faux.compteurs["series_a_l_antenne"] == 1


def test_nouveautes_films(client, tmdb_faux):
    reponse = client.get("/search/nouveautes", params={"type": "film"})
    assert reponse.status_code == 200
    resultats = reponse.json()

    assert len(resultats) == 1
    assert resultats[0]["type"] == "film"
    assert resultats[0]["titre"] == "Le Grand Film"
    assert tmdb_faux.compteurs["films_a_l_affiche"] == 1


def test_nouveautes_type_requis(client):
    assert client.get("/search/nouveautes").status_code == 422
    assert client.get("/search/nouveautes",
                      params={"type": "musique"}).status_code == 422


def test_rate_limit_recherche(client):
    """La recherche est publique et coûte un appel TMDB : elle doit être plafonnée
    pour qu'on ne puisse pas brûler le quota TMDB en la martelant."""
    from core.limitation import limiteur
    limiteur.enabled = True
    limiteur.reset()
    try:
        codes = [client.get("/search/tendances").status_code for _ in range(35)]
    finally:
        limiteur.enabled = False
        limiteur.reset()
    assert 429 in codes


# --- cache partagé : un second appel identique ne doit pas retaper TMDB --------


def test_tendances_second_appel_servi_par_le_cache(client, tmdb_faux):
    client.get("/search/tendances")
    client.get("/search/tendances")
    assert tmdb_faux.compteurs["tendances"] == 1


def test_recherche_second_appel_servi_par_le_cache(client, tmdb_faux):
    client.get("/search", params={"q": "chroniques"})
    client.get("/search", params={"q": "chroniques"})
    assert tmdb_faux.compteurs["search_multi"] == 1


def test_recherche_casse_et_espaces_partagent_la_meme_entree(client, tmdb_faux):
    """« Chroniques » et « chroniques  » désignent la même recherche."""
    client.get("/search", params={"q": "Chroniques"})
    client.get("/search", params={"q": "  chroniques "})
    assert tmdb_faux.compteurs["search_multi"] == 1


def test_recherches_differentes_ne_se_melangent_pas(client, tmdb_faux):
    client.get("/search", params={"q": "chroniques"})
    client.get("/search", params={"q": "grand film"})
    assert tmdb_faux.compteurs["search_multi"] == 2


def test_nouveautes_series_et_films_ont_des_entrees_distinctes(client, tmdb_faux):
    client.get("/search/nouveautes", params={"type": "serie"})
    client.get("/search/nouveautes", params={"type": "serie"})
    client.get("/search/nouveautes", params={"type": "film"})
    assert tmdb_faux.compteurs["series_a_l_antenne"] == 1
    assert tmdb_faux.compteurs["films_a_l_affiche"] == 1


def test_recherche_trop_longue_refusee(client):
    """La longueur de q est bornée : elle part chez TMDB et sert de clé de cache."""
    assert client.get("/search", params={"q": "a" * 101}).status_code == 422
