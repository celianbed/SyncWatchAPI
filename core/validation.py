# core/validation.py — messages de validation lisibles par un humain.
#
# Par défaut, FastAPI renvoie sur un 422 une LISTE d'objets techniques en
# anglais dans `detail`. Les clients (l'app iOS notamment) n'affichent `detail`
# que si c'est une chaîne : un pseudo refusé se traduisait donc à l'écran par
# « Une erreur est survenue (422). », sans dire quoi corriger.
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Nom du champ tel qu'on veut le voir apparaître dans la phrase.
LIBELLES = {
    "adresse_mail": "L'adresse mail",
    "pseudo": "Le pseudo",
    "mot_de_passe": "Le mot de passe",
    "note": "La note",
    "commentaire": "Le commentaire",
    "statut_suivi": "Le statut de suivi",
    "statut": "Le statut",
    "avatar": "L'avatar",
    "prenom": "Le prénom",
    "identity_token": "Le jeton d'identité",
    "id_token": "Le jeton d'identité",
}

# Quand le motif d'un champ est refusé, dire ce qui est permis plutôt que
# d'afficher l'expression régulière.
FORMATS = {
    "pseudo": "Le pseudo ne peut contenir que des lettres, des chiffres, "
              "des espaces, des points, des tirets et des tirets bas.",
}


def _champ(erreur: dict) -> str | None:
    """Dernier segment nommé de `loc` — « body » et les index ne nous disent rien."""
    for partie in reversed(erreur.get("loc", ())):
        if isinstance(partie, str) and partie not in ("body", "query", "path"):
            return partie
    return None


def message_validation(erreur: dict) -> str:
    champ = _champ(erreur)
    libelle = LIBELLES.get(champ) or (f"Le champ « {champ} »" if champ else "La requête")
    contexte = erreur.get("ctx") or {}

    match erreur.get("type"):
        case "missing":
            return f"{libelle} est obligatoire."
        case "string_too_short":
            return f"{libelle} doit faire au moins {contexte.get('min_length')} caractères."
        case "string_too_long":
            return f"{libelle} ne doit pas dépasser {contexte.get('max_length')} caractères."
        case "string_pattern_mismatch":
            return FORMATS.get(champ, f"{libelle} n'a pas le format attendu.")
        case "greater_than_equal":
            return f"{libelle} doit être au moins {contexte.get('ge')}."
        case "less_than_equal":
            return f"{libelle} ne doit pas dépasser {contexte.get('le')}."
        case "int_parsing" | "float_parsing":
            return f"{libelle} doit être un nombre."
        case "bool_parsing":
            return f"{libelle} doit valoir vrai ou faux."
        case "value_error":
            # EmailStr rend un message anglais ; nos validateurs maison, du français
            if champ == "adresse_mail":
                return "L'adresse mail n'est pas valide."
            texte = str(contexte.get("error") or "").strip()
            if texte:
                return texte[0].upper() + texte[1:] + ("" if texte.endswith(".") else ".")
            return f"{libelle} est invalide."
        case _:
            return f"{libelle} est invalide."


async def gestionnaire_erreurs_validation(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Remplace la liste technique par une phrase française affichable telle quelle."""
    # dict.fromkeys : dédoublonne sans perdre l'ordre (deux règles peuvent
    # échouer sur le même champ et produire la même phrase)
    phrases = dict.fromkeys(message_validation(e) for e in exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": " ".join(phrases)},
    )
