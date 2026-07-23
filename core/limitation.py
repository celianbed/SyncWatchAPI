# core/limitation.py — limitation de débit (anti brute-force / anti email bombing)
from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from core.config import settings

# Filet global appliqué à TOUTES les routes par SlowAPIMiddleware (y compris celles
# qu'on n'a pas décorées). Large pour un usage normal de l'app, mais coupe le
# martèlement automatisé.
LIMITE_GLOBALE = "120/minute"

# Clé = adresse IP de l'appelant. `enabled` permet de neutraliser la limitation
# dans les tests (settings.RATE_LIMIT_ACTIF = False, cf. conftest).
limiteur = Limiter(key_func=get_remote_address, enabled=settings.RATE_LIMIT_ACTIF,
                   default_limits=[LIMITE_GLOBALE])

# Quotas par endpoint sensible, exprimés en syntaxe slowapi.
#
# Connexion : doit rester compatible avec le sondage de l'app pendant l'attente de
# vérification (il appelle /auth/connexion toutes les 5 s, soit 12/min) — d'où la
# marge. 30/min coupe malgré tout le brute-force de plusieurs ordres de grandeur,
# d'autant que bcrypt rend chaque essai coûteux.
LIMITE_CONNEXION = "30/minute"      # brute-force de mots de passe
LIMITE_INSCRIPTION = "5/hour"       # création massive de comptes
LIMITE_ENVOI_MAIL = "3/hour"        # email bombing + quota Brevo
# Recherche : publique et non authentifiée, chaque appel coûte une requête TMDB
# (quota TMDB + CPU Render) → plus strict que le filet global.
LIMITE_RECHERCHE = "30/minute"


def brancher_limitation(app: FastAPI) -> None:
    """Branche la limitation sur l'application : réponse 429 au-delà des quotas.

    Le middleware applique LIMITE_GLOBALE à *toutes* les routes ; les décorateurs
    `@limiteur.limit(...)` posent en plus les quotas spécifiques.
    """
    app.state.limiter = limiteur
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
