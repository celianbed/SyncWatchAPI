# api/models/__init__.py
from api.models.utilisateur import Utilisateur
from api.models.serie import Serie, Saison, Episode, categoriser_serie
from api.models.film import Film, categoriser_film
from api.models.genre import Genre
from api.models.suivi import SuivreSerie, VisionnerEpisode, SuivreFilm, VisionnerFilm
from api.models.avis import Avis
from api.models.notification import Appareil, Notification

__all__ = [
    "Utilisateur",
    "Serie", "Saison", "Episode", "categoriser_serie",
    "Film", "categoriser_film",
    "Genre",
    "SuivreSerie", "VisionnerEpisode", "SuivreFilm", "VisionnerFilm",
    "Avis",
    "Appareil", "Notification",
]
