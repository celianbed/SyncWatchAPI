# api/notifications.py — appareils (jetons FCM) et notifications
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.communs import du_proprietaire_ou_404
from api.dependances import utilisateur_courant
from db.database import get_db
from models import (Appareil, Episode, Film, Notification, Saison, Serie,
                       Utilisateur)
from schemas.notification import (AppareilCreation, AppareilPublic,
                                      NotificationPublique)

router = APIRouter()


def _cibles(db: Session, notifs: list[Notification]) -> dict[int, tuple[int, str]]:
    """Fiche à ouvrir au tap, pour tout un lot : {id_notification: (reference, type)}.

    Trois requêtes quelle que soit la taille du lot, là où une résolution notification
    par notification en coûtait une chacune — la liste en comptait autant que l'historique.
    """
    ids_film = {n.id_film for n in notifs if n.id_film is not None}
    ids_serie = {n.id_serie for n in notifs if n.id_serie is not None}
    ids_episode = {n.id_episode for n in notifs if n.id_episode is not None}

    films = dict(db.execute(
        select(Film.id_film, Film.reference_tmdb)
        .where(Film.id_film.in_(ids_film))).all()) if ids_film else {}
    series = dict(db.execute(
        select(Serie.id_serie, Serie.reference_tmdb)
        .where(Serie.id_serie.in_(ids_serie))).all()) if ids_serie else {}
    # remonte épisode → saison → série
    episodes = dict(db.execute(
        select(Episode.id_episode, Serie.reference_tmdb)
        .join(Saison, Episode.id_saison == Saison.id_saison)
        .join(Serie, Saison.id_serie == Serie.id_serie)
        .where(Episode.id_episode.in_(ids_episode))).all()) if ids_episode else {}

    resolues: dict[int, tuple[int, str]] = {}
    for n in notifs:
        if n.id_film is not None and n.id_film in films:
            resolues[n.id_notification] = (films[n.id_film], "film")
        elif n.id_serie is not None and n.id_serie in series:
            resolues[n.id_notification] = (series[n.id_serie], "serie")
        elif n.id_episode is not None and n.id_episode in episodes:
            resolues[n.id_notification] = (episodes[n.id_episode], "serie")
    return resolues


def _publier(notif: Notification,
             cibles: dict[int, tuple[int, str]]) -> NotificationPublique:
    pub = NotificationPublique.model_validate(notif)
    reference, cible = cibles.get(notif.id_notification, (None, None))
    pub.reference_tmdb = reference
    pub.cible = cible
    return pub


@router.post("/appareils", response_model=AppareilPublic,
             status_code=status.HTTP_201_CREATED)
def enregistrer_appareil(
    donnees: AppareilCreation,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Enregistre le jeton FCM ; un jeton déjà connu est rattaché au compte courant
    (changement d'utilisateur sur le même téléphone)."""
    requete = insert(Appareil).values(
        id_utilisateur=utilisateur.id_utilisateur,
        jeton_notif=donnees.jeton_notif,
        plateforme=donnees.plateforme,
    ).on_conflict_do_update(
        index_elements=["jeton_notif"],
        set_={"id_utilisateur": utilisateur.id_utilisateur,
              "plateforme": donnees.plateforme,
              "date_derniere_activite": func.now()},
    ).returning(Appareil.id_appareil)
    id_appareil = db.scalar(requete)
    db.commit()
    return db.get(Appareil, id_appareil)


@router.delete("/appareils/{id_appareil}", status_code=status.HTTP_204_NO_CONTENT)
def supprimer_appareil(
    id_appareil: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """À appeler à la déconnexion pour ne plus recevoir de push sur cet appareil."""
    appareil = du_proprietaire_ou_404(db, Appareil, id_appareil, utilisateur,
                                      "Appareil introuvable.")
    db.delete(appareil)
    db.commit()


@router.get("/notifications/nombre-non-lues")
def nombre_non_lues(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Compteur pour la pastille. Route dédiée : compter en récupérant la liste
    obligerait à la renvoyer entière, donc à ne jamais pouvoir la borner."""
    return {"nombre": db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.id_utilisateur == utilisateur.id_utilisateur,
            Notification.lue.is_(False))) or 0}


@router.get("/notifications", response_model=list[NotificationPublique])
def mes_notifications(
    lue: bool | None = None,
    limite: int = Query(50, ge=1, le=200),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Les plus récentes d'abord. Bornée : l'historique d'un compte ancien se
    compte en centaines, et il était renvoyé en entier à chaque ouverture."""
    requete = (select(Notification)
               .where(Notification.id_utilisateur == utilisateur.id_utilisateur)
               .order_by(Notification.date_envoi.desc())
               .limit(limite))
    if lue is not None:
        requete = requete.where(Notification.lue == lue)
    notifs = list(db.scalars(requete))
    cibles = _cibles(db, notifs)
    return [_publier(notif, cibles) for notif in notifs]


@router.patch("/notifications/{id_notification}/lue", response_model=NotificationPublique)
def marquer_lue(
    id_notification: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    notification = du_proprietaire_ou_404(db, Notification, id_notification, utilisateur,
                                          "Notification introuvable.")
    notification.lue = True
    db.commit()
    db.refresh(notification)
    return _publier(notification, _cibles(db, [notification]))
