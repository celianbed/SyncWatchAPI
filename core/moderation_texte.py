# core/moderation_texte.py — filtre lexical des commentaires.
#
# La directive 1.2 de l'App Store demande « une méthode de filtrage des
# contenus répréhensibles ». Une liste de mots n'en attrape qu'une partie :
# aucun filtre automatique ne remplace le signalement et le blocage, qui
# restent le vrai dispositif. Celui-ci écarte les insultes les plus directes,
# à moindre coût, et refuse à la publication plutôt que de masquer après coup.
import re
import unicodedata

# Injures et termes haineux les plus courants, français et anglais. Volontairement
# court : une liste longue multiplie les faux positifs (un titre de film, un nom
# propre) pour un gain marginal.
_TERMES = (
    "connard", "connasse", "enculé", "encule", "salope", "pute", "fdp",
    "bougnoule", "negre", "youpin", "pédé", "pede", "tapette", "tarlouze",
    "nique ta mere", "ntm", "sale juif", "sale arabe", "sale noir",
    # « retard » est écarté à dessein : mot français courant (« en retard »),
    # il produirait des faux positifs à chaque commentaire sur une diffusion.
    "nigger", "faggot", "kike", "tranny",
)

_MOTIFS = [re.compile(rf"(?<!\w){re.escape(t)}(?!\w)") for t in _TERMES]


def _normaliser(texte: str) -> str:
    """Minuscules, accents retirés, séparateurs réduits à l'espace.

    « C0nnard », « c-o-n-n-a-r-d » ou « Connard » doivent tomber sur la même
    entrée. Le contournement reste possible — c'est la limite de l'exercice.
    """
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", texte.lower())
        if unicodedata.category(c) != "Mn")
    substitutions = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a",
                                   "5": "s", "7": "t", "@": "a", "$": "s"})
    return re.sub(r"[\s._\-*]+", " ", sans_accents.translate(substitutions))


def contient_propos_interdits(texte: str | None) -> bool:
    if not texte:
        return False
    normalise = _normaliser(texte)
    return any(motif.search(normalise) for motif in _MOTIFS)
