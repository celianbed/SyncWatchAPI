# api/taches.py — tâches déclenchées par un cron externe (cron-job.org, etc.)
#
# En hébergement gratuit (Render), le service s'endort : APScheduler ne peut pas
# garantir le job de 8 h. Un cron externe appelle ces endpoints à la place,
# authentifié par le header X-Cron-Secret.
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from api.dependances import client_tmdb
from core.config import settings
from db.database import get_db
from services import notification_service
from services.tmdb_client import ClientTMDB

router = APIRouter()


def verifier_secret(x_cron_secret: str = Header(default="")) -> None:
    if not settings.CRON_SECRET:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "CRON_SECRET non configuré.")
    if not hmac.compare_digest(x_cron_secret, settings.CRON_SECRET):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Secret invalide.")


@router.post("/scan-diffusions", dependencies=[Depends(verifier_secret)])
async def scan_diffusions(
    db: Session = Depends(get_db),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Pipeline quotidien : resynchronise le cache des séries suivies,
    puis crée et pousse les notifications des épisodes diffusés aujourd'hui."""
    series = await notification_service.resynchroniser_series_suivies(db, tmdb)
    notifications = notification_service.scanner_diffusions_du_jour(
        db, notification_service.PousseurJournal())
    return {"series_resynchronisees": series, "notifications_creees": notifications}
