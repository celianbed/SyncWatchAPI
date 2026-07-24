# api/communs.py — petites aides partagées par les routeurs.
# Factorise les répétitions : « récupérer par id ou 404 », contrôle de propriété,
# accès au cache par référence TMDB, et la rangée « similaires » identique entre
# séries et films.
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Film, Serie, Utilisateur
from schemas.recherche import ResultatRecherche
from services.tmdb_client import ClientTMDB

M = TypeVar("M")


def get_ou_404(db: Session, modele: type[M], cle, message: str) -> M:
    """Récupère une ligne par clé primaire (simple ou composite via dict), ou lève 404."""
    objet = db.get(modele, cle)
    if objet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, message)
    return objet


def du_proprietaire_ou_404(
    db: Session, modele: type[M], cle, utilisateur: Utilisateur, message: str
) -> M:
    """Comme get_ou_404, mais 404 aussi si la ligne appartient à un autre utilisateur.
    (404 plutôt que 403 : ne pas révéler l'existence de la ressource d'autrui.)"""
    objet = db.get(modele, cle)
    if objet is None or objet.id_utilisateur != utilisateur.id_utilisateur:
        raise HTTPException(status.HTTP_404_NOT_FOUND, message)
    return objet


def serie_par_reference(db: Session, reference_tmdb: int) -> Serie | None:
    """Série du cache par sa référence TMDB (None si absente)."""
    return db.scalar(select(Serie).where(Serie.reference_tmdb == reference_tmdb))


def film_par_reference(db: Session, reference_tmdb: int) -> Film | None:
    """Film du cache par sa référence TMDB (None si absent)."""
    return db.scalar(select(Film).where(Film.reference_tmdb == reference_tmdb))


def serie_ou_404(db: Session, reference_tmdb: int,
                 message: str = "Série absente du cache.") -> Serie:
    serie = serie_par_reference(db, reference_tmdb)
    if serie is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, message)
    return serie


async def recommandations(
    tmdb: ClientTMDB, media: str, type_cible: str, reference_tmdb: int
) -> list[ResultatRecherche]:
    """Rangée « Titres similaires ». media = "tv"|"movie", type_cible = "serie"|"film"."""
    donnees = await tmdb.similaires(media, reference_tmdb)
    return [ResultatRecherche.depuis_tmdb(brut, type_cible)
            for brut in (donnees or {}).get("results", [])]
