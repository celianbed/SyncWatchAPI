# services/notification_service.py — scan des diffusions du jour + envoi push
import logging
from typing import Protocol

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from db.database import SessionLocal
from models import Appareil, Episode, Notification, Saison, Serie, SuivreSerie
from services import catalogue_service
from services.tmdb_client import ClientTMDB
from services.visionnage_service import STATUTS_ACTIFS

journal = logging.getLogger(__name__)


class Pousseur(Protocol):
    """Canal d'envoi push — l'implémentation FCM se branchera ici."""

    def envoyer(self, jetons: list[str], titre: str, corps: str) -> None: ...


class PousseurJournal:
    """Implémentation par défaut tant que Firebase n'est pas configuré : log seulement."""

    def envoyer(self, jetons: list[str], titre: str, corps: str) -> None:
        journal.info("Push vers %d appareil(s) : %s — %s", len(jetons), titre, corps)


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
                pousseur.envoyer(list(jetons), "SyncWatch", contenu[:255])

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
        creees = scanner_diffusions_du_jour(db, PousseurJournal())
        journal.info("Scan des diffusions : %d notification(s) créée(s)", creees)
    finally:
        db.close()
