# models/utilisateur.py
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base

if TYPE_CHECKING:
    from models.abonnement import Abonnement
    from models.avis import Avis
    from models.notification import Appareil, Notification
    from models.suivi import SuivreFilm, SuivreSerie, VisionnerEpisode, VisionnerFilm


class Utilisateur(Base):
    __tablename__ = "utilisateur"

    id_utilisateur: Mapped[int] = mapped_column(primary_key=True)
    adresse_mail: Mapped[str] = mapped_column(String(255), unique=True)
    # null = compte créé via un fournisseur externe (Google) : pas de mot de passe
    mot_de_passe: Mapped[str | None] = mapped_column(String(255))
    pseudo: Mapped[str] = mapped_column(String(30), unique=True)
    avatar: Mapped[str | None] = mapped_column(String(500))
    date_inscription: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    date_derniere_connexion: Mapped[datetime | None] = mapped_column(DateTime)
    statut_compte: Mapped[str] = mapped_column(String(20), server_default="actif")
    est_verifie: Mapped[bool] = mapped_column(Boolean, server_default="false")
    # Identifiant stable Sign in with Apple (claim "sub" du jeton). Apple ne donne
    # l'adresse mail qu'à la première autorisation, et souvent un relais privé
    # (@privaterelay.appleid.com) : le "sub" est le seul lien fiable vers le compte.
    sub_apple: Mapped[str | None] = mapped_column(String(255), unique=True)
    # Jeton de rafraîchissement Apple, seulement gardé pour pouvoir révoquer l'accès
    # à la suppression du compte — Apple l'exige (App Store 5.1.1(v)).
    jeton_revocation_apple: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        CheckConstraint("statut_compte IN ('actif','suspendu','supprime')", name="chk_statut_compte"),
    )

    suivis_series: Mapped[list["SuivreSerie"]] = relationship(back_populates="utilisateur", cascade="all, delete-orphan")
    visionnages: Mapped[list["VisionnerEpisode"]] = relationship(back_populates="utilisateur", cascade="all, delete-orphan")
    suivis_films: Mapped[list["SuivreFilm"]] = relationship(back_populates="utilisateur", cascade="all, delete-orphan")
    visionnages_films: Mapped[list["VisionnerFilm"]] = relationship(back_populates="utilisateur", cascade="all, delete-orphan")
    avis: Mapped[list["Avis"]] = relationship(back_populates="utilisateur", cascade="all, delete-orphan")
    appareils: Mapped[list["Appareil"]] = relationship(back_populates="utilisateur", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship(
        foreign_keys="Notification.id_utilisateur",
        back_populates="utilisateur", cascade="all, delete-orphan")
    # abonnements = les gens que JE suis ; abonnes = les gens qui ME suivent
    abonnements: Mapped[list["Abonnement"]] = relationship(
        foreign_keys="Abonnement.id_suiveur", back_populates="suiveur", cascade="all, delete-orphan")
    abonnes: Mapped[list["Abonnement"]] = relationship(
        foreign_keys="Abonnement.id_suivi", back_populates="suivi", cascade="all, delete-orphan")
