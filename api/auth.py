# api/auth.py
from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Query,
                     status)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.dependances import envoyeur_mail
from core.securite import (creer_jeton_acces, creer_jeton_verification,
                           decoder_jeton_verification, verifier_mot_de_passe)
from db.database import get_db
from models import Utilisateur
from schemas.jeton import Jeton
from schemas.utilisateur import DemandeVerification
from services.email_service import Envoyeur, envoyer_mail_verification

router = APIRouter()


@router.post("/connexion", response_model=Jeton)
def connexion(
    identifiants: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """Connexion par adresse mail ou pseudo (champ `username` de la spec OAuth2)."""
    utilisateur = db.scalar(select(Utilisateur).where(
        (Utilisateur.adresse_mail == identifiants.username)
        | (Utilisateur.pseudo == identifiants.username)))
    if utilisateur is None or not verifier_mot_de_passe(
            identifiants.password, utilisateur.mot_de_passe):
        # message unique : ne pas révéler si le compte existe
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Identifiants incorrects",
            headers={"WWW-Authenticate": "Bearer"})
    if utilisateur.statut_compte != "actif":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Compte suspendu ou supprimé")
    if not utilisateur.est_verifie:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Adresse mail non vérifiée")

    utilisateur.date_derniere_connexion = func.now()
    db.commit()
    return Jeton(access_token=creer_jeton_acces(utilisateur.id_utilisateur))


@router.get("/verifier-email")
def verifier_email(jeton: str = Query(...), db: Session = Depends(get_db)):
    """Confirme l'adresse mail à partir du lien reçu. Idempotent."""
    id_utilisateur = decoder_jeton_verification(jeton)
    if id_utilisateur is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Lien de vérification invalide ou expiré")
    utilisateur = db.get(Utilisateur, id_utilisateur)
    if utilisateur is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Lien de vérification invalide ou expiré")
    if utilisateur.est_verifie:
        return {"message": "Adresse mail déjà vérifiée."}

    utilisateur.est_verifie = True
    db.commit()
    return {"message": "Adresse mail vérifiée, vous pouvez vous connecter."}


@router.post("/renvoyer-verification", status_code=status.HTTP_202_ACCEPTED)
def renvoyer_verification(
    demande: DemandeVerification,
    taches: BackgroundTasks,
    db: Session = Depends(get_db),
    envoyeur: Envoyeur = Depends(envoyeur_mail),
):
    """Renvoie le mail de confirmation. Réponse générique : ne révèle pas si le
    compte existe ni s'il est déjà vérifié (anti-énumération)."""
    utilisateur = db.scalar(select(Utilisateur).where(
        Utilisateur.adresse_mail == demande.adresse_mail))
    if utilisateur is not None and not utilisateur.est_verifie:
        jeton = creer_jeton_verification(utilisateur.id_utilisateur)
        taches.add_task(envoyer_mail_verification, envoyeur,
                        utilisateur.adresse_mail, utilisateur.pseudo, jeton)
    return {"message": "Si un compte non vérifié existe pour cette adresse, "
                       "un nouveau mail de confirmation vient d'être envoyé."}
