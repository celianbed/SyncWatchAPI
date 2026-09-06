# services/casting_service.py — distribution d'un titre, croisée avec l'historique.
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from models import (Acteur, CastingFilm, CastingSerie, Episode, Saison,
                    VisionnerEpisode, VisionnerFilm)
from schemas.casting import MembreCasting


def _series_vues_par_acteur(db: Session, id_utilisateur: int, ids_acteurs: list[int],
                            id_serie_exclue: int | None) -> dict[int, set[int]]:
    """Pour chaque acteur : les séries de son casting dont j'ai vu un épisode."""
    requete = (
        select(CastingSerie.id_acteur, CastingSerie.id_serie)
        .join(Saison, Saison.id_serie == CastingSerie.id_serie)
        .join(Episode, Episode.id_saison == Saison.id_saison)
        .join(VisionnerEpisode,
              and_(VisionnerEpisode.id_episode == Episode.id_episode,
                   VisionnerEpisode.id_utilisateur == id_utilisateur))
        .where(CastingSerie.id_acteur.in_(ids_acteurs))
        .distinct())
    if id_serie_exclue is not None:
        requete = requete.where(CastingSerie.id_serie != id_serie_exclue)

    vues: dict[int, set[int]] = {}
    for id_acteur, id_serie in db.execute(requete):
        vues.setdefault(id_acteur, set()).add(id_serie)
    return vues


def _films_vus_par_acteur(db: Session, id_utilisateur: int, ids_acteurs: list[int],
                          id_film_exclu: int | None) -> dict[int, set[int]]:
    requete = (
        select(CastingFilm.id_acteur, CastingFilm.id_film)
        .join(VisionnerFilm,
              and_(VisionnerFilm.id_film == CastingFilm.id_film,
                   VisionnerFilm.id_utilisateur == id_utilisateur))
        .where(CastingFilm.id_acteur.in_(ids_acteurs))
        .distinct())
    if id_film_exclu is not None:
        requete = requete.where(CastingFilm.id_film != id_film_exclu)

    vus: dict[int, set[int]] = {}
    for id_acteur, id_film in db.execute(requete):
        vus.setdefault(id_acteur, set()).add(id_film)
    return vus


def casting(db: Session, id_utilisateur: int, *, id_serie: int | None = None,
            id_film: int | None = None) -> list[MembreCasting]:
    """Distribution d'un titre, chaque personne portant le nombre d'autres
    titres de votre historique où elle joue.

    Trois requêtes au total, quel que soit le nombre d'acteurs : la
    distribution, puis les séries vues et les films vus, groupés d'un coup.
    """
    table = CastingSerie if id_serie is not None else CastingFilm
    colonne = table.id_serie if id_serie is not None else table.id_film
    cible = id_serie if id_serie is not None else id_film

    lignes = db.execute(
        select(Acteur, table.personnage)
        .join(table, table.id_acteur == Acteur.id_acteur)
        .where(colonne == cible)
        .order_by(table.ordre)).all()
    if not lignes:
        return []

    ids = [acteur.id_acteur for acteur, _ in lignes]
    series = _series_vues_par_acteur(db, id_utilisateur, ids, id_serie)
    films = _films_vus_par_acteur(db, id_utilisateur, ids, id_film)

    return [
        MembreCasting(
            id_acteur=acteur.id_acteur,
            nom=acteur.nom,
            photo=acteur.photo,
            personnage=personnage,
            deja_vu_dans=len(series.get(acteur.id_acteur, ()))
            + len(films.get(acteur.id_acteur, ())),
        )
        for acteur, personnage in lignes
    ]
