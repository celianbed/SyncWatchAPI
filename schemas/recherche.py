# schemas/recherche.py
from datetime import date
from typing import Literal

from pydantic import BaseModel


class ResultatRecherche(BaseModel):
    """Résultat de /search : projection directe de TMDB, sans passage par le cache."""

    reference_tmdb: int
    type: Literal["serie", "film"]
    titre: str
    affiche: str | None
    image_de_fond: str | None = None
    date_sortie: date | None
    note_moyenne: float | None

    @classmethod
    def depuis_tmdb(cls, brut: dict,
                    type_: Literal["serie", "film"]) -> "ResultatRecherche":
        """Projette un résultat brut TMDB (série ou film) vers ce schéma."""
        serie = type_ == "serie"
        date_brute = brut.get("first_air_date") if serie else brut.get("release_date")
        return cls(
            reference_tmdb=brut["id"], type=type_,
            titre=(brut.get("name") if serie else brut.get("title")) or "",
            affiche=brut.get("poster_path"),
            image_de_fond=brut.get("backdrop_path"),
            date_sortie=date.fromisoformat(date_brute) if date_brute else None,
            note_moyenne=brut.get("vote_average"))
