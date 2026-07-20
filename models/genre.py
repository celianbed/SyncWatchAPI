# models/genre.py
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base
from models.film import categoriser_film
from models.serie import categoriser_serie

if TYPE_CHECKING:
    from models.film import Film
    from models.serie import Serie


class Genre(Base):
    __tablename__ = "genre"

    id_genre: Mapped[int] = mapped_column(primary_key=True)  # réutiliser l'ID TMDB
    libelle: Mapped[str] = mapped_column(String(50), unique=True)

    series: Mapped[list["Serie"]] = relationship(secondary=categoriser_serie, back_populates="genres")
    films: Mapped[list["Film"]] = relationship(secondary=categoriser_film, back_populates="genres")
