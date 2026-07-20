# models/avis.py
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base

if TYPE_CHECKING:
    from models.utilisateur import Utilisateur


class Avis(Base):
    __tablename__ = "avis"

    id_avis: Mapped[int] = mapped_column(primary_key=True)
    id_utilisateur: Mapped[int] = mapped_column(
        ForeignKey("utilisateur.id_utilisateur", ondelete="CASCADE"))
    id_serie: Mapped[int | None] = mapped_column(ForeignKey("serie.id_serie", ondelete="CASCADE"))
    id_film: Mapped[int | None] = mapped_column(ForeignKey("film.id_film", ondelete="CASCADE"))
    id_episode: Mapped[int | None] = mapped_column(ForeignKey("episode.id_episode", ondelete="CASCADE"))
    note: Mapped[int | None] = mapped_column(SmallInteger)
    commentaire: Mapped[str | None] = mapped_column(Text)
    date_creation: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    date_modification: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())

    __table_args__ = (
        # arc exclusif : exactement une cible
        CheckConstraint(
            "(id_serie IS NOT NULL)::int + (id_film IS NOT NULL)::int "
            "+ (id_episode IS NOT NULL)::int = 1",
            name="chk_avis_cible"),
        CheckConstraint("note BETWEEN 1 AND 10", name="chk_note"),
        CheckConstraint("note IS NOT NULL OR commentaire IS NOT NULL", name="chk_avis_contenu"),
    )

    utilisateur: Mapped["Utilisateur"] = relationship(back_populates="avis")
