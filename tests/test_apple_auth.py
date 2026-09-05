# tests/test_apple_auth.py — vérification du jeton d'identité Apple.
# Aucune base, aucun réseau : on joue le rôle d'Apple avec une paire de clés locale.
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk, jwt

from services import apple_auth

BUNDLE = "com.syncwatch.syncwatchMobile"


def _paire_rsa():
    prive = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_prive = prive.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    pem_public = prive.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return pem_prive, pem_public


def _jwk(pem_public, kid):
    cle = jwk.construct(pem_public, algorithm="RS256").to_dict()
    # jose renvoie n/e en bytes : le jeu de clés d'Apple, lui, est du JSON
    cle = {c: (v.decode() if isinstance(v, bytes) else v) for c, v in cle.items()}
    return {**cle, "kid": kid}


@pytest.fixture()
def cle_apple(monkeypatch):
    """Publie une clé « Apple » locale et interdit tout appel réseau."""
    pem_prive, pem_public = _paire_rsa()
    monkeypatch.setattr(apple_auth, "_cles", [_jwk(pem_public, "cle-test")])
    monkeypatch.setattr(apple_auth, "_recuperer_cles",
                        lambda: pytest.fail("aucun appel réseau ne doit partir"))
    return pem_prive


def _jeton(pem_prive, kid="cle-test", **surcharges):
    charge = {"iss": apple_auth.EMETTEUR, "aud": BUNDLE, "sub": "001.abc",
              "iat": int(time.time()), "exp": int(time.time()) + 600,
              "email": "lea@icloud.com", "email_verified": "true"}
    charge.update(surcharges)
    return jwt.encode(charge, pem_prive, algorithm="RS256", headers={"kid": kid})


def test_jeton_valide(cle_apple):
    infos = apple_auth.verifier_token_apple(_jeton(cle_apple), BUNDLE)
    assert infos["sub"] == "001.abc"
    assert infos["email"] == "lea@icloud.com"


def test_audience_d_une_autre_app_refusee(cle_apple):
    # un jeton Apple valide mais émis pour une AUTRE app ne doit pas ouvrir de session
    with pytest.raises(ValueError):
        apple_auth.verifier_token_apple(_jeton(cle_apple, aud="com.autre.app"), BUNDLE)


def test_emetteur_usurpe_refuse(cle_apple):
    with pytest.raises(ValueError):
        apple_auth.verifier_token_apple(
            _jeton(cle_apple, iss="https://pas-apple.example"), BUNDLE)


def test_jeton_expire_refuse(cle_apple):
    with pytest.raises(ValueError):
        apple_auth.verifier_token_apple(
            _jeton(cle_apple, exp=int(time.time()) - 60), BUNDLE)


def test_signature_forgee_refusee(cle_apple):
    # jeton signé avec une autre clé, mais annoncé sous le « kid » d'Apple
    pem_intrus, _ = _paire_rsa()
    with pytest.raises(ValueError):
        apple_auth.verifier_token_apple(_jeton(pem_intrus), BUNDLE)


def test_jeton_illisible_refuse(cle_apple):
    with pytest.raises(ValueError):
        apple_auth.verifier_token_apple("pas-un-jwt", BUNDLE)


def test_revocation_sautee_sans_cle(monkeypatch):
    # sans clé Sign in with Apple configurée : pas d'appel, pas d'exception
    monkeypatch.setattr(apple_auth.settings, "APPLE_TEAM_ID", "")
    assert apple_auth.revocation_configuree() is False
    assert apple_auth.revoquer("un-jeton") is False
