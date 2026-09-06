# models/suivi.py — associations avec données portées
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base

if TYPE_CHECKING:
    from models.film import Film
    from models.serie import Episode, Serie
    from models.utilisateur import Utilisateur


class SuivreSerie(Base):
    __tablename__ = "suivre_serie"

    id_utilisateur: Mapped[int] = mapped_column(
        ForeignKey("utilisateur.id_utilisateur", ondelete="CASCADE"), primary_key=True)
    id_serie: Mapped[int] = mapped_column(
        ForeignKey("serie.id_serie", ondelete="CASCADE"), primary_key=True)
    statut_suivi: Mapped[str] = mapped_column(String(25))
    favori: Mapped[bool] = mapped_column(Boolean, server_default="false")
    date_ajout: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "statut_suivi IN ('a_voir','en_cours','terminee','abandonnee','en_pause')",
            name="chk_statut_suivi"),
    )

    utilisateur: Mapped["Utilisateur"] = relationship(back_populates="suivis_series")
    serie: Mapped["Serie"] = relationship()


class VisionnerEpisode(Base):
    __tablename__ = "visionner_episode"

    id_utilisateur: Mapped[int] = mapped_column(
        ForeignKey("utilisateur.id_utilisateur", ondelete="CASCADE"), primary_key=True)
    id_episode: Mapped[int] = mapped_column(
        ForeignKey("episode.id_episode", ondelete="CASCADE"), primary_key=True)
    date_visionnage: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    nombre_revisionnage: Mapped[int] = mapped_column(Integer, server_default="0")

    __table_args__ = (
        Index("idx_visionner_user", "id_utilisateur", "date_visionnage"),  # stats
    )

    utilisateur: Mapped["Utilisateur"] = relationship(back_populates="visionnages")
    episode: Mapped["Episode"] = relationship()


class SuivreFilm(Base):
    __tablename__ = "suivre_film"

    id_utilisateur: Mapped[int] = mapped_column(
        ForeignKey("utilisateur.id_utilisateur", ondelete="CASCADE"), primary_key=True)
    id_film: Mapped[int] = mapped_column(
        ForeignKey("film.id_film", ondelete="CASCADE"), primary_key=True)
    statut: Mapped[str] = mapped_column(String(10))
    favori: Mapped[bool] = mapped_column(Boolean, server_default="false")

    __table_args__ = (
        CheckConstraint("statut IN ('a_voir','vu')", name="chk_statut_film"),
    )

    utilisateur: Mapped["Utilisateur"] = relationship(back_populates="suivis_films")
    film: Mapped["Film"] = relationship()


class VisionnerFilm(Base):
    __tablename__ = "visionner_film"

    # date dans la PK : plusieurs visionnages du même film possibles
    id_utilisateur: Mapped[int] = mapped_column(
        ForeignKey("utilisateur.id_utilisateur", ondelete="CASCADE"), primary_key=True)
    id_film: Mapped[int] = mapped_column(
        ForeignKey("film.id_film", ondelete="CASCADE"), primary_key=True)
    date_visionnage: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, server_default=func.now())

    utilisateur: Mapped["Utilisateur"] = relationship(back_populates="visionnages_films")
    film: Mapped["Film"] = relationship()
