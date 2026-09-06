# models/serie.py
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Table, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base

if TYPE_CHECKING:
    from models.genre import Genre

categoriser_serie = Table(
    "categoriser_serie", Base.metadata,
    Column("id_serie", ForeignKey("serie.id_serie", ondelete="CASCADE"), primary_key=True),
    Column("id_genre", ForeignKey("genre.id_genre", ondelete="CASCADE"), primary_key=True),
)


class Serie(Base):
    __tablename__ = "serie"

    id_serie: Mapped[int] = mapped_column(primary_key=True)
    reference_tmdb: Mapped[int] = mapped_column(Integer, unique=True)
    titre: Mapped[str] = mapped_column(String(255))
    titre_original: Mapped[str | None] = mapped_column(String(255))
    synopsis: Mapped[str | None] = mapped_column(Text)
    affiche: Mapped[str | None] = mapped_column(String(500))
    image_de_fond: Mapped[str | None] = mapped_column(String(500))
    statut_diffusion: Mapped[str | None] = mapped_column(String(25))
    date_premiere_diffusion: Mapped[date | None] = mapped_column(Date)
    note_moyenne_tmdb: Mapped[float | None] = mapped_column(Numeric(3, 1))
    date_maj_cache: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    saisons: Mapped[list["Saison"]] = relationship(
        back_populates="serie", cascade="all, delete-orphan", order_by="Saison.num_saison")
    genres: Mapped[list["Genre"]] = relationship(secondary=categoriser_serie, back_populates="series")


class Saison(Base):
    __tablename__ = "saison"

    id_saison: Mapped[int] = mapped_column(primary_key=True)
    id_serie: Mapped[int] = mapped_column(ForeignKey("serie.id_serie", ondelete="CASCADE"))
    reference_tmdb: Mapped[int] = mapped_column(Integer, unique=True)
    num_saison: Mapped[int] = mapped_column(SmallInteger)  # 0 = épisodes spéciaux
    titre: Mapped[str | None] = mapped_column(String(255))
    affiche: Mapped[str | None] = mapped_column(String(500))
    date_diffusion: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        UniqueConstraint("id_serie", "num_saison", name="uq_saison_numero"),
    )

    serie: Mapped["Serie"] = relationship(back_populates="saisons")
    episodes: Mapped[list["Episode"]] = relationship(
        back_populates="saison", cascade="all, delete-orphan", order_by="Episode.num_episode")


class Episode(Base):
    __tablename__ = "episode"

    id_episode: Mapped[int] = mapped_column(primary_key=True)
    id_saison: Mapped[int] = mapped_column(ForeignKey("saison.id_saison", ondelete="CASCADE"))
    reference_tmdb: Mapped[int] = mapped_column(Integer, unique=True)
    num_episode: Mapped[int] = mapped_column(SmallInteger)
    titre: Mapped[str | None] = mapped_column(String(255))
    synopsis: Mapped[str | None] = mapped_column(Text)
    duree: Mapped[int | None] = mapped_column(SmallInteger)  # minutes
    date_diffusion: Mapped[date | None] = mapped_column(Date)
    vignette: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        UniqueConstraint("id_saison", "num_episode", name="uq_episode_numero"),
        Index("idx_episode_diffusion", "date_diffusion"),  # cron notifications
    )

    saison: Mapped["Saison"] = relationship(back_populates="episodes")
