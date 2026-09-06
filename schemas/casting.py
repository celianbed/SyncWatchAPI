# schemas/casting.py
from pydantic import BaseModel


class MembreCasting(BaseModel):
    """Une tête d'affiche, vue par l'utilisateur qui consulte la fiche."""

    id_acteur: int
    nom: str
    photo: str | None
    personnage: str | None

    # Nombre d'AUTRES titres de votre historique où cette personne joue. C'est
    # tout l'intérêt d'une table de casting plutôt qu'un passage direct depuis
    # TMDB : Letterboxd affiche une liste, nous affichons un lien avec vous.
    deja_vu_dans: int = 0
