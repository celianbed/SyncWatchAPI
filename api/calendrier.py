# api/calendrier.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.dependances import utilisateur_courant
from db.database import get_db
from models import Utilisateur
from schemas.visionnage import CalendrierEntree, ProchainEpisode, SerieResume
from services import visionnage_service

router = APIRouter()


@router.get("/calendrier", response_model=list[CalendrierEntree])
def calendrier(
    jours: int = Query(default=14, ge=1, le=60,
                       description="Fenêtre en jours à partir d'aujourd'hui"),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Diffusions à venir (aujourd'hui inclus) des séries suivies actives,
    triées par date — alimente l'onglet Calendrier de l'app."""
    lignes = visionnage_service.calendrier(db, utilisateur.id_utilisateur, jours)
    return [CalendrierEntree(serie=SerieResume.model_validate(serie),
                             episode=ProchainEpisode.depuis_episode(episode, num_saison))
            for episode, num_saison, serie in lignes]
