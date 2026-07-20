# schemas/plateformes.py — « Où regarder » (données JustWatch via TMDB)
from pydantic import BaseModel


class Plateforme(BaseModel):
    nom: str
    logo: str | None


class PlateformesVisionnage(BaseModel):
    """Offres de visionnage dans un pays. Source JustWatch relayée par TMDB :
    l'attribution « Données JustWatch » doit rester visible côté client."""

    lien: str | None  # page « où regarder » de TMDB (porte l'attribution)
    abonnement: list[Plateforme]
    gratuit: list[Plateforme]
    location: list[Plateforme]
    achat: list[Plateforme]

    @classmethod
    def depuis_tmdb(cls, donnees: dict | None, pays: str) -> "PlateformesVisionnage":
        offres = ((donnees or {}).get("results") or {}).get(pays) or {}

        def groupe(*cles: str) -> list[Plateforme]:
            return [Plateforme(nom=p.get("provider_name") or "",
                               logo=p.get("logo_path"))
                    for cle in cles for p in offres.get(cle) or []]

        return cls(lien=offres.get("link"),
                   abonnement=groupe("flatrate"),
                   gratuit=groupe("free", "ads"),
                   location=groupe("rent"),
                   achat=groupe("buy"))
