# api/api/films.py
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.api.dependances import client_tmdb, utilisateur_courant
from api.db.database import get_db
from api.models import Film, SuivreFilm, Utilisateur, VisionnerFilm
from api.schemas.film import FilmPublic
from api.schemas.plateformes import PlateformesVisionnage
from api.schemas.recherche import ResultatRecherche
from api.schemas.suivi import SuiviFilmCreation, SuiviFilmPublic
from api.schemas.visionnage import FilmVu
from api.services import catalogue_service
from api.services.tmdb_client import ClientTMDB

router = APIRouter()


@router.get("/{reference_tmdb}", response_model=FilmPublic)
async def fiche_film(
    reference_tmdb: int,
    db: Session = Depends(get_db),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Fiche détaillée — servie du cache s'il est frais, sinon rafraîchie depuis TMDB."""
    film = await catalogue_service.obtenir_film(db, tmdb, reference_tmdb)
    if film is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Film inconnu de TMDB.")
    return film


@router.post("/{reference_tmdb}/suivre", response_model=SuiviFilmPublic,
             status_code=status.HTTP_201_CREATED)
async def suivre_film(
    reference_tmdb: int,
    donnees: SuiviFilmCreation | None = None,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    donnees = donnees or SuiviFilmCreation()

    film = await catalogue_service.obtenir_film(db, tmdb, reference_tmdb)
    if film is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Film inconnu de TMDB.")

    deja = db.get(SuivreFilm, {"id_utilisateur": utilisateur.id_utilisateur,
                               "id_film": film.id_film})
    if deja is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Film déjà suivi.")

    suivi = SuivreFilm(id_utilisateur=utilisateur.id_utilisateur, id_film=film.id_film,
                       statut=donnees.statut, favori=donnees.favori)
    db.add(suivi)
    db.commit()
    db.refresh(suivi)
    return suivi


@router.delete("/{reference_tmdb}/suivre", status_code=status.HTTP_204_NO_CONTENT)
def ne_plus_suivre_film(
    reference_tmdb: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    film = db.scalar(select(Film).where(Film.reference_tmdb == reference_tmdb))
    suivi = film and db.get(SuivreFilm, {"id_utilisateur": utilisateur.id_utilisateur,
                                         "id_film": film.id_film})
    if not suivi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Film non suivi.")
    db.delete(suivi)
    db.commit()


@router.post("/{reference_tmdb}/vu", response_model=FilmVu,
             status_code=status.HTTP_201_CREATED)
async def marquer_film_vu(
    reference_tmdb: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Chaque appel enregistre un visionnage : revoir un film est possible."""
    film = await catalogue_service.obtenir_film(db, tmdb, reference_tmdb)
    if film is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Film inconnu de TMDB.")

    # horodatage côté Python : now() SQL est figé par transaction, ce qui
    # empêcherait deux visionnages dans la même transaction (PK composite)
    visionnage = VisionnerFilm(id_utilisateur=utilisateur.id_utilisateur,
                               id_film=film.id_film, date_visionnage=datetime.now())
    db.add(visionnage)

    suivi = db.get(SuivreFilm, {"id_utilisateur": utilisateur.id_utilisateur,
                                "id_film": film.id_film})
    if suivi is not None:
        suivi.statut = "vu"
    db.commit()

    nombre = db.scalar(select(func.count()).select_from(VisionnerFilm).where(
        VisionnerFilm.id_utilisateur == utilisateur.id_utilisateur,
        VisionnerFilm.id_film == film.id_film))
    return FilmVu(id_film=film.id_film, date_visionnage=visionnage.date_visionnage,
                  nombre_visionnages=nombre)


@router.get("/{reference_tmdb}/similaires", response_model=list[ResultatRecherche])
async def films_similaires(
    reference_tmdb: int, tmdb: ClientTMDB = Depends(client_tmdb)
):
    """Recommandations TMDB pour ce film — rangée « Titres similaires »."""
    donnees = await tmdb.similaires("movie", reference_tmdb)
    return [ResultatRecherche.depuis_tmdb(brut, "film")
            for brut in (donnees or {}).get("results", [])]


@router.get("/{reference_tmdb}/plateformes", response_model=PlateformesVisionnage)
async def films_plateformes(
    reference_tmdb: int,
    pays: str = Query(default="FR", min_length=2, max_length=2),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Où regarder ce film (JustWatch via TMDB, attribution requise)."""
    return PlateformesVisionnage.depuis_tmdb(
        await tmdb.plateformes("movie", reference_tmdb), pays.upper())
