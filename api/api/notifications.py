# api/api/notifications.py — appareils (jetons FCM) et notifications
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.api.dependances import utilisateur_courant
from api.db.database import get_db
from api.models import Appareil, Notification, Utilisateur
from api.schemas.notification import (AppareilCreation, AppareilPublic,
                                      NotificationPublique)

router = APIRouter()


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
    appareil = db.get(Appareil, id_appareil)
    if appareil is None or appareil.id_utilisateur != utilisateur.id_utilisateur:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appareil introuvable.")
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
    return db.scalars(requete).all()


@router.patch("/notifications/{id_notification}/lue", response_model=NotificationPublique)
def marquer_lue(
    id_notification: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    notification = db.get(Notification, id_notification)
    # 404 aussi pour la notification d'un autre : ne pas révéler son existence
    if notification is None or notification.id_utilisateur != utilisateur.id_utilisateur:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification introuvable.")
    notification.lue = True
    db.commit()
    db.refresh(notification)
    return notification
