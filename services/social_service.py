# services/social_service.py — logique du graphe social (abonnements / amitié).
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (Abonnement, Avis, Episode, Film, Saison, Serie,
                       SuivreFilm, SuivreSerie, Utilisateur)


def _comptes_par_user(db: Session, colonne_user, ids: list[int]) -> dict[int, int]:
    """{id_utilisateur: nombre de lignes} pour les utilisateurs `ids` (en un appel)."""
    if not ids:
        return {}
    lignes = db.execute(
        select(colonne_user, func.count()).where(colonne_user.in_(ids))
        .group_by(colonne_user)).all()
    return {uid: n for uid, n in lignes}


def resumes(db: Session, uid_courant: int, users: list[Utilisateur]) -> list[dict]:
    """ResumeUtilisateur (compteurs + relation) pour une liste — sans N+1."""
    ids = [u.id_utilisateur for u in users]
    nb_series = _comptes_par_user(db, SuivreSerie.id_utilisateur, ids)
    nb_films = _comptes_par_user(db, SuivreFilm.id_utilisateur, ids)
    # qui je suis / qui me suit, parmi ces utilisateurs
    je_suis = set(db.scalars(select(Abonnement.id_suivi).where(
        Abonnement.id_suiveur == uid_courant, Abonnement.id_suivi.in_(ids))).all())
    me_suivent = set(db.scalars(select(Abonnement.id_suiveur).where(
        Abonnement.id_suivi == uid_courant, Abonnement.id_suiveur.in_(ids))).all())

    resultats = []
    for u in users:
        uid = u.id_utilisateur
        abonne, suit = uid in je_suis, uid in me_suivent
        resultats.append({
            "id_utilisateur": uid,
            "pseudo": u.pseudo,
            "avatar": u.avatar,
            "nb_series": nb_series.get(uid, 0),
            "nb_films": nb_films.get(uid, 0),
            "est_abonne": abonne,
            "me_suit": suit,
            "est_ami": abonne and suit,
        })
    return resultats


def avis_profil(db: Session, id_utilisateur: int, limite: int = 10) -> list[dict]:
    """Derniers avis d'un utilisateur, avec titre résolu (série/film/épisode)."""
    avis = db.scalars(
        select(Avis).where(Avis.id_utilisateur == id_utilisateur)
        .order_by(Avis.date_creation.desc()).limit(limite)).all()

    ids_serie = {a.id_serie for a in avis if a.id_serie}
    ids_film = {a.id_film for a in avis if a.id_film}
    ids_episode = {a.id_episode for a in avis if a.id_episode}

    series, films, episodes = {}, {}, {}
    if ids_serie:
        for sid, titre, ref in db.execute(select(
                Serie.id_serie, Serie.titre, Serie.reference_tmdb)
                .where(Serie.id_serie.in_(ids_serie))).all():
            series[sid] = (titre, ref)
    if ids_film:
        for fid, titre, ref in db.execute(select(
                Film.id_film, Film.titre, Film.reference_tmdb)
                .where(Film.id_film.in_(ids_film))).all():
            films[fid] = (titre, ref)
    if ids_episode:
        for eid, num_ep, num_sai, titre, ref in db.execute(
                select(Episode.id_episode, Episode.num_episode, Saison.num_saison,
                       Serie.titre, Serie.reference_tmdb)
                .join(Saison, Episode.id_saison == Saison.id_saison)
                .join(Serie, Saison.id_serie == Serie.id_serie)
                .where(Episode.id_episode.in_(ids_episode))).all():
            code = f"S{num_sai:02d}E{num_ep:02d}"
            episodes[eid] = (f"{titre} · {code}", ref)

    resultats = []
    for a in avis:
        if a.id_serie in series:
            titre, ref, type_ = *series[a.id_serie], "serie"
        elif a.id_film in films:
            titre, ref, type_ = *films[a.id_film], "film"
        elif a.id_episode in episodes:
            titre, ref, type_ = *episodes[a.id_episode], "episode"
        else:
            continue  # cible absente du cache (rare)
        resultats.append({
            "id_avis": a.id_avis, "titre": titre, "type": type_,
            "reference_tmdb": ref, "note": a.note, "date_creation": a.date_creation,
        })
    return resultats


def profil_detaille(db: Session, uid_courant: int, cible: Utilisateur) -> dict:
    """Profil public détaillé (compteurs abonnés/abonnements/séries + relation)."""
    cid = cible.id_utilisateur
    nb_abonnes = db.scalar(select(func.count()).select_from(Abonnement)
                           .where(Abonnement.id_suivi == cid))
    nb_abonnements = db.scalar(select(func.count()).select_from(Abonnement)
                               .where(Abonnement.id_suiveur == cid))
    nb_series = db.scalar(select(func.count()).select_from(SuivreSerie)
                          .where(SuivreSerie.id_utilisateur == cid))
    est_abonne = db.get(
        Abonnement, {"id_suiveur": uid_courant, "id_suivi": cid}) is not None
    me_suit = db.get(
        Abonnement, {"id_suiveur": cid, "id_suivi": uid_courant}) is not None
    return {
        "id_utilisateur": cid,
        "pseudo": cible.pseudo,
        "avatar": cible.avatar,
        "date_inscription": cible.date_inscription,
        "nb_abonnes": nb_abonnes,
        "nb_abonnements": nb_abonnements,
        "nb_series": nb_series,
        "est_abonne": est_abonne,
        "me_suit": me_suit,
        "est_ami": est_abonne and me_suit,
    }
