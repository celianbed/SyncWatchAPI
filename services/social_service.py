# services/social_service.py — logique du graphe social (abonnements / amitié).
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (Abonnement, Avis, Episode, Film, Saison, Serie,
                       SuivreFilm, SuivreSerie, Utilisateur, VisionnerEpisode,
                       VisionnerFilm)


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


def progression_serie_abonnements(db: Session, uid: int, serie: Serie) -> list[dict]:
    """Où en sont les personnes suivies (par uid) qui suivent aussi `serie`."""
    episodes = db.execute(
        select(Episode.id_episode, Saison.num_saison, Episode.num_episode)
        .join(Saison, Episode.id_saison == Saison.id_saison)
        .where(Saison.id_serie == serie.id_serie, Saison.num_saison > 0)
        .order_by(Saison.num_saison, Episode.num_episode)).all()
    total = len(episodes)
    ids_episodes = [e[0] for e in episodes]

    suivis = select(Abonnement.id_suivi).where(Abonnement.id_suiveur == uid)
    users = db.scalars(
        select(Utilisateur)
        .join(SuivreSerie, SuivreSerie.id_utilisateur == Utilisateur.id_utilisateur)
        .where(SuivreSerie.id_serie == serie.id_serie,
               Utilisateur.id_utilisateur.in_(suivis))
        .order_by(Utilisateur.pseudo)).all()

    resultats = []
    for u in users:
        vus = set()
        if ids_episodes:
            vus = set(db.scalars(select(VisionnerEpisode.id_episode).where(
                VisionnerEpisode.id_utilisateur == u.id_utilisateur,
                VisionnerEpisode.id_episode.in_(ids_episodes))).all())
        prochain_code = None
        for id_ep, ns, ne in episodes:
            if id_ep not in vus:
                prochain_code = f"S{ns:02d}E{ne:02d}"
                break
        resultats.append({
            "id_utilisateur": u.id_utilisateur, "pseudo": u.pseudo,
            "avatar": u.avatar, "episodes_vus": len(vus),
            "total_episodes": total, "prochain_code": prochain_code})
    return resultats


def compatibilite(db: Session, uid: int, cid: int) -> dict:
    """Compatibilité de goûts uid ↔ cid.

    Priorité à la **concordance des notes** sur les titres notés en commun (le
    signal le plus fort) ; sinon **recouvrement** des bibliothèques ; sinon 0.
    """
    def biblio(u: int) -> tuple[set, set]:
        series = set(db.scalars(select(SuivreSerie.id_serie)
                                .where(SuivreSerie.id_utilisateur == u)).all())
        films = set(db.scalars(select(SuivreFilm.id_film)
                               .where(SuivreFilm.id_utilisateur == u)).all())
        return series, films

    def notes(u: int) -> dict:
        d = {}
        for id_s, id_f, note in db.execute(
                select(Avis.id_serie, Avis.id_film, Avis.note)
                .where(Avis.id_utilisateur == u, Avis.note.is_not(None),
                       Avis.id_episode.is_(None))).all():
            if id_s is not None:
                d[("s", id_s)] = note
            elif id_f is not None:
                d[("f", id_f)] = note
        return d

    sa, fa = biblio(uid)
    sb, fb = biblio(cid)
    communs = len(sa & sb) + len(fa & fb)
    taille_min = min(len(sa) + len(fa), len(sb) + len(fb))

    na, nb = notes(uid), notes(cid)
    notes_communes = set(na) & set(nb)
    if notes_communes:
        accord = sum(1 - abs(na[k] - nb[k]) / 9 for k in notes_communes) / len(notes_communes)
        return {"pourcentage": round(accord * 100), "titres_communs": communs,
                "base": "notes"}
    if communs > 0 and taille_min:
        return {"pourcentage": round(communs / taille_min * 100),
                "titres_communs": communs, "base": "titres"}
    return {"pourcentage": 0, "titres_communs": 0, "base": "aucune"}


def fil_activite(db: Session, uid: int, limite: int = 40) -> list[dict]:
    """Fil d'activité des personnes suivies : avis, films vus, séries suivies.

    Trois sources fusionnées et triées par date décroissante (les avis d'épisode
    sont ignorés dans le fil pour rester lisible).
    """
    suivis = (select(Abonnement.id_suivi)
              .where(Abonnement.id_suiveur == uid).scalar_subquery())

    def _acteur(aid, pseudo, avatar):
        return {"id_utilisateur": aid, "pseudo": pseudo, "avatar": avatar}

    evenements: list[dict] = []

    # Films vus
    for date_v, titre, ref, aid, pseudo, avatar in db.execute(
            select(VisionnerFilm.date_visionnage, Film.titre, Film.reference_tmdb,
                   Utilisateur.id_utilisateur, Utilisateur.pseudo, Utilisateur.avatar)
            .join(Film, VisionnerFilm.id_film == Film.id_film)
            .join(Utilisateur, VisionnerFilm.id_utilisateur == Utilisateur.id_utilisateur)
            .where(VisionnerFilm.id_utilisateur.in_(suivis))
            .order_by(VisionnerFilm.date_visionnage.desc()).limit(limite)).all():
        evenements.append({
            "type": "film_vu", "date": date_v, "titre": titre, "type_cible": "film",
            "reference_tmdb": ref, "note": None, "acteur": _acteur(aid, pseudo, avatar)})

    # Séries suivies
    for date_a, titre, ref, aid, pseudo, avatar in db.execute(
            select(SuivreSerie.date_ajout, Serie.titre, Serie.reference_tmdb,
                   Utilisateur.id_utilisateur, Utilisateur.pseudo, Utilisateur.avatar)
            .join(Serie, SuivreSerie.id_serie == Serie.id_serie)
            .join(Utilisateur, SuivreSerie.id_utilisateur == Utilisateur.id_utilisateur)
            .where(SuivreSerie.id_utilisateur.in_(suivis))
            .order_by(SuivreSerie.date_ajout.desc()).limit(limite)).all():
        evenements.append({
            "type": "serie_suivie", "date": date_a, "titre": titre, "type_cible": "serie",
            "reference_tmdb": ref, "note": None, "acteur": _acteur(aid, pseudo, avatar)})

    # Avis (série ou film — via outerjoin ; les avis d'épisode sont exclus)
    for date_c, note, titre_s, ref_s, titre_f, ref_f, aid, pseudo, avatar in db.execute(
            select(Avis.date_creation, Avis.note, Serie.titre, Serie.reference_tmdb,
                   Film.titre, Film.reference_tmdb,
                   Utilisateur.id_utilisateur, Utilisateur.pseudo, Utilisateur.avatar)
            .join(Utilisateur, Avis.id_utilisateur == Utilisateur.id_utilisateur)
            .outerjoin(Serie, Avis.id_serie == Serie.id_serie)
            .outerjoin(Film, Avis.id_film == Film.id_film)
            .where(Avis.id_utilisateur.in_(suivis), Avis.id_episode.is_(None))
            .order_by(Avis.date_creation.desc()).limit(limite)).all():
        titre = titre_s or titre_f
        if titre is None:
            continue
        evenements.append({
            "type": "avis", "date": date_c, "titre": titre,
            "type_cible": "serie" if titre_s else "film",
            "reference_tmdb": ref_s if titre_s else ref_f, "note": note,
            "acteur": _acteur(aid, pseudo, avatar)})

    evenements.sort(key=lambda e: e["date"], reverse=True)
    return evenements[:limite]


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
    }
