# core/config.py
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinelle : clé de signature non configurée (l'app refuse de démarrer avec, cf. main.py)
SECRET_KEY_PAR_DEFAUT = "dev-uniquement-a-remplacer"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # .env à la racine du dépôt, quel que soit le répertoire d'exécution
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
    )

    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/syncwatch"

    @field_validator("DATABASE_URL")
    @classmethod
    def normaliser_schema_postgres(cls, v: str) -> str:
        # certains hébergeurs fournissent "postgres://", refusé par SQLAlchemy 2
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v

    # JWT — SECRET_KEY à définir dans .env, jamais committée.
    # Si elle reste à la valeur par défaut, l'application refuse de démarrer (voir main.py).
    SECRET_KEY: str = SECRET_KEY_PAR_DEFAUT
    ALGORITHME_JWT: str = "HS256"
    
    DUREE_JETON_MINUTES: int = 60 * 24 * 7  # 7 jours : app mobile, pas de refresh token pour l'instant

    # Documentation interactive : pratique en dev, à couper en prod (DOCS_ACTIVES=false
    # sur Render) pour ne pas exposer publiquement le schéma complet de l'API.
    DOCS_ACTIVES: bool = True

    # TMDB — jeton d'accès en lecture (v4) à définir dans .env
    TMDB_API_TOKEN: str = ""
    TMDB_URL_BASE: str = "https://api.themoviedb.org/3"
    TMDB_LANGUE: str = "fr-FR"
    DUREE_CACHE_HEURES: int = 24  # fraîcheur du cache catalogue

    # Limitation de débit (anti brute-force / email bombing) — False dans les tests
    RATE_LIMIT_ACTIF: bool = True

    # Notifications — scan quotidien des diffusions
    NOTIFICATIONS_PLANIFIEES: bool = True  # False dans les tests
    HEURE_SCAN_NOTIFICATIONS: int = 8  # heure locale du job
    # Push FCM (Android) : JSON du compte de service Firebase. Vide = pas de push (mode journal).
    FIREBASE_CREDENTIALS_JSON: str = ""

    # Connexion Google : ID du client OAuth « Web » (audience du id_token à vérifier).
    GOOGLE_CLIENT_ID: str = ""

    # Suivi d'erreurs Sentry (vide = désactivé). DSN à définir en prod.
    SENTRY_DSN: str = ""
    SENTRY_ENV: str = "production"

    # Secret exigé par /taches/* (déclenchement par un cron externe en prod)
    CRON_SECRET: str = ""

    # Vérification d'adresse mail
    URL_BASE_API: str = "http://localhost:8000"  # sert à construire le lien de vérification
    DUREE_JETON_VERIF_HEURES: int = 48
    DUREE_JETON_RESET_MINUTES: int = 30  # lien « mot de passe oublié » : court par sécurité
    MAIL_EXPEDITEUR: str = "no-reply@syncwatch.app"  # « From » des mails (validé chez Brevo)

    # Envoi via l'API HTTP de Brevo (port 443) — recommandé sur Render/PaaS qui filtrent le SMTP.
    # Prioritaire sur le SMTP si renseigné. Clé « xkeysib-… » (SMTP & API → API Keys).
    BREVO_API_KEY: str = ""

    # SMTP — repli / dev local. Laissé vide : les mails sont alors seulement journalisés.
    SMTP_HOTE: str = ""
    SMTP_PORT: int = 587
    SMTP_UTILISATEUR: str = ""
    SMTP_MOT_DE_PASSE: str = ""
    SMTP_TLS: bool = True  # STARTTLS


settings = Settings()
