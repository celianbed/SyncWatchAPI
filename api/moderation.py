# api/moderation.py — signalement de contenus (App Store, directive 1.2).
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.communs import get_ou_404
from api.dependances import envoyeur_mail, utilisateur_courant
from db.database import get_db
from models import Avis, Signalement, Utilisateur
from schemas.moderation import SignalementCreation, SignalementPublic
from services import moderation_service
from services.email_service import Envoyeur, envoyer_alerte_signalement

router = APIRouter()


@router.post("/signalements", response_model=SignalementPublic,
             status_code=status.HTTP_201_CREATED)
def signaler(
    donnees: SignalementCreation,
    taches: BackgroundTasks,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
    envoyeur: Envoyeur = Depends(envoyeur_mail),
):
    """Signale un avis ou une personne.

    Aucun seuil automatique : à cette échelle, un compteur de signalements
    serait une arme plutôt qu'une protection — deux comptes coordonnés
    enterreraient n'importe quel contenu. Le signalement masque la cible pour
    celui qui signale, et l'éditeur tranche. La sanction existe déjà :
    `statut_compte = 'suspendu'` verrouille un compte partout.
    """
    if donnees.id_avis is not None:
        avis = get_ou_404(db, Avis, donnees.id_avis, "Avis introuvable.")
        if avis.id_utilisateur == utilisateur.id_utilisateur:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "On ne signale pas son propre avis.")
    else:
        if donnees.id_vise == utilisateur.id_utilisateur:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "On ne se signale pas soi-même.")
        get_ou_404(db, Utilisateur, donnees.id_vise, "Utilisateur introuvable.")

    if moderation_service.deja_signale(db, utilisateur.id_utilisateur,
                                       id_avis=donnees.id_avis,
                                       id_vise=donnees.id_vise):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Tu as déjà signalé ce contenu.")

    signalement = Signalement(
        id_signaleur=utilisateur.id_utilisateur,
        id_avis=donnees.id_avis,
        id_vise=donnees.id_vise,
        motif=donnees.motif,
        precision=donnees.precision,
    )
    db.add(signalement)
    db.commit()
    db.refresh(signalement)

    # en tâche de fond : un backend mail indisponible ne doit pas faire échouer
    # le signalement, qui est déjà enregistré.
    taches.add_task(envoyer_alerte_signalement, envoyeur,
                    signalement.id_signalement, utilisateur.pseudo,
                    donnees.motif, donnees.id_avis, donnees.id_vise,
                    donnees.precision)
    return signalement


@router.get("/signalements/moi", response_model=list[SignalementPublic])
def mes_signalements(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Ce que j'ai signalé — pour que l'app puisse dire « déjà signalé »."""
    return moderation_service.signalements_de(db, utilisateur.id_utilisateur)
