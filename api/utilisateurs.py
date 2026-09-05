# api/utilisateurs.py
from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException,
                     Request, status)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.dependances import client_tmdb, envoyeur_mail, utilisateur_courant
from core.limitation import LIMITE_INSCRIPTION, limiteur
from core.securite import (creer_jeton_reset, creer_jeton_verification,
                           hacher_mot_de_passe)
from db.database import get_db
from models import (Abonnement, Film, Notification, Serie, SuivreFilm,
                       SuivreSerie, Utilisateur, VisionnerFilm)
from schemas.recherche import ResultatRecherche
from schemas.social import (AvisProfil, Compatibilite, ProfilPublic,
                               RecommandationCreation, ResumeUtilisateur)
from schemas.utilisateur import (UtilisateurCreation, UtilisateurMaj,
                                     UtilisateurPublic)
from services import catalogue_service, notification_service, social_service
from services.apple_auth import revoquer as revoquer_apple
from services.tmdb_client import ClientTMDB
from services.email_service import (Envoyeur, envoyer_mail_compte_existant,
                                    envoyer_mail_verification)

router = APIRouter()


# Une recommandation fait sonner le téléphone du destinataire. On exige donc un
# lien social, et on plafonne les envois vers une même personne sur la journée :
# suivre quelqu'un étant libre, le lien seul ne protégerait de rien.
RECOMMANDATIONS_PAR_JOUR = 3

MESSAGE_INSCRIPTION = ("Si cette adresse peut être utilisée, un mail de confirmation "
                       "vient d'être envoyé. Ouvre-le pour activer ton compte.")


@router.post("", status_code=status.HTTP_202_ACCEPTED)
@limiteur.limit(LIMITE_INSCRIPTION)  # anti création massive de comptes
def inscrire(
    request: Request,
    donnees: UtilisateurCreation,
    taches: BackgroundTasks,
    db: Session = Depends(get_db),
    envoyeur: Envoyeur = Depends(envoyeur_mail),
):
    """Inscription. La réponse est **identique** que l'adresse existe déjà ou non
    (anti-énumération) : c'est le mail reçu qui diffère. Seul le pseudo, non
    sensible et imposé à l'utilisateur, peut renvoyer un conflit explicite."""
    if db.scalar(select(Utilisateur).where(Utilisateur.pseudo == donnees.pseudo)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce pseudo est déjà pris.")

    existant = db.scalar(select(Utilisateur).where(
        Utilisateur.adresse_mail == donnees.adresse_mail))
    if existant is not None:
        # On ne crée rien et on ne le dit pas : on prévient le vrai propriétaire.
        # (compte Google, sans mot de passe : rien à réinitialiser → pas de mail)
        if existant.mot_de_passe is not None:
            jeton_reset = creer_jeton_reset(existant.id_utilisateur, existant.mot_de_passe)
            taches.add_task(envoyer_mail_compte_existant, envoyeur,
                            existant.adresse_mail, existant.pseudo, jeton_reset)
        return {"message": MESSAGE_INSCRIPTION}

    utilisateur = Utilisateur(
        adresse_mail=donnees.adresse_mail,
        pseudo=donnees.pseudo,
        mot_de_passe=hacher_mot_de_passe(donnees.mot_de_passe),
    )
    db.add(utilisateur)
    db.commit()
    db.refresh(utilisateur)

    # compte créé non vérifié : on envoie le lien de confirmation hors du chemin critique
    jeton = creer_jeton_verification(utilisateur.id_utilisateur)
    taches.add_task(envoyer_mail_verification, envoyeur,
                    utilisateur.adresse_mail, utilisateur.pseudo, jeton)
    return {"message": MESSAGE_INSCRIPTION}


# déclaré avant /{id_utilisateur}, sinon "moi" serait capté comme un id
@router.get("/moi", response_model=UtilisateurPublic)
def moi(utilisateur: Utilisateur = Depends(utilisateur_courant)):
    return utilisateur


@router.patch("/moi", response_model=UtilisateurPublic)
def modifier_moi(
    donnees: UtilisateurMaj,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Met à jour le profil (pseudo, avatar) — champs absents inchangés."""
    champs = donnees.model_dump(exclude_unset=True)
    if champs.get("pseudo") is None:
        champs.pop("pseudo", None)  # le pseudo est obligatoire : null ignoré
    nouveau_pseudo = champs.get("pseudo")
    if (nouveau_pseudo and nouveau_pseudo != utilisateur.pseudo
            and db.scalar(select(Utilisateur).where(Utilisateur.pseudo == nouveau_pseudo))):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce pseudo est déjà pris.")
    for champ, valeur in champs.items():
        setattr(utilisateur, champ, valeur)
    db.commit()
    db.refresh(utilisateur)
    return utilisateur


@router.delete("/moi", status_code=status.HTTP_204_NO_CONTENT)
def supprimer_moi(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Supprime définitivement le compte : suivis, visionnages, avis, abonnements,
    appareils et notifications partent en cascade.

    Exigé par l'App Store (5.1.1 v) dès lors que l'app crée des comptes — et il
    s'agit d'une vraie suppression, pas d'une désactivation.
    """
    if utilisateur.jeton_revocation_apple:
        # Apple demande de révoquer l'accès avant d'oublier le compte
        revoquer_apple(utilisateur.jeton_revocation_apple)
    db.delete(utilisateur)
    db.commit()


# déclarés avant /{id_utilisateur} (deux segments : pas de collision, mais on groupe le "moi")
@router.get("/moi/favoris", response_model=list[ResultatRecherche])
def mes_favoris(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Séries et films marqués favoris — carrousel du profil."""
    uid = utilisateur.id_utilisateur
    series = db.scalars(
        select(Serie).join(SuivreSerie, SuivreSerie.id_serie == Serie.id_serie)
        .where(SuivreSerie.id_utilisateur == uid, SuivreSerie.favori.is_(True))
        .order_by(SuivreSerie.date_ajout.desc())).all()
    films = db.scalars(
        select(Film).join(SuivreFilm, SuivreFilm.id_film == Film.id_film)
        .where(SuivreFilm.id_utilisateur == uid, SuivreFilm.favori.is_(True))).all()
    return ([ResultatRecherche.depuis_serie(s) for s in series]
            + [ResultatRecherche.depuis_film(f) for f in films])


@router.get("/moi/films-vus", response_model=list[ResultatRecherche])
def mes_films_vus(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Films vus récemment (distincts, dernier visionnage d'abord) — carrousel du profil."""
    uid = utilisateur.id_utilisateur
    dernier = (
        select(VisionnerFilm.id_film,
               func.max(VisionnerFilm.date_visionnage).label("dernier"))
        .where(VisionnerFilm.id_utilisateur == uid)
        .group_by(VisionnerFilm.id_film).subquery())
    films = db.scalars(
        select(Film).join(dernier, Film.id_film == dernier.c.id_film)
        .order_by(dernier.c.dernier.desc()).limit(20)).all()
    return [ResultatRecherche.depuis_film(f) for f in films]


# ── Social : abonnements (suivre un utilisateur ; amitié = suivi mutuel) ──

def _utilisateur_actif_ou_404(db: Session, id_utilisateur: int) -> Utilisateur:
    cible = db.get(Utilisateur, id_utilisateur)
    if cible is None or cible.statut_compte != "actif":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable.")
    return cible


@router.post("/{id_utilisateur}/abonner", status_code=status.HTTP_201_CREATED)
def abonner(
    id_utilisateur: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """S'abonner à un utilisateur (asymétrique). Suivi mutuel = amis."""
    if id_utilisateur == utilisateur.id_utilisateur:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "On ne peut pas s'abonner à soi-même.")
    _utilisateur_actif_ou_404(db, id_utilisateur)
    cle = {"id_suiveur": utilisateur.id_utilisateur, "id_suivi": id_utilisateur}
    if db.get(Abonnement, cle) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Déjà abonné.")
    db.add(Abonnement(**cle))
    db.commit()
    # notif sociale : prévenir la personne suivie (+ push si elle a un appareil)
    notification_service.notifier(
        db, id_utilisateur, "abonnement",
        f"{utilisateur.pseudo} a commencé à te suivre",
        id_acteur=utilisateur.id_utilisateur,
        donnees={"cible": "profil", "id_acteur": str(utilisateur.id_utilisateur)})
    return {"statut": "abonne"}


@router.delete("/{id_utilisateur}/abonner", status_code=status.HTTP_204_NO_CONTENT)
def se_desabonner(
    id_utilisateur: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    lien = db.get(Abonnement, {"id_suiveur": utilisateur.id_utilisateur,
                               "id_suivi": id_utilisateur})
    if lien is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tu n'es pas abonné.")
    db.delete(lien)
    db.commit()


@router.get("/{id_utilisateur}/abonnes", response_model=list[ResumeUtilisateur])
def abonnes(
    id_utilisateur: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Les utilisateurs qui suivent {id_utilisateur}."""
    _utilisateur_actif_ou_404(db, id_utilisateur)
    users = db.scalars(
        select(Utilisateur)
        .join(Abonnement, Abonnement.id_suiveur == Utilisateur.id_utilisateur)
        .where(Abonnement.id_suivi == id_utilisateur)
        .order_by(Abonnement.date_abonnement.desc())).all()
    return social_service.resumes(db, utilisateur.id_utilisateur, list(users))


@router.get("/{id_utilisateur}/abonnements", response_model=list[ResumeUtilisateur])
def abonnements(
    id_utilisateur: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Les utilisateurs que {id_utilisateur} suit."""
    _utilisateur_actif_ou_404(db, id_utilisateur)
    users = db.scalars(
        select(Utilisateur)
        .join(Abonnement, Abonnement.id_suivi == Utilisateur.id_utilisateur)
        .where(Abonnement.id_suiveur == id_utilisateur)
        .order_by(Abonnement.date_abonnement.desc())).all()
    return social_service.resumes(db, utilisateur.id_utilisateur, list(users))


@router.get("/{id_utilisateur}/series-suivies", response_model=list[ResultatRecherche])
def series_suivies(
    id_utilisateur: int,
    _: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Séries suivies par un utilisateur (carrousel du profil public)."""
    series = db.scalars(
        select(Serie).join(SuivreSerie, SuivreSerie.id_serie == Serie.id_serie)
        .where(SuivreSerie.id_utilisateur == id_utilisateur)
        .order_by(SuivreSerie.date_ajout.desc()).limit(30)).all()
    return [ResultatRecherche.depuis_serie(s) for s in series]


@router.get("/{id_utilisateur}/avis", response_model=list[AvisProfil])
def avis_utilisateur(
    id_utilisateur: int,
    _: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Derniers avis (titre + note) d'un utilisateur — section du profil public."""
    return social_service.avis_profil(db, id_utilisateur)


@router.get("/{id_utilisateur}/compatibilite", response_model=Compatibilite)
def compatibilite(
    id_utilisateur: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Compatibilité de goûts entre l'utilisateur courant et {id_utilisateur}."""
    _utilisateur_actif_ou_404(db, id_utilisateur)
    return social_service.compatibilite(db, utilisateur.id_utilisateur, id_utilisateur)


@router.post("/{id_utilisateur}/recommander", status_code=status.HTTP_201_CREATED)
async def recommander(
    id_utilisateur: int,
    donnees: RecommandationCreation,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
    tmdb: ClientTMDB = Depends(client_tmdb),
):
    """Recommande un titre à un utilisateur : notification (+ push) « X te recommande … »."""
    if id_utilisateur == utilisateur.id_utilisateur:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "On ne se recommande pas un titre à soi-même.")
    _utilisateur_actif_ou_404(db, id_utilisateur)

    if db.scalar(select(Abonnement.id_suivi).where(
            Abonnement.id_suiveur == utilisateur.id_utilisateur,
            Abonnement.id_suivi == id_utilisateur)) is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "On ne recommande qu'aux personnes que l'on suit.")

    envoyees_aujourdhui = db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.id_utilisateur == id_utilisateur,
            Notification.id_acteur == utilisateur.id_utilisateur,
            Notification.type == "recommandation",
            Notification.date_envoi >= func.current_date()))
    if envoyees_aujourdhui >= RECOMMANDATIONS_PAR_JOUR:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Trop de recommandations envoyées à cette personne aujourd'hui.")

    if donnees.type == "serie":
        serie = await catalogue_service.obtenir_serie(db, tmdb, donnees.reference_tmdb)
        if serie is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Série inconnue de TMDB.")
        titre, id_serie, id_film = serie.titre, serie.id_serie, None
    else:
        film = await catalogue_service.obtenir_film(db, tmdb, donnees.reference_tmdb)
        if film is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Film inconnu de TMDB.")
        titre, id_serie, id_film = film.titre, None, film.id_film

    notification_service.notifier(
        db, id_utilisateur, "recommandation",
        f"{utilisateur.pseudo} te recommande {titre}",
        id_acteur=utilisateur.id_utilisateur, id_serie=id_serie, id_film=id_film,
        donnees={"reference_tmdb": str(donnees.reference_tmdb), "cible": donnees.type})
    return {"statut": "recommande"}


@router.get("/{id_utilisateur}", response_model=ProfilPublic)
def lire(
    id_utilisateur: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Profil public détaillé (compteurs + relation) — jamais l'adresse mail."""
    cible = _utilisateur_actif_ou_404(db, id_utilisateur)
    return social_service.profil_detaille(db, utilisateur.id_utilisateur, cible)
