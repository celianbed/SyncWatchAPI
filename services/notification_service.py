# services/notification_service.py — scan des diffusions du jour + envoi push
import json
import logging
from typing import Protocol

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from core.config import settings
from db.database import SessionLocal
from models import Appareil, Episode, Notification, Saison, Serie, SuivreSerie
from services import catalogue_service
from services.tmdb_client import ClientTMDB
from services.visionnage_service import STATUTS_ACTIFS

journal = logging.getLogger(__name__)


class Pousseur(Protocol):
    """Canal d'envoi push. `donnees` = payload de navigation (ex. reference_tmdb)."""

    def envoyer(self, jetons: list[str], titre: str, corps: str,
                donnees: dict | None = None) -> None: ...


class PousseurJournal:
    """Implémentation par défaut tant que Firebase n'est pas configuré : log seulement."""

    def envoyer(self, jetons: list[str], titre: str, corps: str,
                donnees: dict | None = None) -> None:
        journal.info("Push vers %d appareil(s) : %s — %s", len(jetons), titre, corps)


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
    """Envoi push réel via Firebase Cloud Messaging (Android)."""

    def envoyer(self, jetons: list[str], titre: str, corps: str,
                donnees: dict | None = None) -> None:
        from firebase_admin import messaging
        message = messaging.MulticastMessage(
            tokens=jetons,
            notification=messaging.Notification(title=titre, body=corps),
            # les valeurs data FCM doivent être des chaînes (navigation au tap)
            data={cle: str(valeur) for cle, valeur in (donnees or {}).items()},
        )
        reponse = messaging.send_each_for_multicast(message)
        if reponse.failure_count:
            journal.warning("Push FCM : %d/%d envois en échec",
                            reponse.failure_count, len(jetons))


def pousseur_par_defaut() -> Pousseur:
    """FCM si le compte de service Firebase est configuré, sinon journalisation."""
    if settings.FIREBASE_CREDENTIALS_JSON:
        _init_firebase()
        return PousseurFCM()
    return PousseurJournal()


def scanner_diffusions_du_jour(db: Session, pousseur: Pousseur | None = None) -> int:
    """Pour chaque épisode diffusé aujourd'hui d'une série suivie active :
    une notification en base + un push vers les appareils de l'utilisateur.
    Idempotent : relancer le scan le même jour ne crée pas de doublon.
    """
    lignes = db.execute(
        select(Episode, Saison.num_saison, Serie, SuivreSerie.id_utilisateur)
        .join(Saison, Episode.id_saison == Saison.id_saison)
        .join(Serie, Saison.id_serie == Serie.id_serie)
        .join(SuivreSerie, and_(
            SuivreSerie.id_serie == Serie.id_serie,
            SuivreSerie.statut_suivi.in_(STATUTS_ACTIFS)))
        .where(Episode.date_diffusion == func.current_date())).all()

    creees = 0
    for episode, num_saison, serie, id_utilisateur in lignes:
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

        if pousseur is not None:
            jetons = db.scalars(select(Appareil.jeton_notif).where(
                Appareil.id_utilisateur == id_utilisateur)).all()
            if jetons:
                # data : ouvre la fiche série au tap sur la notif
                pousseur.envoyer(list(jetons), "SyncWatch", contenu[:255],
                                 {"reference_tmdb": serie.reference_tmdb, "cible": "serie"})

    db.commit()
    return creees


async def resynchroniser_series_suivies(db: Session, tmdb: ClientTMDB) -> int:
    """Rafraîchit depuis TMDB les séries suivies actives (fiche + saisons + épisodes).

    Sans cette resynchronisation, le cache d'une série que personne ne consulte
    vieillit et le scan des diffusions ne voit jamais les nouveaux épisodes.
    """
    series = db.scalars(
        select(Serie)
        .join(SuivreSerie, and_(SuivreSerie.id_serie == Serie.id_serie,
                                SuivreSerie.statut_suivi.in_(STATUTS_ACTIFS)))
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
