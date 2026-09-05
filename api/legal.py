# api/legal.py — pages publiques exigées par la loi et par l'App Store :
# mentions légales et politique de confidentialité.
import html

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
    """Valeurs échappées : elles viennent de l'environnement, donc d'une source de
    confiance, mais string.Template n'échappe rien et l'échappement est gratuit."""
    champs = {
        "editeur_nom": settings.EDITEUR_NOM,
        "editeur_adresse": settings.EDITEUR_ADRESSE,
        "editeur_siret": settings.EDITEUR_SIRET,
        "contact": settings.CONTACT_EMAIL,
        "hebergeur": settings.HEBERGEUR,
        "hebergeur_bdd": settings.HEBERGEUR_BDD,
    }
    return {cle: html.escape(valeur) if valeur else MANQUANT
            for cle, valeur in champs.items()}


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
