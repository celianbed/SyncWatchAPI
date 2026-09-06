# models/moderation.py — blocage entre personnes, et signalement de contenus.
#
# Exigé par la directive 1.2 de l'App Store dès qu'une app laisse ses
# utilisateurs publier du texte visible par d'autres : pouvoir bloquer
# quelqu'un, et pouvoir signaler un contenu avec une réponse en temps voulu.
from datetime import datetime

from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, Index,
                        String, Text, func)
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class Blocage(Base):
    """Un utilisateur en bloque un autre. Asymétrique et unilatéral : la
    personne bloquée n'en est pas informée, c'est le principe.

    Le blocage est le levier le plus efficace, parce qu'il ne demande aucun
    arbitrage : il agit immédiatement et n'engage que celui qui le pose.
    """

    __tablename__ = "blocage"

    id_bloqueur: Mapped[int] = mapped_column(
        ForeignKey("utilisateur.id_utilisateur", ondelete="CASCADE"), primary_key=True)
    id_bloque: Mapped[int] = mapped_column(
        ForeignKey("utilisateur.id_utilisateur", ondelete="CASCADE"), primary_key=True)
    date_blocage: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("id_bloqueur <> id_bloque", name="chk_pas_auto_blocage"),
        # « qui m'a bloqué » : sert à me retirer de leurs listes
        Index("idx_blocage_bloque", "id_bloque"),
    )


class Signalement(Base):
    """Un contenu ou une personne porté à la connaissance de l'éditeur.

    Aucun seuil automatique : à cette échelle, un compteur serait une arme
    (deux comptes coordonnés enterreraient n'importe quel avis) plutôt qu'une
    protection. Le signalement masque le contenu pour celui qui le signale,
    et l'éditeur tranche — la sanction existant déjà via `statut_compte`.
    """

    __tablename__ = "signalement"

    id_signalement: Mapped[int] = mapped_column(primary_key=True)
    id_signaleur: Mapped[int] = mapped_column(
        ForeignKey("utilisateur.id_utilisateur", ondelete="CASCADE"))
    # arc exclusif : un avis OU une personne
    id_avis: Mapped[int | None] = mapped_column(
        ForeignKey("avis.id_avis", ondelete="CASCADE"))
    id_vise: Mapped[int | None] = mapped_column(
        ForeignKey("utilisateur.id_utilisateur", ondelete="CASCADE"))
    motif: Mapped[str] = mapped_column(String(30))
    precision: Mapped[str | None] = mapped_column(Text)
    date_signalement: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    statut: Mapped[str] = mapped_column(String(20), server_default="nouveau")

    __table_args__ = (
        CheckConstraint(
            "(id_avis IS NOT NULL)::int + (id_vise IS NOT NULL)::int = 1",
            name="chk_signalement_cible"),
        CheckConstraint("statut IN ('nouveau','traite','rejete')",
                        name="chk_statut_signalement"),
        Index("idx_signalement_statut", "statut"),
    )
