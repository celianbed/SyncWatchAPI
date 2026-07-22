# api/auth.py
import html
import re

from fastapi import (APIRouter, BackgroundTasks, Depends, Form, HTTPException,
                     Query, status)
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.dependances import envoyeur_mail
from core.config import settings
from core.gabarits import rendre
from core.securite import (creer_jeton_acces, creer_jeton_reset,
                           creer_jeton_verification, decoder_jeton_reset,
                           decoder_jeton_verification, empreinte_mot_de_passe,
                           hacher_mot_de_passe, verifier_mot_de_passe)
from db.database import get_db
from models import Utilisateur
from schemas.jeton import Jeton
from schemas.utilisateur import (ConnexionGoogle, DemandeReinitialisation,
                                    DemandeVerification)
from services.email_service import (Envoyeur, envoyer_mail_reset,
                                    envoyer_mail_verification)

router = APIRouter()


def _page_resultat(icone: str, titre: str, sous_titre: str) -> str:
    """Page « carte » de résultat (vérification, reset…) — gabarit page_resultat.html."""
    return rendre("page_resultat.html", icone=icone, titre=titre, sous_titre=sous_titre)


def _page_reset_formulaire(jeton: str, erreur: str | None = None) -> str:
    """Formulaire web « nouveau mot de passe + confirmation » — gabarit reset_formulaire.html."""
    bloc_erreur = f'<p class="err">{html.escape(erreur)}</p>' if erreur else ""
    return rendre("reset_formulaire.html", bloc_erreur=bloc_erreur,
                  jeton=html.escape(jeton))


def _valider_mot_de_passe(mdp: str, confirmation: str) -> str | None:
    """Renvoie un message d'erreur, ou None si le mot de passe est valide."""
    if mdp != confirmation:
        return "Les deux mots de passe ne correspondent pas."
    if len(mdp) < 8:
        return "Le mot de passe doit faire au moins 8 caractères."
    if len(mdp.encode("utf-8")) > 72:  # limite bcrypt (octets, pas caractères)
        return "Mot de passe trop long (limite : 72 octets)."
    return None


def _utilisateur_pour_reset(jeton: str, db: Session) -> Utilisateur | None:
    """Résout un jeton de reset en utilisateur ; None si invalide/expiré/déjà utilisé.
    L'empreinte lie le jeton au hash courant → un jeton devient caduc dès le 1er reset."""
    decode = decoder_jeton_reset(jeton)
    if decode is None:
        return None
    id_utilisateur, empreinte = decode
    utilisateur = db.get(Utilisateur, id_utilisateur)
    if utilisateur is None or empreinte_mot_de_passe(utilisateur.mot_de_passe) != empreinte:
        return None
    return utilisateur


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


def _verifier_token_google(id_token_str: str) -> dict:
    """Vérifie le id_token Google (signature Google + audience). ValueError si invalide."""
    return google_id_token.verify_oauth2_token(
        id_token_str, google_requests.Request(), settings.GOOGLE_CLIENT_ID)


def _pseudo_unique(db: Session, base: str) -> str:
    """Dérive un pseudo valide (3-30, alphanumérique) et unique depuis un nom Google."""
    pseudo = re.sub(r"[^A-Za-z0-9_]", "", base)[:30]
    if len(pseudo) < 3:
        pseudo = (pseudo + "membre")[:30]
    candidat, i = pseudo, 1
    while db.scalar(select(Utilisateur.id_utilisateur).where(Utilisateur.pseudo == candidat)):
        suffixe = str(i)
        candidat = pseudo[:30 - len(suffixe)] + suffixe
        i += 1
    return candidat


@router.post("/google", response_model=Jeton)
def connexion_google(donnees: ConnexionGoogle, db: Session = Depends(get_db)):
    """Connexion / inscription via Google : vérifie le id_token, lie au compte du
    même email s'il existe, sinon crée un compte (sans mot de passe, déjà vérifié)."""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Connexion Google non configurée.")
    try:
        infos = _verifier_token_google(donnees.id_token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton Google invalide",
                            headers={"WWW-Authenticate": "Bearer"})

    email = infos.get("email")
    if not email or not infos.get("email_verified"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Compte Google sans adresse mail vérifiée")

    utilisateur = db.scalar(select(Utilisateur).where(Utilisateur.adresse_mail == email))
    if utilisateur is None:  # premier passage : création du compte
        utilisateur = Utilisateur(
            adresse_mail=email,
            pseudo=_pseudo_unique(
                db, infos.get("given_name") or infos.get("name") or email.split("@")[0]),
            mot_de_passe=None,
            est_verifie=True,
        )
        db.add(utilisateur)
        db.flush()

    if utilisateur.statut_compte != "actif":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Compte suspendu ou supprimé")

    utilisateur.est_verifie = True  # Google a validé l'email → compte marqué vérifié
    utilisateur.date_derniere_connexion = func.now()
    db.commit()
    return Jeton(access_token=creer_jeton_acces(utilisateur.id_utilisateur))


@router.get("/verifier-email", response_class=HTMLResponse)
def verifier_email(jeton: str = Query(...), db: Session = Depends(get_db)):
    """Confirme l'adresse mail à partir du lien reçu, puis renvoie une page de
    confirmation. L'app détecte la vérification et connecte l'utilisateur. Idempotent."""
    id_utilisateur = decoder_jeton_verification(jeton)
    utilisateur = db.get(Utilisateur, id_utilisateur) if id_utilisateur is not None else None
    if utilisateur is None:
        return HTMLResponse(
            _page_resultat("⚠️", "Lien invalide ou expiré",
                           "Ce lien de vérification n'est plus valable. Ouvre l'app et demande un nouveau lien."),
            status_code=status.HTTP_400_BAD_REQUEST)

    if not utilisateur.est_verifie:
        utilisateur.est_verifie = True
        db.commit()
    return HTMLResponse(_page_resultat(
        "✅", "Adresse vérifiée",
        "Ton compte est activé. Retourne dans l'application SyncWatch : tu vas être connecté automatiquement."))


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


@router.post("/mot-de-passe-oublie", status_code=status.HTTP_202_ACCEPTED)
def mot_de_passe_oublie(
    demande: DemandeReinitialisation,
    taches: BackgroundTasks,
    db: Session = Depends(get_db),
    envoyeur: Envoyeur = Depends(envoyeur_mail),
):
    """Envoie un lien de réinitialisation. Réponse générique (anti-énumération)."""
    utilisateur = db.scalar(select(Utilisateur).where(
        Utilisateur.adresse_mail == demande.adresse_mail))
    # pas de reset pour un compte Google (sans mot de passe) : rien à réinitialiser
    if utilisateur is not None and utilisateur.mot_de_passe is not None:
        jeton = creer_jeton_reset(utilisateur.id_utilisateur, utilisateur.mot_de_passe)
        taches.add_task(envoyer_mail_reset, envoyeur,
                        utilisateur.adresse_mail, utilisateur.pseudo, jeton)
    return {"message": "Si un compte existe pour cette adresse, "
                       "un mail de réinitialisation vient d'être envoyé."}


@router.get("/reinitialiser-mot-de-passe", response_class=HTMLResponse)
def formulaire_reset(jeton: str = Query(...), db: Session = Depends(get_db)):
    """Page web : formulaire de saisie du nouveau mot de passe (ouverte depuis le mail)."""
    utilisateur = _utilisateur_pour_reset(jeton, db)
    if utilisateur is None:
        return HTMLResponse(
            _page_resultat("⚠️", "Lien invalide ou expiré",
                           "Ce lien de réinitialisation n'est plus valable. Refais une demande depuis l'app."),
            status_code=status.HTTP_400_BAD_REQUEST)
    return HTMLResponse(_page_reset_formulaire(jeton))


@router.post("/reinitialiser-mot-de-passe", response_class=HTMLResponse)
def reinitialiser_mot_de_passe(
    jeton: str = Form(...),
    mot_de_passe: str = Form(...),
    confirmation: str = Form(...),
    db: Session = Depends(get_db),
):
    """Traite le formulaire : valide, change le mot de passe (invalide le jeton), confirme."""
    utilisateur = _utilisateur_pour_reset(jeton, db)
    if utilisateur is None:
        return HTMLResponse(
            _page_resultat("⚠️", "Lien invalide ou expiré",
                           "Ce lien de réinitialisation n'est plus valable. Refais une demande depuis l'app."),
            status_code=status.HTTP_400_BAD_REQUEST)

    erreur = _valider_mot_de_passe(mot_de_passe, confirmation)
    if erreur is not None:
        return HTMLResponse(_page_reset_formulaire(jeton, erreur=erreur),
                            status_code=status.HTTP_400_BAD_REQUEST)

    utilisateur.mot_de_passe = hacher_mot_de_passe(mot_de_passe)
    db.commit()
    return HTMLResponse(_page_resultat(
        "✅", "Mot de passe modifié",
        "Ton mot de passe a été changé. Retourne dans l'app SyncWatch et connecte-toi."))
