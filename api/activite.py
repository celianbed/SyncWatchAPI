# api/activite.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.dependances import utilisateur_courant
from db.database import get_db
from models import Utilisateur
from schemas.activite import EvenementActivite
from services import social_service

router = APIRouter()


@router.get("", response_model=list[EvenementActivite])
def fil_activite(
    limite: int = Query(40, ge=1, le=100),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Fil d'activité des personnes suivies : avis, films vus, séries suivies."""
    return social_service.fil_activite(db, utilisateur.id_utilisateur, limite)
