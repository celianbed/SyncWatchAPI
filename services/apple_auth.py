# services/apple_auth.py — vérification du jeton d'identité Sign in with Apple
"""Contrairement à Google, aucune bibliothèque officielle ne fait la vérification :
on récupère les clés publiques d'Apple (JWKS) et on valide le JWT nous-mêmes.
"""
import logging
import threading
import time

import httpx
from jose import jwt
from jose.exceptions import JWTError

from core.config import settings

URL_CLES = "https://appleid.apple.com/auth/keys"
URL_JETON = "https://appleid.apple.com/auth/token"
URL_REVOCATION = "https://appleid.apple.com/auth/revoke"
EMETTEUR = "https://appleid.apple.com"

journal = logging.getLogger(__name__)

# Les clés d'Apple changent rarement : on les garde en mémoire et on ne les
# rafraîchit que si le "kid" du jeton reçu est inconnu (rotation de clé).
_cles: list[dict] = []
_verrou = threading.Lock()


def _recuperer_cles() -> list[dict]:
    reponse = httpx.get(URL_CLES, timeout=10)
    reponse.raise_for_status()
    return reponse.json()["keys"]


def _cle_pour(kid: str) -> dict:
    """Clé publique Apple d'identifiant `kid`, en rechargeant le jeu si besoin."""
    global _cles
    with _verrou:
        cle = next((c for c in _cles if c["kid"] == kid), None)
        if cle is None:  # jeu vide au démarrage, ou clé tournée par Apple
            _cles = _recuperer_cles()
            cle = next((c for c in _cles if c["kid"] == kid), None)
    if cle is None:
        raise ValueError(f"clé Apple inconnue ({kid})")
    return cle


def verifier_token_apple(identity_token: str, audience: str) -> dict:
    """Vérifie signature, émetteur, audience et expiration. ValueError si invalide.

    `audience` = identifiant du bundle iOS (ce que l'app a demandé à Apple).
    """
    try:
        kid = jwt.get_unverified_header(identity_token)["kid"]
    except (JWTError, KeyError) as e:
        raise ValueError(f"en-tête de jeton Apple illisible : {e}") from e

    try:

        claims = jwt.get_unverified_claims(identity_token)
        print(f"[DEBUG] aud reçu: {claims.get('aud')} | attendu: {audience}")
        print(f"[DEBUG] iss reçu: {claims.get('iss')} | attendu: {EMETTEUR}")
        
        return jwt.decode(identity_token, _cle_pour(kid), algorithms=["RS256"],
                          audience=audience, issuer=EMETTEUR)

        
    except JWTError as e:
        raise ValueError(f"jeton Apple invalide : {e}") from e
    except httpx.HTTPError as e:  # Apple injoignable : ne pas laisser fuiter en 500
        raise ValueError(f"clés Apple indisponibles : {e}") from e


# --- Révocation (exigée par Apple à la suppression d'un compte) ------------------


def revocation_configuree() -> bool:
    """La clé Sign in with Apple est-elle fournie ? Sinon on saute la révocation."""
    return bool(settings.APPLE_TEAM_ID and settings.APPLE_KEY_ID
                and settings.APPLE_PRIVATE_KEY)


def _secret_client() -> str:
    """« client_secret » attendu par Apple : un JWT court signé (ES256) avec le .p8."""
    maintenant = int(time.time())
    return jwt.encode(
        {"iss": settings.APPLE_TEAM_ID, "iat": maintenant, "exp": maintenant + 300,
         "aud": EMETTEUR, "sub": settings.APPLE_BUNDLE_ID},
        settings.APPLE_PRIVATE_KEY, algorithm="ES256",
        headers={"kid": settings.APPLE_KEY_ID})


def echanger_code(code: str) -> str | None:
    """Échange le code d'autorisation contre un jeton de rafraîchissement, seule
    chose qui permettra plus tard de révoquer l'accès. None si indisponible.

    Un échec n'est jamais bloquant : la connexion, elle, ne dépend que du jeton
    d'identité déjà vérifié.
    """
    if not revocation_configuree():
        return None
    try:
        reponse = httpx.post(URL_JETON, timeout=10, data={
            "client_id": settings.APPLE_BUNDLE_ID,
            "client_secret": _secret_client(),
            "code": code,
            "grant_type": "authorization_code"})
        reponse.raise_for_status()
        return reponse.json().get("refresh_token")
    except (httpx.HTTPError, JWTError, ValueError) as e:
        journal.warning("Apple : échange du code impossible (%s)", e)
        return None


def revoquer(jeton_rafraichissement: str) -> bool:
    """Révoque l'accès Apple d'un compte supprimé. False si ça n'a pas pu se faire."""
    if not revocation_configuree():
        journal.warning("Apple : révocation sautée (clé Sign in with Apple absente)")
        return False
    try:
        reponse = httpx.post(URL_REVOCATION, timeout=10, data={
            "client_id": settings.APPLE_BUNDLE_ID,
            "client_secret": _secret_client(),
            "token": jeton_rafraichissement,
            "token_type_hint": "refresh_token"})
        reponse.raise_for_status()
        return True
    except (httpx.HTTPError, JWTError) as e:
        journal.warning("Apple : révocation impossible (%s)", e)
        return False
