# tests/faux_tmdb.py — doublure du client TMDB + charges utiles figées
import copy
from collections import Counter

REF_SERIE = 4901

SERIE_DETAIL = {
    "id": REF_SERIE,
    "name": "Les Chroniques",
    "original_name": "The Chronicles",
    "overview": "Une série de test.",
    "poster_path": "/affiche.jpg",
    "backdrop_path": "/fond.jpg",
    "status": "Returning Series",
    "first_air_date": "2020-01-10",
    "vote_average": 8.3,
    "genres": [
        {"id": 18, "name": "Drame"},
        {"id": 10765, "name": "Science-Fiction & Fantastique"},
    ],
    "seasons": [
        {"id": 101, "season_number": 1},
        {"id": 201, "season_number": 2},
    ],
}

SAISONS = {
    1: {
        "id": 101, "season_number": 1, "name": "Saison 1",
        "poster_path": "/s1.jpg", "air_date": "2020-01-10",
        "episodes": [
            {"id": 1001, "episode_number": 1, "name": "Pilote",
             "overview": "Premier épisode.", "runtime": 52,
             "air_date": "2020-01-10", "still_path": "/e11.jpg"},
            {"id": 1002, "episode_number": 2, "name": "La Suite",
             "overview": "", "runtime": 48,
             "air_date": "2020-01-17", "still_path": None},
        ],
    },
    2: {
        "id": 201, "season_number": 2, "name": "Saison 2",
        "poster_path": "/s2.jpg", "air_date": "2021-01-08",
        "episodes": [
            {"id": 2001, "episode_number": 1, "name": "Le Retour",
             "overview": "", "runtime": 50,
             "air_date": "2021-01-08", "still_path": None},
            {"id": 2002, "episode_number": 2, "name": "Épisode à venir",
             "overview": "", "runtime": None,
             "air_date": "", "still_path": None},  # pas encore diffusé
        ],
    },
}

REF_FILM = 550

FILM_DETAIL = {
    "id": REF_FILM,
    "title": "Le Grand Film",
    "original_title": "The Great Movie",
    "overview": "Un film de test.",
    "poster_path": "/film.jpg",
    "runtime": 139,
    "release_date": "1999-10-15",
    "vote_average": 8.4,
    "genres": [{"id": 18, "name": "Drame"}],
}

RECHERCHE_MULTI = {
    "results": [
        {"media_type": "tv", "id": REF_SERIE, "name": "Les Chroniques",
         "poster_path": "/affiche.jpg", "backdrop_path": "/fond.jpg",
         "first_air_date": "2020-01-10", "vote_average": 8.3},
        {"media_type": "movie", "id": 550, "title": "Le Grand Film",
         "poster_path": "/film.jpg", "release_date": "1999-10-15",
         "vote_average": 8.4},
        {"media_type": "person", "id": 42, "name": "Personne Célèbre"},
    ]
}

# /tv/on_the_air et /movie/now_playing : pas de media_type dans ces réponses
SERIES_A_L_ANTENNE = {
    "results": [
        {"id": REF_SERIE, "name": "Les Chroniques", "poster_path": "/affiche.jpg",
         "backdrop_path": "/fond.jpg", "first_air_date": "2020-01-10",
         "vote_average": 8.3},
    ]
}

FILMS_A_L_AFFICHE = {
    "results": [
        {"id": REF_FILM, "title": "Le Grand Film", "poster_path": "/film.jpg",
         "release_date": "1999-10-15", "vote_average": 8.4},
    ]
}

# /watch/providers : offres par pays (données JustWatch)
PLATEFORMES = {
    "results": {
        "FR": {
            "link": "https://www.themoviedb.org/tv/4901/watch?locale=FR",
            "flatrate": [{"provider_name": "Netflix", "logo_path": "/netflix.jpg"}],
            "ads": [{"provider_name": "TF1+", "logo_path": "/tf1.jpg"}],
            "buy": [{"provider_name": "Apple TV", "logo_path": "/atv.jpg"}],
        },
    }
}

# /recommendations : résultats typés selon le média interrogé
SIMILAIRES_TV = {
    "results": [
        {"id": 777, "name": "La Suite des Chroniques", "poster_path": "/suite.jpg",
         "first_air_date": "2022-03-01", "vote_average": 7.5},
    ]
}

SIMILAIRES_FILM = {
    "results": [
        {"id": 888, "title": "Le Film Suivant", "poster_path": "/suivant.jpg",
         "release_date": "2001-05-01", "vote_average": 7.1},
    ]
}

# /{media}/{id}/videos : bandes-annonces (on privilégie Trailer officiel FR)
VIDEOS = {
    "results": [
        {"site": "Vimeo", "key": "ignore", "type": "Trailer", "official": True,
         "iso_639_1": "fr", "name": "Sur Vimeo — ignoré"},
        {"site": "YouTube", "key": "cle_fr", "type": "Trailer", "official": True,
         "iso_639_1": "fr", "name": "Bande-annonce VF"},
        {"site": "YouTube", "key": "cle_en", "type": "Teaser", "official": True,
         "iso_639_1": "en", "name": "Teaser"},
    ]
}


class FauxClientTMDB:
    """Même interface que ClientTMDB, réponses figées, compteur d'appels."""

    def __init__(self):
        self.compteurs = Counter()

    async def search_multi(self, requete):
        self.compteurs["search_multi"] += 1
        return copy.deepcopy(RECHERCHE_MULTI)

    async def tendances(self):
        # même forme de charge utile que search_multi (endpoint TMDB /trending)
        self.compteurs["tendances"] += 1
        return copy.deepcopy(RECHERCHE_MULTI)

    async def series_a_l_antenne(self):
        self.compteurs["series_a_l_antenne"] += 1
        return copy.deepcopy(SERIES_A_L_ANTENNE)

    async def films_a_l_affiche(self):
        self.compteurs["films_a_l_affiche"] += 1
        return copy.deepcopy(FILMS_A_L_AFFICHE)

    async def plateformes(self, media, tmdb_id):
        self.compteurs["plateformes"] += 1
        return copy.deepcopy(PLATEFORMES)

    async def similaires(self, media, tmdb_id):
        self.compteurs["similaires"] += 1
        return copy.deepcopy(SIMILAIRES_TV if media == "tv" else SIMILAIRES_FILM)

    async def videos(self, media, tmdb_id):
        self.compteurs["videos"] += 1
        return copy.deepcopy(VIDEOS["results"])

    async def get_serie(self, tmdb_id, append=None):
        self.compteurs["get_serie"] += 1
        return copy.deepcopy(SERIE_DETAIL) if tmdb_id == REF_SERIE else None

    async def get_saison(self, tmdb_id, num_saison):
        self.compteurs["get_saison"] += 1
        if tmdb_id != REF_SERIE:
            return None
        return copy.deepcopy(SAISONS.get(num_saison))

    async def get_film(self, tmdb_id):
        self.compteurs["get_film"] += 1
        return copy.deepcopy(FILM_DETAIL) if tmdb_id == REF_FILM else None
