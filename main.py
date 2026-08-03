# main.py
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from api import (accueil, activite, auth, avis, calendrier, decouverte, films,
                     notifications, recherche, series, stats, taches,
                     utilisateurs, visionnage)
from core.config import SECRET_KEY_PAR_DEFAUT, settings
from core.limitation import brancher_limitation

# Suivi d'erreurs : à initialiser AVANT la création de l'app (sinon inactif).
if settings.SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(dsn=settings.SENTRY_DSN, environment=settings.SENTRY_ENV,
                    traces_sample_rate=0.1, send_default_pii=False)
from db.database import get_db
from services import notification_service
from services.tmdb_client import ClientTMDB


@asynccontextmanager
async def lifespan(app: FastAPI):

    # Refus de démarrer avec la clé de signature par défaut : elle est publique
    # (dans le dépôt), donc n'importe qui pourrait forger un jeton d'accès.
    if settings.SECRET_KEY == SECRET_KEY_PAR_DEFAUT:
        raise RuntimeError(
            "SECRET_KEY non configurée : définissez-la dans .env (local) ou dans "
            "les variables d'environnement (production).")

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
    # En prod (DOCS_ACTIVES=false) : pas de /docs, /redoc ni /openapi.json exposés.
    docs_url="/docs" if settings.DOCS_ACTIVES else None,
    redoc_url="/redoc" if settings.DOCS_ACTIVES else None,
    openapi_url="/openapi.json" if settings.DOCS_ACTIVES else None,
)

# En dev : tout autoriser. À restreindre aux domaines du front en production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Limitation de débit : renvoie 429 au-delà des quotas (cf. core/limitation.py)
brancher_limitation(app)


@app.api_route("/", methods=["GET", "HEAD"], tags=["sante"])
def racine():
    reponse = {"application": "SyncWatch"}
    if settings.DOCS_ACTIVES:
        reponse["documentation"] = "/docs"
    return reponse


@app.get("/health", tags=["sante"])
def health(db: Session = Depends(get_db)):
    """Vérifie que l'API répond et que la base de données est joignable."""
    db.execute(text("SELECT 1"))
    return {"statut": "ok", "base_de_donnees": "accessible"}


app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(utilisateurs.router, prefix="/utilisateurs", tags=["utilisateurs"])
app.include_router(recherche.router, prefix="/search", tags=["recherche"])
app.include_router(decouverte.router, prefix="/decouverte", tags=["decouverte"])
app.include_router(activite.router, prefix="/activite", tags=["activite"])
app.include_router(series.router, prefix="/series", tags=["series"])
app.include_router(films.router, prefix="/films", tags=["films"])
app.include_router(visionnage.router, tags=["visionnage"])
app.include_router(accueil.router, tags=["accueil"])
app.include_router(calendrier.router, tags=["calendrier"])
app.include_router(avis.router, prefix="/avis", tags=["avis"])
app.include_router(stats.router, prefix="/stats", tags=["stats"])
app.include_router(notifications.router, tags=["notifications"])
app.include_router(taches.router, prefix="/taches", tags=["taches"])
