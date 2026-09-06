# api/visionnage.py — marquage vu/non-vu des épisodes et saisons
from fastapi import APIRouter, Depends, status
from sqlalchemy import delete, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.communs import get_ou_404
from api.dependances import utilisateur_courant
from db.database import get_db
from models import Episode, Saison, Utilisateur, VisionnerEpisode
from schemas.visionnage import EpisodeVu, SaisonNonVue, SaisonVue

router = APIRouter()


@router.post("/episodes/{id_episode}/vu", response_model=EpisodeVu,
             status_code=status.HTTP_201_CREATED)
def marquer_episode_vu(
    id_episode: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Marque un épisode vu ; re-marquer compte un revisionnage."""
    get_ou_404(db, Episode, id_episode, "Épisode introuvable.")

    requete = insert(VisionnerEpisode).values(
        id_utilisateur=utilisateur.id_utilisateur, id_episode=id_episode)
    db.execute(requete.on_conflict_do_update(
        index_elements=["id_utilisateur", "id_episode"],
        set_={"nombre_revisionnage": VisionnerEpisode.nombre_revisionnage + 1,
              "date_visionnage": func.now()}))
    db.commit()
    return db.get(VisionnerEpisode, {"id_utilisateur": utilisateur.id_utilisateur,
                                     "id_episode": id_episode})


@router.delete("/episodes/{id_episode}/vu", status_code=status.HTTP_204_NO_CONTENT)
def retirer_episode_vu(
    id_episode: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    vu = get_ou_404(db, VisionnerEpisode,
                    {"id_utilisateur": utilisateur.id_utilisateur, "id_episode": id_episode},
                    "Épisode non marqué comme vu.")
    db.delete(vu)
    db.commit()


@router.post("/saisons/{id_saison}/vu", response_model=SaisonVue)
def marquer_saison_vue(
    id_saison: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Marque vus tous les épisodes déjà diffusés de la saison (les vus restent vus)."""
    get_ou_404(db, Saison, id_saison, "Saison introuvable.")

    diffusees = (select(literal(utilisateur.id_utilisateur), Episode.id_episode)
                 .where(Episode.id_saison == id_saison,
                        Episode.date_diffusion.is_not(None),
                        Episode.date_diffusion <= func.current_date()))
    resultat = db.execute(insert(VisionnerEpisode).from_select(
        ["id_utilisateur", "id_episode"], diffusees).on_conflict_do_nothing())
    db.commit()
    return SaisonVue(episodes_marques=resultat.rowcount)


@router.delete("/saisons/{id_saison}/vu", response_model=SaisonNonVue)
def retirer_saison_vue(
    id_saison: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Défait un « tout marquer vu » : la saison entière redevient non vue.
    Sans cette route, un clic sur « Tout marquer vu » était définitif."""
    get_ou_404(db, Saison, id_saison, "Saison introuvable.")

    de_la_saison = select(Episode.id_episode).where(Episode.id_saison == id_saison)
    resultat = db.execute(delete(VisionnerEpisode).where(
        VisionnerEpisode.id_utilisateur == utilisateur.id_utilisateur,
        VisionnerEpisode.id_episode.in_(de_la_saison)))
    db.commit()
    return SaisonNonVue(episodes_retires=resultat.rowcount)
