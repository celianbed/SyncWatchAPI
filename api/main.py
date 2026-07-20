# api/main.py
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.api import (accueil, auth, avis, calendrier, films, notifications,
                     recherche, series, stats, taches, utilisateurs, visionnage)
from api.core.config import settings
from api.db.database import get_db
from api.services import notification_service
from api.services.tmdb_client import ClientTMDB


@asynccontextmanager
async def lifespan(app: FastAPI):
    # un seul client TMDB pour toute la vie de l'app (réutilise les connexions)
    app.state.tmdb = ClientTMDB()

    planificateur = None
    if settings.NOTIFICATIONS_PLANIFIEES:
        planificateur = BackgroundScheduler()
        planificateur.add_job(notification_service.job_quotidien, "cron",
                              hour=settings.HEURE_SCAN_NOTIFICATIONS, minute=0)
        planificateur.start()

    yield

    if planificateur is not None:
        planificateur.shutdown(wait=False)
    await app.state.tmdb.fermer()


app = FastAPI(
    title="SyncWatch API",
    description="Suivi de séries et de films : historique de visionnage, avis, notifications de sortie.",
    version="0.1.0",
    lifespan=lifespan,
)

# En dev : tout autoriser. À restreindre aux domaines du front en production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["sante"])
def racine():
    return {"application": "SyncWatch", "documentation": "/docs"}


@app.get("/health", tags=["sante"])
def health(db: Session = Depends(get_db)):
    """Vérifie que l'API répond et que la base de données est joignable."""
    db.execute(text("SELECT 1"))
    return {"statut": "ok", "base_de_donnees": "accessible"}


app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(utilisateurs.router, prefix="/utilisateurs", tags=["utilisateurs"])
app.include_router(recherche.router, prefix="/search", tags=["recherche"])
app.include_router(series.router, prefix="/series", tags=["series"])
app.include_router(films.router, prefix="/films", tags=["films"])
app.include_router(visionnage.router, tags=["visionnage"])
app.include_router(accueil.router, tags=["accueil"])
app.include_router(calendrier.router, tags=["calendrier"])
app.include_router(avis.router, prefix="/avis", tags=["avis"])
app.include_router(stats.router, prefix="/stats", tags=["stats"])
app.include_router(notifications.router, tags=["notifications"])
app.include_router(taches.router, prefix="/taches", tags=["taches"])
