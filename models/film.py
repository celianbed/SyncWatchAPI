# models/film.py
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base

if TYPE_CHECKING:
    from models.genre import Genre

categoriser_film = Table(
    "categoriser_film", Base.metadata,
    Column("id_film", ForeignKey("film.id_film", ondelete="CASCADE"), primary_key=True),
    Column("id_genre", ForeignKey("genre.id_genre", ondelete="CASCADE"), primary_key=True),
)


class Film(Base):
    __tablename__ = "film"

    id_film: Mapped[int] = mapped_column(primary_key=True)
    reference_tmdb: Mapped[int] = mapped_column(Integer, unique=True)
    titre: Mapped[str] = mapped_column(String(255))
    titre_original: Mapped[str | None] = mapped_column(String(255))
    synopsis: Mapped[str | None] = mapped_column(Text)
    affiche: Mapped[str | None] = mapped_column(String(500))
    duree: Mapped[int | None] = mapped_column(SmallInteger)
    date_sortie: Mapped[date | None] = mapped_column(Date)
    note_moyenne_tmdb: Mapped[float | None] = mapped_column(Numeric(3, 1))
    date_maj_cache: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    genres: Mapped[list["Genre"]] = relationship(secondary=categoriser_film, back_populates="films")
