# services/visionnage_service.py — les requêtes signature du suivi de visionnage
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from models import Episode, Saison, Serie, SuivreSerie, VisionnerEpisode

# les statuts de suivi pour lesquels l'accueil propose un épisode
STATUTS_ACTIFS = ("a_voir", "en_cours")


def _episodes_vus(id_utilisateur: int):
    return select(VisionnerEpisode.id_episode).where(
        VisionnerEpisode.id_utilisateur == id_utilisateur)


def accueil(db: Session, id_utilisateur: int):
    """« À regarder ce soir » : le prochain épisode déjà diffusé de chaque
    série suivie active. Renvoie des lignes (Episode, num_saison, Serie).
    """
    rang = func.row_number().over(
        partition_by=Saison.id_serie,
        order_by=(Saison.num_saison, Episode.num_episode)).label("rang")
    candidats = (
        select(Episode.id_episode, rang)
        .join(Saison, Episode.id_saison == Saison.id_saison)
        .join(SuivreSerie, and_(
            SuivreSerie.id_serie == Saison.id_serie,
            SuivreSerie.id_utilisateur == id_utilisateur,
            SuivreSerie.statut_suivi.in_(STATUTS_ACTIFS)))
        .where(Saison.num_saison > 0,
               Episode.id_episode.not_in(_episodes_vus(id_utilisateur)),
               Episode.date_diffusion.is_not(None),
               Episode.date_diffusion <= func.current_date())
        .subquery())

    return db.execute(
        select(Episode, Saison.num_saison, Serie)
        .join(candidats, candidats.c.id_episode == Episode.id_episode)
        .join(Saison, Episode.id_saison == Saison.id_saison)
        .join(Serie, Saison.id_serie == Serie.id_serie)
        .where(candidats.c.rang == 1)
        .order_by(Serie.titre)).all()


def calendrier(db: Session, id_utilisateur: int, jours: int):
    """Diffusions à venir (aujourd'hui inclus) des séries suivies actives.

    Renvoie des lignes (Episode, num_saison, Serie) triées par date de diffusion.
    """
    return db.execute(
        select(Episode, Saison.num_saison, Serie)
        .join(Saison, Episode.id_saison == Saison.id_saison)
        .join(Serie, Saison.id_serie == Serie.id_serie)
        .join(SuivreSerie, and_(
            SuivreSerie.id_serie == Serie.id_serie,
            SuivreSerie.id_utilisateur == id_utilisateur,
            SuivreSerie.statut_suivi.in_(STATUTS_ACTIFS)))
        .where(Episode.date_diffusion.is_not(None),
               Episode.date_diffusion >= func.current_date(),
               Episode.date_diffusion <= func.current_date() + jours)
        .order_by(Episode.date_diffusion, Serie.titre,
                  Saison.num_saison, Episode.num_episode)).all()
