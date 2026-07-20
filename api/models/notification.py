# api/models/notification.py
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.database import Base

if TYPE_CHECKING:
    from api.models.utilisateur import Utilisateur


class Appareil(Base):
    __tablename__ = "appareil"

    id_appareil: Mapped[int] = mapped_column(primary_key=True)
    id_utilisateur: Mapped[int] = mapped_column(
        ForeignKey("utilisateur.id_utilisateur", ondelete="CASCADE"))
    jeton_notif: Mapped[str] = mapped_column(String(500), unique=True)
    plateforme: Mapped[str] = mapped_column(String(10))
    date_enregistrement: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    date_derniere_activite: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        CheckConstraint("plateforme IN ('android','ios','web')", name="chk_plateforme"),
    )

    utilisateur: Mapped["Utilisateur"] = relationship(back_populates="appareils")


class Notification(Base):
    __tablename__ = "notification"

    id_notification: Mapped[int] = mapped_column(primary_key=True)
    id_utilisateur: Mapped[int] = mapped_column(
        ForeignKey("utilisateur.id_utilisateur", ondelete="CASCADE"))
    id_episode: Mapped[int | None] = mapped_column(ForeignKey("episode.id_episode", ondelete="CASCADE"))
    id_serie: Mapped[int | None] = mapped_column(ForeignKey("serie.id_serie", ondelete="CASCADE"))
    id_film: Mapped[int | None] = mapped_column(ForeignKey("film.id_film", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(30))
    contenu: Mapped[str] = mapped_column(String(255))
    date_envoi: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    lue: Mapped[bool] = mapped_column(Boolean, server_default="false")

    __table_args__ = (
        # au plus une cible (zéro = notification système)
        CheckConstraint(
            "(id_episode IS NOT NULL)::int + (id_serie IS NOT NULL)::int "
            "+ (id_film IS NOT NULL)::int <= 1",
            name="chk_notif_cible"),
        CheckConstraint(
            "type IN ('nouvel_episode','nouvelle_saison','sortie_film','systeme','rappel')",
            name="chk_type_notif"),
        Index("idx_notif_user", "id_utilisateur", "lue"),
    )

    utilisateur: Mapped["Utilisateur"] = relationship(back_populates="notifications")
