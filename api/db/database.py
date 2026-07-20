# api/db/database.py
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from api.core.config import settings


class Base(DeclarativeBase):
    pass


# pool_pre_ping + pool_recycle : Neon (serverless) coupe les connexions inactives,
# on les vérifie avant usage et on les renouvelle avant qu'elles n'expirent
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """Dépendance FastAPI : fournit une session fermée en fin de requête."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
