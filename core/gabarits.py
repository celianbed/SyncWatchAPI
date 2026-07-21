# core/gabarits.py — rend les gabarits (HTML, copie d'emails) rangés dans templates/
import tomllib
from functools import lru_cache
from pathlib import Path
from string import Template

_DOSSIER = Path(__file__).resolve().parents[1] / "templates"


@lru_cache(maxsize=None)
def _gabarit(nom: str) -> Template:
    return Template((_DOSSIER / nom).read_text(encoding="utf-8"))


def rendre(nom: str, **contexte: str) -> str:
    """Charge templates/<nom> et substitue les $placeholders (syntaxe string.Template :
    n'entre pas en conflit avec les accolades du CSS/JS). Les valeurs issues de
    l'utilisateur doivent être échappées (html.escape) par l'appelant."""
    return _gabarit(nom).substitute(**contexte)


def substituer(gabarit: str, **contexte: str) -> str:
    """Substitue les $placeholders dans une chaîne (copie d'email, etc.)."""
    return Template(gabarit).substitute(**contexte)


@lru_cache(maxsize=None)
def contenus_emails() -> dict:
    """Copie des emails (sujet, titre, bouton, corps…) depuis templates/emails.toml."""
    return tomllib.loads((_DOSSIER / "emails.toml").read_text(encoding="utf-8"))
