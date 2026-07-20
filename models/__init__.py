# models/__init__.py
from models.utilisateur import Utilisateur
from models.serie import Serie, Saison, Episode, categoriser_serie
from models.film import Film, categoriser_film
from models.genre import Genre
from models.suivi import SuivreSerie, VisionnerEpisode, SuivreFilm, VisionnerFilm
from models.avis import Avis
from models.notification import Appareil, Notification

__all__ = [
    "Utilisateur",
    "Serie", "Saison", "Episode", "categoriser_serie",
    "Film", "categoriser_film",
    "Genre",
    "SuivreSerie", "VisionnerEpisode", "SuivreFilm", "VisionnerFilm",
    "Avis",
    "Appareil", "Notification",
]
