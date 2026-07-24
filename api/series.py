# api/series.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.communs import recommandations, serie_ou_404, serie_par_reference
from api.dependances import client_tmdb, utilisateur_courant
from db.database import get_db
from models import Serie, SuivreSerie, Utilisateur
from schemas.plateformes import PlateformesVisionnage
from schemas.recherche import ResultatRecherche
from schemas.serie import SaisonAvecEpisodes, SeriePublique
from schemas.suivi import SuiviCreation, SuiviMaj, SuiviPublic
from schemas.visionnage import ProchainEpisode
from services import catalogue_service, visionnage_service
from services.tmdb_client import ClientTMDB

router = APIRouter()


def _suivi_ou_404(db: Session, utilisateur: Utilisateur, reference_tmdb: int) -> SuivreSerie:
    serie = serie_par_reference(db, reference_tmdb)
    suivi = serie and db.get(SuivreSerie, {"id_utilisateur": utilisateur.id_utilisateur,
                                           "id_serie": serie.id_serie})
    if not suivi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Série non suivie.")
    return suivi


@router.get("/{reference_tmdb}", response_model=SeriePublique)
async def fiche_serie(
    reference_tmdb: int,
    db: Session = Depends(get_db),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Fiche détaillée — servie du cache s'il est frais, sinon rafraîchie depuis TMDB."""
    serie = await catalogue_service.obtenir_serie(db, tmdb, reference_tmdb)
    if serie is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Série inconnue de TMDB.")
    return serie


@router.post("/{reference_tmdb}/suivre", response_model=SuiviPublic,
             status_code=status.HTTP_201_CREATED)
async def suivre_serie(
    reference_tmdb: int,
    donnees: SuiviCreation | None = None,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Suit une série : cache série + saisons + épisodes, puis crée la ligne de suivi."""
    donnees = donnees or SuiviCreation()

    serie = await catalogue_service.obtenir_serie(db, tmdb, reference_tmdb)
    if serie is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Série inconnue de TMDB.")

    deja = db.get(SuivreSerie, {"id_utilisateur": utilisateur.id_utilisateur,
                                "id_serie": serie.id_serie})
    if deja is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Série déjà suivie.")

    # le détail des épisodes n'est stocké que pour les séries suivies
    await catalogue_service.synchroniser_episodes(db, tmdb, serie)

    suivi = SuivreSerie(
        id_utilisateur=utilisateur.id_utilisateur,
        id_serie=serie.id_serie,
        statut_suivi=donnees.statut_suivi,
        favori=donnees.favori,
    )
    db.add(suivi)
    db.commit()
    db.refresh(suivi)
    return suivi


@router.patch("/{reference_tmdb}/suivre", response_model=SuiviPublic)
def modifier_suivi(
    reference_tmdb: int,
    donnees: SuiviMaj,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Change le statut de suivi et/ou le marquage favori."""
    suivi = _suivi_ou_404(db, utilisateur, reference_tmdb)
    if donnees.statut_suivi is not None:
        suivi.statut_suivi = donnees.statut_suivi
    if donnees.favori is not None:
        suivi.favori = donnees.favori
    db.commit()
    db.refresh(suivi)
    return suivi


@router.delete("/{reference_tmdb}/suivre", status_code=status.HTTP_204_NO_CONTENT)
def ne_plus_suivre(
    reference_tmdb: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Arrête le suivi — l'historique de visionnage est conservé."""
    suivi = _suivi_ou_404(db, utilisateur, reference_tmdb)
    db.delete(suivi)
    db.commit()


@router.get("/{reference_tmdb}/saisons", response_model=list[SaisonAvecEpisodes])
def saisons_serie(reference_tmdb: int, db: Session = Depends(get_db)):
    """Saisons et épisodes du cache (remplis dès qu'un utilisateur suit la série)."""
    return serie_ou_404(db, reference_tmdb).saisons


@router.get("/{reference_tmdb}/prochain-episode", response_model=ProchainEpisode | None)
def prochain_episode(
    reference_tmdb: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Premier épisode non vu (saisons spéciales exclues) ; null si tout est vu."""
    serie = serie_ou_404(db, reference_tmdb)
    ligne = visionnage_service.prochain_episode(db, utilisateur.id_utilisateur, serie.id_serie)
    if ligne is None:
        return None
    episode, num_saison = ligne
    return ProchainEpisode.depuis_episode(episode, num_saison)


@router.get("/{reference_tmdb}/similaires", response_model=list[ResultatRecherche])
async def series_similaires(
    reference_tmdb: int, tmdb: ClientTMDB = Depends(client_tmdb)
):
    """Recommandations TMDB pour cette série — rangée « Titres similaires »."""
    return await recommandations(tmdb, "tv", "serie", reference_tmdb)


@router.get("/{reference_tmdb}/plateformes", response_model=PlateformesVisionnage)
async def series_plateformes(
    reference_tmdb: int,
    pays: str = Query(default="FR", min_length=2, max_length=2),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Où regarder cette série (JustWatch via TMDB, attribution requise)."""
    return PlateformesVisionnage.depuis_tmdb(
        await tmdb.plateformes("tv", reference_tmdb), pays.upper())
