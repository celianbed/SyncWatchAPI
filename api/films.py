# api/films.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.communs import film_par_reference, recommandations
from api.dependances import client_tmdb, utilisateur_courant
from db.database import get_db
from models import Film, SuivreFilm, Utilisateur, VisionnerFilm
from schemas.film import FilmPublic
from schemas.plateformes import PlateformesVisionnage
from schemas.casting import MembreCasting
from schemas.decouverte import BandeAnnonce
from schemas.recherche import ResultatRecherche
from schemas.suivi import SuiviFilmCreation, SuiviFilmPublic
from schemas.visionnage import EtatVisionnageFilm, FilmVu
from services import casting_service, catalogue_service, decouverte_service
from services.tmdb_client import ClientTMDB

router = APIRouter()


def _nombre_visionnages(db: Session, id_utilisateur: int, id_film: int) -> int:
    """Combien de fois l'utilisateur a vu ce film (0 si jamais)."""
    return db.scalar(select(func.count()).select_from(VisionnerFilm).where(
        VisionnerFilm.id_utilisateur == id_utilisateur,
        VisionnerFilm.id_film == id_film))


@router.get("/{reference_tmdb}", response_model=FilmPublic)
async def fiche_film(
    reference_tmdb: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
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
    film = film_par_reference(db, reference_tmdb)
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

    # clock_timestamp() : horloge réelle de la BDD (avance dans la transaction,
    # contrairement à now() figé → pas de collision de PK sur deux visionnages),
    # et surtout même horloge que les épisodes → regroupement cohérent dans les stats.
    visionnage = VisionnerFilm(id_utilisateur=utilisateur.id_utilisateur,
                               id_film=film.id_film,
                               date_visionnage=func.clock_timestamp())
    db.add(visionnage)

    suivi = db.get(SuivreFilm, {"id_utilisateur": utilisateur.id_utilisateur,
                                "id_film": film.id_film})
    if suivi is not None:
        suivi.statut = "vu"
    db.commit()

    nombre = _nombre_visionnages(db, utilisateur.id_utilisateur, film.id_film)
    return FilmVu(id_film=film.id_film, date_visionnage=visionnage.date_visionnage,
                  nombre_visionnages=nombre)


@router.get("/{reference_tmdb}/vu", response_model=EtatVisionnageFilm)
def etat_visionnage_film(
    reference_tmdb: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Le film a-t-il déjà été vu par l'utilisateur courant ? (bouton « Vu » de la fiche)"""
    film = film_par_reference(db, reference_tmdb)
    if film is None:  # pas encore en cache = jamais vu, jamais mis de côté
        return EtatVisionnageFilm(deja_vu=False, nombre_visionnages=0)
    nombre = _nombre_visionnages(db, utilisateur.id_utilisateur, film.id_film)
    suivi = db.get(SuivreFilm, {"id_utilisateur": utilisateur.id_utilisateur,
                                "id_film": film.id_film})
    return EtatVisionnageFilm(
        deja_vu=nombre > 0, nombre_visionnages=nombre,
        dans_a_voir=suivi is not None and suivi.statut == "a_voir")


@router.get("/{reference_tmdb}/similaires", response_model=list[ResultatRecherche])
async def films_similaires(
    reference_tmdb: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Recommandations TMDB pour ce film — rangée « Titres similaires »."""
    return await recommandations(tmdb, "movie", "film", reference_tmdb)


@router.get("/{reference_tmdb}/plateformes", response_model=PlateformesVisionnage)
async def films_plateformes(
    reference_tmdb: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    pays: str = Query(default="FR", min_length=2, max_length=2),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Où regarder ce film (JustWatch via TMDB, attribution requise)."""
    return PlateformesVisionnage.depuis_tmdb(
        await tmdb.plateformes("movie", reference_tmdb), pays.upper())


@router.get("/{reference_tmdb}/bande-annonce", response_model=BandeAnnonce)
async def films_bande_annonce(
    reference_tmdb: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Meilleure bande-annonce YouTube — 404 si le titre n'en a aucune.

    Réutilise le classement du feed « Extraits » (Trailer > Teaser > Clip,
    officiel d'abord, VF avant VO) pour que les deux montrent la même vidéo.
    """
    cles = decouverte_service.candidats_youtube(
        await tmdb.videos("movie", reference_tmdb))
    if not cles:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Aucune bande-annonce disponible.")
    return BandeAnnonce(cle_youtube=cles[0])


@router.get("/{reference_tmdb}/casting", response_model=list[MembreCasting])
def casting_film(
    reference_tmdb: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Têtes d'affiche, chacune portant le nombre d'autres titres déjà vus où
    elle joue — la liste seule est dans TMDB, ce croisement n'est qu'ici."""
    film = film_par_reference(db, reference_tmdb)
    if film is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Film absent du cache.")
    return casting_service.casting(db, utilisateur.id_utilisateur,
                                   id_film=film.id_film)
