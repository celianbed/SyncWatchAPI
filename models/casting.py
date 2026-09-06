# models/casting.py — distribution des séries et des films.
#
# Deux tables d'association plutôt qu'une seule à cible polymorphe : une clé
# primaire ne peut pas porter de NULL en PostgreSQL, et « id_serie OU id_film »
# imposerait des contorsions. C'est déjà le parti pris des genres
# (categoriser_serie / categoriser_film).
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base

if TYPE_CHECKING:
    pass


class Acteur(Base):
    __tablename__ = "acteur"

    id_acteur: Mapped[int] = mapped_column(primary_key=True)  # réutiliser l'ID TMDB
    nom: Mapped[str] = mapped_column(String(255))
    photo: Mapped[str | None] = mapped_column(String(500))


class CastingSerie(Base):
    __tablename__ = "casting_serie"

    id_serie: Mapped[int] = mapped_column(
        ForeignKey("serie.id_serie", ondelete="CASCADE"), primary_key=True)
    id_acteur: Mapped[int] = mapped_column(
        ForeignKey("acteur.id_acteur", ondelete="CASCADE"), primary_key=True)
    personnage: Mapped[str | None] = mapped_column(String(255))
    # rang TMDB : sert à ne garder que les têtes d'affiche, et à les ordonner
    ordre: Mapped[int] = mapped_column(SmallInteger, server_default="0")

    acteur: Mapped["Acteur"] = relationship()


class CastingFilm(Base):
    __tablename__ = "casting_film"

    id_film: Mapped[int] = mapped_column(
        ForeignKey("film.id_film", ondelete="CASCADE"), primary_key=True)
    id_acteur: Mapped[int] = mapped_column(
        ForeignKey("acteur.id_acteur", ondelete="CASCADE"), primary_key=True)
    personnage: Mapped[str | None] = mapped_column(String(255))
    ordre: Mapped[int] = mapped_column(SmallInteger, server_default="0")

    acteur: Mapped["Acteur"] = relationship()
