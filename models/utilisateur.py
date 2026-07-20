# models/utilisateur.py
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base

if TYPE_CHECKING:
    from models.avis import Avis
    from models.notification import Appareil, Notification
    from models.suivi import SuivreFilm, SuivreSerie, VisionnerEpisode, VisionnerFilm


class Utilisateur(Base):
    __tablename__ = "utilisateur"

    id_utilisateur: Mapped[int] = mapped_column(primary_key=True)
    adresse_mail: Mapped[str] = mapped_column(String(255), unique=True)
    mot_de_passe: Mapped[str] = mapped_column(String(255))  # hash bcrypt/argon2
    pseudo: Mapped[str] = mapped_column(String(30), unique=True)
    avatar: Mapped[str | None] = mapped_column(String(500))
    date_inscription: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    date_derniere_connexion: Mapped[datetime | None] = mapped_column(DateTime)
    statut_compte: Mapped[str] = mapped_column(String(20), server_default="actif")

    __table_args__ = (
        CheckConstraint("statut_compte IN ('actif','suspendu','supprime')", name="chk_statut_compte"),
    )

    suivis_series: Mapped[list["SuivreSerie"]] = relationship(back_populates="utilisateur", cascade="all, delete-orphan")
    visionnages: Mapped[list["VisionnerEpisode"]] = relationship(back_populates="utilisateur", cascade="all, delete-orphan")
    suivis_films: Mapped[list["SuivreFilm"]] = relationship(back_populates="utilisateur", cascade="all, delete-orphan")
    visionnages_films: Mapped[list["VisionnerFilm"]] = relationship(back_populates="utilisateur", cascade="all, delete-orphan")
    avis: Mapped[list["Avis"]] = relationship(back_populates="utilisateur", cascade="all, delete-orphan")
    appareils: Mapped[list["Appareil"]] = relationship(back_populates="utilisateur", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="utilisateur", cascade="all, delete-orphan")
