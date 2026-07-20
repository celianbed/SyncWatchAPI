# api/core/config.py
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # .env à la racine de api/, quel que soit le répertoire d'exécution
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

    # JWT — SECRET_KEY à définir dans .env, jamais committée
    SECRET_KEY: str = "dev-uniquement-a-remplacer"
    ALGORITHME_JWT: str = "HS256"
    
    DUREE_JETON_MINUTES: int = 60 * 24 * 7  # 7 jours : app mobile, pas de refresh token pour l'instant

    # TMDB — jeton d'accès en lecture (v4) à définir dans .env
    TMDB_API_TOKEN: str = ""
    TMDB_URL_BASE: str = "https://api.themoviedb.org/3"
    TMDB_LANGUE: str = "fr-FR"
    DUREE_CACHE_HEURES: int = 24  # fraîcheur du cache catalogue

    # Notifications — scan quotidien des diffusions
    NOTIFICATIONS_PLANIFIEES: bool = True  # False dans les tests
    HEURE_SCAN_NOTIFICATIONS: int = 8  # heure locale du job

    # Secret exigé par /taches/* (déclenchement par un cron externe en prod)
    CRON_SECRET: str = ""


settings = Settings()
