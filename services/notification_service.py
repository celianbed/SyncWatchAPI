# services/notification_service.py — scan des diffusions du jour + envoi push
import json
import logging
from typing import Protocol

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from core.config import settings
from db.database import SessionLocal
from models import Appareil, Episode, Notification, Saison, Serie, SuivreSerie
from services import catalogue_service
from services.tmdb_client import ClientTMDB

journal = logging.getLogger(__name__)

# Une série « terminée » ne l'est que jusqu'à la saison suivante : sans elle ici,
# son cache ne serait plus jamais rafraîchi et l'app n'apprendrait jamais qu'un
# nouvel épisode existe. Seul « abandonnée » est exclu — un abandon est explicite.
STATUTS_A_RESYNCHRONISER = ("a_voir", "en_cours", "terminee", "en_pause")

# Notifications de diffusion : « terminée » redevient d'actualité dès qu'un
# épisode sort, alors qu'« en pause » est un retrait volontaire qu'on respecte.
STATUTS_NOTIFIES = ("a_voir", "en_cours", "terminee")


class Pousseur(Protocol):
    """Canal d'envoi push. `donnees` = payload de navigation (ex. reference_tmdb),
    `badge` = pastille à afficher sur l'icône iOS.

    Renvoie les jetons que le service a déclarés périmés, à retirer de la base.
    """

    def envoyer(self, jetons: list[str], titre: str, corps: str,
                donnees: dict | None = None,
                badge: int | None = None) -> list[str]: ...


class PousseurJournal:
    """Implémentation par défaut tant que Firebase n'est pas configuré : log seulement."""

    def envoyer(self, jetons: list[str], titre: str, corps: str,
                donnees: dict | None = None,
                badge: int | None = None) -> list[str]:
        journal.info("Push vers %d appareil(s) : %s — %s", len(jetons), titre, corps)
        return []


_firebase_pret = False


def _init_firebase() -> None:
    """Initialise firebase-admin une seule fois, à partir du JSON du compte de service."""
    global _firebase_pret
    if _firebase_pret:
        return
    import firebase_admin
    from firebase_admin import credentials
    firebase_admin.initialize_app(
        credentials.Certificate(json.loads(settings.FIREBASE_CREDENTIALS_JSON)))
    _firebase_pret = True


class PousseurFCM:
    """Envoi push réel via Firebase Cloud Messaging (Android et iOS/APNs)."""

    def envoyer(self, jetons: list[str], titre: str, corps: str,
                donnees: dict | None = None,
                badge: int | None = None) -> list[str]:
        from firebase_admin import messaging
        message = messaging.MulticastMessage(
            tokens=jetons,
            notification=messaging.Notification(title=titre, body=corps),
            # les valeurs data FCM doivent être des chaînes (navigation au tap)
            data={cle: str(valeur) for cle, valeur in (donnees or {}).items()},
            # iOS ne joue un son et ne badge l'icône que si APNs le demande
            # explicitement ; sans ce bloc la notification arrive muette.
            apns=messaging.APNSConfig(payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default", badge=badge))),
        )
        reponse = messaging.send_each_for_multicast(message)
        if reponse.failure_count:
            journal.warning("Push FCM : %d/%d envois en échec",
                            reponse.failure_count, len(jetons))
        # app désinstallée, jeton régénéré, projet Firebase changé : le jeton ne
        # vaudra plus jamais rien, on le signale pour qu'il soit retiré de la base.
        return [jeton for jeton, resultat in zip(jetons, reponse.responses)
                if isinstance(resultat.exception,
                              (messaging.UnregisteredError, messaging.SenderIdMismatchError))]


def pousseur_par_defaut() -> Pousseur:
    """FCM si le compte de service Firebase est configuré, sinon journalisation."""
    if settings.FIREBASE_CREDENTIALS_JSON:
        _init_firebase()
        return PousseurFCM()
    return PousseurJournal()


def _non_lues(db: Session, id_utilisateur: int) -> int:
    """Nombre de notifications non lues — sert de pastille sur l'icône iOS."""
    return db.scalar(select(func.count()).select_from(Notification).where(
        Notification.id_utilisateur == id_utilisateur, Notification.lue.is_(False))) or 0


def _purger_jetons(db: Session, jetons: list[str]) -> None:
    """Retire les appareils dont le jeton a été refusé définitivement par FCM."""
    if not jetons:
        return
    db.execute(delete(Appareil).where(Appareil.jeton_notif.in_(jetons)))
    journal.info("Push : %d jeton(s) périmé(s) retiré(s)", len(jetons))


def notifier(db: Session, id_destinataire: int, type_: str, contenu: str, *,
             pousseur: Pousseur | None = None, id_acteur: int | None = None,
             id_serie: int | None = None, id_film: int | None = None,
             donnees: dict | None = None) -> Notification:
    """Crée une notification en base + push vers les appareils du destinataire.

    Sert les évènements sociaux (abonnement, recommandation…). Le push part sur
    le canal courant (FCM en prod, journal sinon) ; sans appareil enregistré, la
    notification existe quand même dans l'app.
    """
    notif = Notification(id_utilisateur=id_destinataire, type=type_,
                         contenu=contenu[:255], id_acteur=id_acteur,
                         id_serie=id_serie, id_film=id_film)
    db.add(notif)
    db.commit()
    db.refresh(notif)

    jetons = db.scalars(select(Appareil.jeton_notif).where(
        Appareil.id_utilisateur == id_destinataire)).all()
    if not jetons:
        # sans cette trace, un push absent était indiscernable d'un push
        # envoyé : la fonction sortait sans rien dire.
        journal.info("Push ignoré : aucun appareil enregistré pour l'utilisateur %d",
                     id_destinataire)
        return notif

    _purger_jetons(db, (pousseur or pousseur_par_defaut()).envoyer(
        list(jetons), "SyncWatch", contenu[:255], donnees or {},
        badge=_non_lues(db, id_destinataire)))
    db.commit()
    return notif


def scanner_diffusions_du_jour(db: Session, pousseur: Pousseur | None = None) -> int:
    """Pour chaque épisode diffusé aujourd'hui d'une série suivie active :
    une notification en base + un push vers les appareils de l'utilisateur.
    Idempotent : relancer le scan le même jour ne crée pas de doublon.
    """
    lignes = db.execute(
        select(Episode, Saison.num_saison, Serie, SuivreSerie)
        .join(Saison, Episode.id_saison == Saison.id_saison)
        .join(Serie, Saison.id_serie == Serie.id_serie)
        .join(SuivreSerie, and_(
            SuivreSerie.id_serie == Serie.id_serie,
            SuivreSerie.statut_suivi.in_(STATUTS_NOTIFIES)))
        .where(Episode.date_diffusion == func.current_date())).all()

    creees = 0
    for episode, num_saison, serie, suivi in lignes:
        id_utilisateur = suivi.id_utilisateur
        deja = db.scalar(select(Notification.id_notification).where(
            Notification.id_utilisateur == id_utilisateur,
            Notification.id_episode == episode.id_episode,
            Notification.type == "nouvel_episode"))
        if deja is not None:
            continue

        contenu = f"Nouvel épisode de {serie.titre} : S{num_saison:02d}E{episode.num_episode:02d}"
        if episode.titre:
            contenu += f" – {episode.titre}"
        db.add(Notification(id_utilisateur=id_utilisateur, id_episode=episode.id_episode,
                            type="nouvel_episode", contenu=contenu[:255]))
        creees += 1

        # « terminée » vient de cesser d'être vrai : on repasse la série en cours,
        # sinon elle ne remonterait pas dans « À regarder ce soir » et la
        # notification n'aurait nulle part où mener.
        if suivi.statut_suivi == "terminee":
            suivi.statut_suivi = "en_cours"

        if pousseur is not None:
            jetons = db.scalars(select(Appareil.jeton_notif).where(
                Appareil.id_utilisateur == id_utilisateur)).all()
            if jetons:
                # data : ouvre la fiche série au tap sur la notif
                db.flush()  # pour que la notif qu'on vient d'ajouter compte dans la pastille
                _purger_jetons(db, pousseur.envoyer(
                    list(jetons), "SyncWatch", contenu[:255],
                    {"reference_tmdb": serie.reference_tmdb, "cible": "serie"},
                    badge=_non_lues(db, id_utilisateur)))

    db.commit()
    return creees


async def resynchroniser_series_suivies(db: Session, tmdb: ClientTMDB) -> int:
    """Rafraîchit depuis TMDB les séries suivies (fiche + saisons + épisodes).

    Sans cette resynchronisation, le cache d'une série que personne ne consulte
    vieillit et le scan des diffusions ne voit jamais les nouveaux épisodes.
    """
    series = db.scalars(
        select(Serie)
        .join(SuivreSerie, and_(SuivreSerie.id_serie == Serie.id_serie,
                                SuivreSerie.statut_suivi.in_(STATUTS_A_RESYNCHRONISER)))
        .distinct()).all()

    for serie in series:
        donnees = await tmdb.get_serie(serie.reference_tmdb)
        if donnees is None:
            continue
        serie = catalogue_service.upsert_serie(db, donnees)
        await catalogue_service.synchroniser_episodes(db, tmdb, serie)

    return len(series)


def job_quotidien() -> None:
    """Point d'entrée APScheduler : session dédiée, hors requête HTTP."""
    db = SessionLocal()
    try:
        creees = scanner_diffusions_du_jour(db, pousseur_par_defaut())
        journal.info("Scan des diffusions : %d notification(s) créée(s)", creees)
    finally:
        db.close()
