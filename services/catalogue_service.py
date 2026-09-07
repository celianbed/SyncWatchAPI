# services/catalogue_service.py — cache catalogue : upsert à la demande depuis TMDB
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.config import settings
from models import (Acteur, CastingFilm, CastingSerie, Episode, Film, Genre,
                    Saison, Serie, categoriser_film, categoriser_serie)
from services.tmdb_client import ClientTMDB


def _date_ou_none(valeur: str | None) -> date | None:
    # TMDB renvoie parfois "" au lieu d'omettre la date
    return date.fromisoformat(valeur) if valeur else None


def _est_frais(db: Session, date_maj: datetime) -> bool:
    # écart mesuré par l'horloge de la BDD (func.now()), pas datetime.now() du process :
    # un décalage de fuseau process/BDD fausserait sinon la fenêtre de fraîcheur.
    ecart = db.scalar(select(func.now() - date_maj))
    return ecart is not None and ecart < timedelta(hours=settings.DUREE_CACHE_HEURES)


def upsert_serie(db: Session, donnees: dict) -> Serie:
    """Insère ou rafraîchit une série (+ ses genres) depuis une fiche TMDB."""
    valeurs = {
        "reference_tmdb": donnees["id"],
        "titre": donnees.get("name") or "",
        "titre_original": donnees.get("original_name"),
        "synopsis": donnees.get("overview"),
        "affiche": donnees.get("poster_path"),
        "image_de_fond": donnees.get("backdrop_path"),
        "statut_diffusion": donnees.get("status"),
        "date_premiere_diffusion": _date_ou_none(donnees.get("first_air_date")),
        "note_moyenne_tmdb": donnees.get("vote_average"),
    }
    requete = insert(Serie).values(**valeurs).on_conflict_do_update(
        index_elements=["reference_tmdb"],
        set_={**valeurs, "date_maj_cache": func.now()},
    ).returning(Serie.id_serie)
    id_serie = db.scalar(requete)

    _associer_genres(db, categoriser_serie, "id_serie", id_serie, donnees.get("genres", []))
    _associer_casting(db, CastingSerie, "id_serie", id_serie, donnees.get("credits"))
    db.commit()
    return db.get(Serie, id_serie)


# On ne garde que les têtes d'affiche : au-delà, TMDB descend vers des rôles
# d'une réplique, sans intérêt pour la fiche ni pour le croisement « déjà vu ».
TETES_D_AFFICHE = 12


def _associer_casting(db: Session, table, colonne_cible: str, id_cible: int,
                      credits: dict | None) -> None:
    """Enregistre la distribution d'un titre, si TMDB l'a jointe à la fiche.

    Sans `append_to_response=credits`, `credits` est absent : on ne touche
    alors à rien, plutôt que d'effacer une distribution déjà connue.
    """
    if not credits:
        return
    classes = sorted(
        (p for p in credits.get("cast", []) if p.get("id") and p.get("name")),
        key=lambda p: p.get("order", 999))
    # TMDB liste la même personne plusieurs fois quand elle tient deux rôles
    # (jumeaux, anthologie, doublage d'animation) : sans déduplication, la
    # clé primaire (titre, acteur) est violée et toute la mise en cache échoue.
    # On garde la première occurrence, celle dont l'`order` est le meilleur.
    vus: set[int] = set()
    distribution = []
    for p in classes:
        if p["id"] not in vus:
            vus.add(p["id"])
            distribution.append(p)
        if len(distribution) == TETES_D_AFFICHE:
            break
    if not distribution:
        return

    db.execute(insert(Acteur).values([
        {"id_acteur": p["id"], "nom": p["name"], "photo": p.get("profile_path")}
        for p in distribution
    ]).on_conflict_do_update(
        index_elements=["id_acteur"],
        # sans quoi un nom corrigé chez TMDB (mariage, orthographe) resterait
        # figé à sa première insertion, contrairement aux fiches série et film
        set_={"nom": insert(Acteur).excluded.nom,
              "photo": insert(Acteur).excluded.photo}))

    # la distribution d'un titre peut changer (personnages renommés, ordre
    # revu) : on remplace plutôt que d'accumuler.
    db.execute(delete(table).where(getattr(table, colonne_cible) == id_cible))
    db.execute(insert(table).values([
        {colonne_cible: id_cible, "id_acteur": p["id"],
         "personnage": (p.get("character") or None), "ordre": p.get("order", 0)}
        for p in distribution
    ]))


def _associer_genres(db: Session, table_association, colonne_cible: str,
                     id_cible: int, genres: list[dict]) -> None:
    if not genres:
        return
    db.execute(insert(Genre).values(
        [{"id_genre": g["id"], "libelle": g["name"]} for g in genres]
    ).on_conflict_do_nothing(index_elements=["id_genre"]))
    db.execute(insert(table_association).values(
        [{colonne_cible: id_cible, "id_genre": g["id"]} for g in genres]
    ).on_conflict_do_nothing())


def upsert_film(db: Session, donnees: dict) -> Film:
    """Insère ou rafraîchit un film (+ ses genres) depuis une fiche TMDB."""
    valeurs = {
        "reference_tmdb": donnees["id"],
        "titre": donnees.get("title") or "",
        "titre_original": donnees.get("original_title"),
        "synopsis": donnees.get("overview"),
        "affiche": donnees.get("poster_path"),
        "duree": donnees.get("runtime"),
        "date_sortie": _date_ou_none(donnees.get("release_date")),
        "note_moyenne_tmdb": donnees.get("vote_average"),
    }
    requete = insert(Film).values(**valeurs).on_conflict_do_update(
        index_elements=["reference_tmdb"],
        set_={**valeurs, "date_maj_cache": func.now()},
    ).returning(Film.id_film)
    id_film = db.scalar(requete)

    _associer_genres(db, categoriser_film, "id_film", id_film, donnees.get("genres", []))
    _associer_casting(db, CastingFilm, "id_film", id_film, donnees.get("credits"))
    db.commit()
    return db.get(Film, id_film)


async def obtenir_film(db: Session, tmdb: ClientTMDB, reference_tmdb: int) -> Film | None:
    """Renvoie le film du cache si frais, sinon le (re)charge depuis TMDB."""
    film = db.scalar(select(Film).where(Film.reference_tmdb == reference_tmdb))
    if film is not None and _est_frais(db, film.date_maj_cache):
        return film
    donnees = await tmdb.get_film(reference_tmdb, append="credits")
    if donnees is None:
        return film
    return upsert_film(db, donnees)


async def obtenir_serie(db: Session, tmdb: ClientTMDB, reference_tmdb: int) -> Serie | None:
    """Renvoie la série du cache si fraîche, sinon la (re)charge depuis TMDB.

    Si TMDB ne connaît pas la référence : None (ou le cache périmé s'il existe).
    """
    serie = db.scalar(select(Serie).where(Serie.reference_tmdb == reference_tmdb))
    if serie is not None and _est_frais(db, serie.date_maj_cache):
        return serie
    donnees = await tmdb.get_serie(reference_tmdb, append="credits")
    if donnees is None:
        return serie
    return upsert_serie(db, donnees)


async def synchroniser_episodes(db: Session, tmdb: ClientTMDB, serie: Serie) -> None:
    """Upserte toutes les saisons et tous les épisodes d'une série.

    Appelé quand un utilisateur suit la série : c'est le seul cas où le détail
    des épisodes est nécessaire (tracking du visionnage, notifications).
    """
    detail = await tmdb.get_serie(serie.reference_tmdb)
    if detail is None:
        return

    for resume in detail.get("seasons", []):
        donnees_saison = await tmdb.get_saison(serie.reference_tmdb, resume["season_number"])
        if donnees_saison is None:
            continue

        valeurs_saison = {
            "id_serie": serie.id_serie,
            "reference_tmdb": resume["id"],
            "num_saison": resume["season_number"],
            "titre": donnees_saison.get("name"),
            "affiche": donnees_saison.get("poster_path"),
            "date_diffusion": _date_ou_none(donnees_saison.get("air_date")),
        }
        id_saison = db.scalar(insert(Saison).values(**valeurs_saison).on_conflict_do_update(
            index_elements=["reference_tmdb"], set_=valeurs_saison
        ).returning(Saison.id_saison))

        lignes = [{
            "id_saison": id_saison,
            "reference_tmdb": ep["id"],
            "num_episode": ep["episode_number"],
            "titre": ep.get("name"),
            "synopsis": ep.get("overview"),
            "duree": ep.get("runtime"),
            "date_diffusion": _date_ou_none(ep.get("air_date")),
            "vignette": ep.get("still_path"),
        } for ep in donnees_saison.get("episodes", [])]
        if lignes:
            requete = insert(Episode).values(lignes)
            db.execute(requete.on_conflict_do_update(
                index_elements=["reference_tmdb"],
                set_={colonne: requete.excluded[colonne] for colonne in (
                    "id_saison", "num_episode", "titre", "synopsis",
                    "duree", "date_diffusion", "vignette")},
            ))

    db.commit()
