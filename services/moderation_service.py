# services/moderation_service.py — blocage et signalement.
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from models import Abonnement, Blocage, Signalement


def ids_masques(db: Session, id_utilisateur: int) -> set[int]:
    """Personnes à ne jamais montrer à `id_utilisateur`.

    Le masquage est **symétrique** : bloquer quelqu'un le fait disparaître de
    votre vue, et vous fait disparaître de la sienne. Sans réciprocité, la
    personne bloquée continuerait de vous lire et de vous recommander des
    titres — le blocage ne protégerait rien.
    """
    return set(db.scalars(
        select(Blocage.id_bloque).where(Blocage.id_bloqueur == id_utilisateur)
        .union(select(Blocage.id_bloqueur).where(
            Blocage.id_bloque == id_utilisateur))))


def bloque(db: Session, id_utilisateur: int, id_autre: int) -> bool:
    """Y a-t-il un blocage dans un sens ou dans l'autre ?"""
    return db.scalar(
        select(Blocage.id_bloqueur).where(or_(
            (Blocage.id_bloqueur == id_utilisateur) & (Blocage.id_bloque == id_autre),
            (Blocage.id_bloqueur == id_autre) & (Blocage.id_bloque == id_utilisateur),
        )).limit(1)) is not None


def bloquer(db: Session, id_bloqueur: int, id_bloque: int) -> None:
    """Pose le blocage et rompt les abonnements dans les deux sens.

    Laisser l'abonnement en place n'aurait pas de sens : la personne resterait
    dans vos compteurs et continuerait de recevoir vos notifications d'activité.
    """
    if not db.get(Blocage, {"id_bloqueur": id_bloqueur, "id_bloque": id_bloque}):
        db.add(Blocage(id_bloqueur=id_bloqueur, id_bloque=id_bloque))

    db.execute(delete(Abonnement).where(or_(
        (Abonnement.id_suiveur == id_bloqueur) & (Abonnement.id_suivi == id_bloque),
        (Abonnement.id_suiveur == id_bloque) & (Abonnement.id_suivi == id_bloqueur),
    )))
    db.commit()


def debloquer(db: Session, id_bloqueur: int, id_bloque: int) -> None:
    """Retire le blocage. Les abonnements rompus ne sont pas rétablis : ce
    serait présumer d'une intention qui n'a pas été exprimée."""
    db.execute(delete(Blocage).where(Blocage.id_bloqueur == id_bloqueur,
                                     Blocage.id_bloque == id_bloque))
    db.commit()


def signalements_de(db: Session, id_utilisateur: int) -> list[Signalement]:
    return list(db.scalars(select(Signalement).where(
        Signalement.id_signaleur == id_utilisateur)
        .order_by(Signalement.date_signalement.desc())))


def avis_signales_par(db: Session, id_utilisateur: int) -> set[int]:
    """Avis que cette personne a signalés : masqués pour elle immédiatement,
    sans attendre d'arbitrage. C'est honnête et ça ne demande aucun jugement."""
    return set(db.scalars(
        select(Signalement.id_avis).where(
            Signalement.id_signaleur == id_utilisateur,
            Signalement.id_avis.is_not(None))))
