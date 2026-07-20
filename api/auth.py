# api/auth.py
from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Query,
                     status)
from fastapi.responses import HTMLResponse
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


def _page_verification(succes: bool) -> str:
    """Page de confirmation affichée après clic sur le lien de vérification.
    L'app détecte la vérification toute seule et connecte l'utilisateur — la page
    invite simplement à revenir dans l'app."""
    if succes:
        icone, titre = "✅", "Adresse vérifiée"
        sous_titre = ("Ton compte est activé. Retourne dans l'application SyncWatch : "
                      "tu vas être connecté automatiquement.")
    else:
        icone, titre = "⚠️", "Lien invalide ou expiré"
        sous_titre = ("Ce lien de vérification n'est plus valable. Ouvre l'app "
                      "et demande un nouveau lien.")
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SyncWatch</title>
<style>
  body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:#0F172A; font-family:-apple-system,Arial,sans-serif; color:#F1F5F9; }}
  .carte {{ background:#1E293B; border-radius:16px; padding:36px 28px; max-width:340px; width:86%;
           text-align:center; }}
  .icone {{ font-size:52px; }}
  h1 {{ font-size:22px; margin:16px 0 6px; }}
  p {{ color:#94A3B8; font-size:14px; line-height:21px; margin:0; }}
</style></head>
<body><div class="carte">
  <div class="icone">{icone}</div>
  <h1>{titre}</h1>
  <p>{sous_titre}</p>
</div></body></html>"""


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


@router.get("/verifier-email", response_class=HTMLResponse)
def verifier_email(jeton: str = Query(...), db: Session = Depends(get_db)):
    """Confirme l'adresse mail à partir du lien reçu, puis renvoie une page
    qui rouvre l'app (deep link). Idempotent."""
    id_utilisateur = decoder_jeton_verification(jeton)
    utilisateur = db.get(Utilisateur, id_utilisateur) if id_utilisateur is not None else None
    if utilisateur is None:
        return HTMLResponse(_page_verification(succes=False),
                            status_code=status.HTTP_400_BAD_REQUEST)

    if not utilisateur.est_verifie:
        utilisateur.est_verifie = True
        db.commit()
    return HTMLResponse(_page_verification(succes=True))


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
