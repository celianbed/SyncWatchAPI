# models/abonnement.py
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base

if TYPE_CHECKING:
    from models.utilisateur import Utilisateur


class Abonnement(Base):
    """Un utilisateur (suiveur) s'abonne à un autre (suivi). Relation asymétrique.

    Le suivi **mutuel** (A→B et B→A) définit l'« amitié » : calculée à la volée,
    jamais stockée. Débloque plus tard les fonctions intimes (progression partagée…).
    """

    __tablename__ = "abonnement"

    id_suiveur: Mapped[int] = mapped_column(
        ForeignKey("utilisateur.id_utilisateur", ondelete="CASCADE"), primary_key=True)
    id_suivi: Mapped[int] = mapped_column(
        ForeignKey("utilisateur.id_utilisateur", ondelete="CASCADE"), primary_key=True)
    date_abonnement: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("id_suiveur <> id_suivi", name="chk_pas_auto_abonnement"),
        Index("idx_abonnement_suivi", "id_suivi"),  # « qui me suit » (abonnés)
    )

    suiveur: Mapped["Utilisateur"] = relationship(
        foreign_keys=[id_suiveur], back_populates="abonnements")
    suivi: Mapped["Utilisateur"] = relationship(
        foreign_keys=[id_suivi], back_populates="abonnes")
