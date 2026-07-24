# api/notifications.py — appareils (jetons FCM) et notifications
from fastapi import APIRouter, Depends, status
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


def _resoudre_cible(db: Session, notif: Notification) -> tuple[int | None, str | None]:
    """Résout la fiche à ouvrir au tap : (reference_tmdb, "serie"|"film")."""
    if notif.id_film is not None:
        return db.scalar(select(Film.reference_tmdb)
                         .where(Film.id_film == notif.id_film)), "film"
    if notif.id_serie is not None:
        return db.scalar(select(Serie.reference_tmdb)
                         .where(Serie.id_serie == notif.id_serie)), "serie"
    if notif.id_episode is not None:  # remonte épisode → saison → série
        return db.scalar(
            select(Serie.reference_tmdb)
            .join(Saison, Saison.id_serie == Serie.id_serie)
            .join(Episode, Episode.id_saison == Saison.id_saison)
            .where(Episode.id_episode == notif.id_episode)), "serie"
    return None, None


def _publier(db: Session, notif: Notification) -> NotificationPublique:
    reference, cible = _resoudre_cible(db, notif)
    pub = NotificationPublique.model_validate(notif)
    pub.reference_tmdb = reference
    pub.cible = cible if reference is not None else None
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


@router.get("/notifications", response_model=list[NotificationPublique])
def mes_notifications(
    lue: bool | None = None,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    requete = (select(Notification)
               .where(Notification.id_utilisateur == utilisateur.id_utilisateur)
               .order_by(Notification.date_envoi.desc()))
    if lue is not None:
        requete = requete.where(Notification.lue == lue)
    return [_publier(db, notif) for notif in db.scalars(requete)]


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
    return notification
