# api/accueil.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependances import utilisateur_courant
from db.database import get_db
from models import Utilisateur
from schemas.visionnage import AccueilEntree, ProchainEpisode, SerieResume
from services import visionnage_service

router = APIRouter()


@router.get("/accueil", response_model=list[AccueilEntree])
def accueil(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """« À regarder ce soir » : prochain épisode diffusé de chaque série suivie active."""
    lignes = visionnage_service.accueil(db, utilisateur.id_utilisateur)
    return [AccueilEntree(serie=SerieResume.model_validate(serie),
                          episode=ProchainEpisode.depuis_episode(episode, num_saison))
            for episode, num_saison, serie in lignes]
