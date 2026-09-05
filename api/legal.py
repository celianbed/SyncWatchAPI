# api/legal.py — pages publiques exigées par la loi et par l'App Store :
# mentions légales et politique de confidentialité.
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from core.config import settings
from core.gabarits import rendre

router = APIRouter()

# Date de dernière révision des textes eux-mêmes : à remonter à la main dès qu'on
# touche au fond, jamais automatiquement (sinon elle mentirait à chaque déploiement).
MAJ = "5 septembre 2026"

# Un champ d'identité oublié doit crever les yeux sur la page plutôt que de laisser
# un blanc : une mention légale incomplète est un manquement, pas un détail.
MANQUANT = "— à compléter —"


def _identite() -> dict[str, str]:
    return {
        "editeur_nom": settings.EDITEUR_NOM or MANQUANT,
        "editeur_adresse": settings.EDITEUR_ADRESSE or MANQUANT,
        "editeur_siret": settings.EDITEUR_SIRET or MANQUANT,
        "contact": settings.CONTACT_EMAIL or MANQUANT,
        "hebergeur": settings.HEBERGEUR or MANQUANT,
        "hebergeur_bdd": settings.HEBERGEUR_BDD or MANQUANT,
    }


def _page(gabarit: str, titre: str) -> HTMLResponse:
    """Rend le corps du document, puis l'enveloppe dans la mise en page commune."""
    return HTMLResponse(rendre("page_legale.html", titre=titre, maj=MAJ,
                               contenu=rendre(gabarit, **_identite())))


@router.get("/mentions-legales", response_class=HTMLResponse)
def mentions_legales():
    return _page("mentions_legales.html", "Mentions légales")


@router.get("/confidentialite", response_class=HTMLResponse)
def confidentialite():
    return _page("confidentialite.html", "Politique de confidentialité")
