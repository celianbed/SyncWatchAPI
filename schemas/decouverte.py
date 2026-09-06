# schemas/decouverte.py
from typing import Literal

from pydantic import BaseModel


class ExtraitFeed(BaseModel):
    """Une entrée du feed « extraits » : un titre en tendance + sa bande-annonce."""

    reference_tmdb: int
    type: Literal["serie", "film"]
    titre: str
    affiche: str | None
    image_de_fond: str | None = None
    apercu: str | None = None
    annee: int | None = None
    note_moyenne: float | None = None
    cle_youtube: str  # identifiant de la vidéo YouTube (bande-annonce)


class BandeAnnonce(BaseModel):
    """Meilleure bande-annonce YouTube d'un titre, pour le bouton de la fiche.

    Même classement que le feed « Extraits » : Trailer avant Teaser, officiel
    avant amateur, VF avant VO.
    """

    cle_youtube: str
