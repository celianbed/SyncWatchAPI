# tests/test_casting.py — distribution des fiches, et son croisement avec
# l'historique de visionnage. C'est ce croisement qui justifie une table de
# casting plutôt qu'un simple passage depuis TMDB : la liste, tout le monde
# l'a ; « vous l'avez déjà vue ailleurs », nous seuls pouvons le dire.
from sqlalchemy import select

from models import Film, Serie
from tests.faux_tmdb import REF_FILM, REF_SERIE


def _h(jeton):
    return {"Authorization": f"Bearer {jeton}"}


def test_casting_serie_ordonne_par_tete_daffiche(client, jeton):
    client.post(f"/series/{REF_SERIE}/suivre", headers=_h(jeton))

    casting = client.get(f"/series/{REF_SERIE}/casting", headers=_h(jeton)).json()

    assert [m["nom"] for m in casting] == ["Alba Rivas", "Jasper Roy"]
    assert casting[0]["personnage"] == "Nora"
    assert casting[0]["photo"] == "/alba.jpg"
    assert all(m["deja_vu_dans"] == 0 for m in casting)


def test_casting_film(client, jeton):
    client.get(f"/films/{REF_FILM}", headers=_h(jeton))

    casting = client.get(f"/films/{REF_FILM}/casting", headers=_h(jeton)).json()

    assert [m["nom"] for m in casting] == ["Alba Rivas", "Milo Fontaine"]
    assert casting[0]["personnage"] == "Elle-même"


def test_actrice_deja_vue_dans_un_autre_titre(client, db, jeton):
    """Le cœur de la fonctionnalité : Alba joue dans la série et dans le film.
    Une fois le film vu, sa fiche série doit le signaler."""
    client.post(f"/series/{REF_SERIE}/suivre", headers=_h(jeton))
    client.get(f"/films/{REF_FILM}", headers=_h(jeton))
    client.post(f"/films/{REF_FILM}/vu", headers=_h(jeton))

    casting = client.get(f"/series/{REF_SERIE}/casting", headers=_h(jeton)).json()
    par_nom = {m["nom"]: m["deja_vu_dans"] for m in casting}

    assert par_nom["Alba Rivas"] == 1
    assert par_nom["Jasper Roy"] == 0, "il ne joue que dans la série"


def test_le_titre_consulte_ne_se_compte_pas_lui_meme(client, db, jeton):
    # sinon toute fiche d'un titre vu afficherait « déjà vu dans 1 titre »,
    # en parlant d'elle-même
    client.get(f"/films/{REF_FILM}", headers=_h(jeton))
    client.post(f"/films/{REF_FILM}/vu", headers=_h(jeton))

    casting = client.get(f"/films/{REF_FILM}/casting", headers=_h(jeton)).json()

    assert all(m["deja_vu_dans"] == 0 for m in casting)


def test_serie_vue_compte_pour_lacteur(client, db, jeton):
    client.post(f"/series/{REF_SERIE}/suivre", headers=_h(jeton))
    saisons = client.get(f"/series/{REF_SERIE}/saisons", headers=_h(jeton)).json()
    client.post(f"/episodes/{saisons[0]['episodes'][0]['id_episode']}/vu",
                headers=_h(jeton))
    client.get(f"/films/{REF_FILM}", headers=_h(jeton))

    casting = client.get(f"/films/{REF_FILM}/casting", headers=_h(jeton)).json()
    par_nom = {m["nom"]: m["deja_vu_dans"] for m in casting}

    assert par_nom["Alba Rivas"] == 1, "un seul épisode suffit à dire « déjà vue »"


def test_casting_dun_titre_absent_du_cache(client, jeton):
    assert client.get("/series/999999/casting", headers=_h(jeton)).status_code == 404
    assert client.get("/films/999999/casting", headers=_h(jeton)).status_code == 404


def test_casting_exige_une_authentification(client):
    assert client.get(f"/series/{REF_SERIE}/casting").status_code == 401


def test_la_distribution_est_remplacee_et_non_accumulee(client, db, jeton):
    # une distribution peut être corrigée chez TMDB ; deux passages ne doivent
    # pas laisser deux fois les mêmes personnes
    client.post(f"/series/{REF_SERIE}/suivre", headers=_h(jeton))
    id_serie = db.scalar(select(Serie.id_serie).where(
        Serie.reference_tmdb == REF_SERIE))
    from services import catalogue_service
    from tests.faux_tmdb import CREDITS_SERIE, SERIE_DETAIL
    catalogue_service.upsert_serie(db, {**SERIE_DETAIL, "credits": CREDITS_SERIE})

    casting = client.get(f"/series/{REF_SERIE}/casting", headers=_h(jeton)).json()
    assert len(casting) == 2
    assert id_serie is not None
