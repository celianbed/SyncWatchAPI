# tests/test_social.py
from sqlalchemy import select

from models import Utilisateur
from tests.faux_tmdb import REF_FILM, REF_SERIE


def _h(jeton):
    return {"Authorization": f"Bearer {jeton}"}


def _id(db, pseudo):
    return db.scalar(select(Utilisateur).where(
        Utilisateur.pseudo == pseudo)).id_utilisateur


def _jeton_de(client, pseudo, mdp="motdepasse123"):
    return client.post("/auth/connexion",
                       data={"username": pseudo, "password": mdp}).json()["access_token"]


def test_abonner_et_profil(client, db, jeton, inscrire):
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    id_bob, id_celian = _id(db, "bob"), _id(db, "celian")

    assert client.post(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton)).status_code == 201

    profil = client.get(f"/utilisateurs/{id_bob}", headers=_h(jeton)).json()
    assert profil["est_abonne"] is True
    assert profil["nb_abonnes"] == 1
    assert profil["est_ami"] is False
    assert "adresse_mail" not in profil  # jamais de fuite d'email

    abos = client.get(f"/utilisateurs/{id_celian}/abonnements", headers=_h(jeton)).json()
    assert [u["pseudo"] for u in abos] == ["bob"]
    abonnes = client.get(f"/utilisateurs/{id_bob}/abonnes", headers=_h(jeton)).json()
    assert [u["pseudo"] for u in abonnes] == ["celian"]


def test_amitie_mutuelle(client, db, jeton, inscrire):
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    id_bob, id_celian = _id(db, "bob"), _id(db, "celian")
    jeton_bob = _jeton_de(client, "bob")

    client.post(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton))        # celian -> bob
    client.post(f"/utilisateurs/{id_celian}/abonner", headers=_h(jeton_bob))  # bob -> celian

    profil = client.get(f"/utilisateurs/{id_bob}", headers=_h(jeton)).json()
    assert profil["est_ami"] is True
    assert profil["me_suit"] is True


def test_desabonner(client, db, jeton, inscrire):
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    id_bob = _id(db, "bob")
    client.post(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton))

    assert client.delete(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton)).status_code == 204
    profil = client.get(f"/utilisateurs/{id_bob}", headers=_h(jeton)).json()
    assert profil["est_abonne"] is False
    # re-désabonner = 404
    assert client.delete(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton)).status_code == 404


def test_abonner_soi_meme_et_inconnu(client, db, jeton):
    id_celian = _id(db, "celian")
    assert client.post(f"/utilisateurs/{id_celian}/abonner", headers=_h(jeton)).status_code == 400
    assert client.post("/utilisateurs/999999/abonner", headers=_h(jeton)).status_code == 404


def test_double_abonnement_409(client, db, jeton, inscrire):
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    id_bob = _id(db, "bob")
    client.post(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton))
    assert client.post(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton)).status_code == 409


def test_recherche_utilisateurs(client, db, jeton, inscrire):
    inscrire(pseudo="bobby", adresse_mail="bob@example.com")
    inscrire(pseudo="alice", adresse_mail="alice@example.com")
    res = client.get("/search/utilisateurs", params={"q": "bob"}, headers=_h(jeton)).json()
    assert [u["pseudo"] for u in res] == ["bobby"]
    # soi-même exclu de ses propres résultats
    assert client.get("/search/utilisateurs", params={"q": "celian"}, headers=_h(jeton)).json() == []


def test_avis_profil_titre_et_note(client, db, jeton):
    # suivre la série (la met en cache), puis noter (note seule, pas de commentaire)
    id_serie = client.post(f"/series/{REF_SERIE}/suivre", headers=_h(jeton)).json()["id_serie"]
    client.post("/avis", headers=_h(jeton), json={"id_serie": id_serie, "note": 9})

    id_celian = _id(db, "celian")
    avis = client.get(f"/utilisateurs/{id_celian}/avis", headers=_h(jeton)).json()
    assert len(avis) == 1
    assert avis[0]["note"] == 9
    assert avis[0]["type"] == "serie"
    assert avis[0]["titre"]  # titre résolu
    assert avis[0]["reference_tmdb"] == REF_SERIE
    assert "commentaire" not in avis[0]  # juste la note


def test_avis_profil_vide(client, db, jeton, inscrire):
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    assert client.get(f"/utilisateurs/{_id(db, 'bob')}/avis", headers=_h(jeton)).json() == []


def test_avis_de_mes_abonnements(client, db, jeton, inscrire):
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    inscrire(pseudo="carol", adresse_mail="carol@example.com")
    id_bob = _id(db, "bob")
    client.post(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton))  # celian suit bob

    jeton_bob, jeton_carol = _jeton_de(client, "bob"), _jeton_de(client, "carol")
    id_serie = client.post(f"/series/{REF_SERIE}/suivre",
                           headers=_h(jeton_bob)).json()["id_serie"]
    client.post("/avis", headers=_h(jeton_bob),
                json={"id_serie": id_serie, "note": 9, "commentaire": "Top"})
    client.post(f"/series/{REF_SERIE}/suivre", headers=_h(jeton_carol))
    client.post("/avis", headers=_h(jeton_carol), json={"id_serie": id_serie, "note": 3})

    # celian voit l'avis de bob (suivi), pas celui de carol (non suivie)
    avis = client.get("/avis/abonnements", params={"id_serie": id_serie},
                      headers=_h(jeton)).json()
    assert len(avis) == 1
    assert avis[0]["utilisateur"]["pseudo"] == "bob"
    assert "avatar" in avis[0]["utilisateur"]
    assert avis[0]["note"] == 9
    assert avis[0]["commentaire"] == "Top"


def test_compatibilite_sur_les_notes(client, db, jeton, inscrire):
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    id_bob = _id(db, "bob")
    jeton_bob = _jeton_de(client, "bob")
    id_serie = client.post(f"/series/{REF_SERIE}/suivre",
                           headers=_h(jeton)).json()["id_serie"]
    client.post(f"/series/{REF_SERIE}/suivre", headers=_h(jeton_bob))
    client.post("/avis", headers=_h(jeton), json={"id_serie": id_serie, "note": 8})
    client.post("/avis", headers=_h(jeton_bob), json={"id_serie": id_serie, "note": 8})

    r = client.get(f"/utilisateurs/{id_bob}/compatibilite", headers=_h(jeton)).json()
    assert r["base"] == "notes"
    assert r["pourcentage"] == 100  # notes identiques
    assert r["titres_communs"] == 1


def test_compatibilite_aucune_donnee(client, db, jeton, inscrire):
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    r = client.get(f"/utilisateurs/{_id(db, 'bob')}/compatibilite",
                   headers=_h(jeton)).json()
    assert r == {"pourcentage": 0, "titres_communs": 0, "base": "aucune"}


def test_fil_activite(client, db, jeton, inscrire):
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    inscrire(pseudo="carol", adresse_mail="carol@example.com")
    id_bob = _id(db, "bob")
    client.post(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton))  # celian suit bob

    jeton_bob = _jeton_de(client, "bob")
    id_serie = client.post(f"/series/{REF_SERIE}/suivre",
                           headers=_h(jeton_bob)).json()["id_serie"]
    client.post(f"/films/{REF_FILM}/vu", headers=_h(jeton_bob))
    client.post("/avis", headers=_h(jeton_bob), json={"id_serie": id_serie, "note": 8})

    # carol (non suivie) agit aussi → doit être exclue du fil de celian
    client.post(f"/films/{REF_FILM}/vu", headers=_h(_jeton_de(client, "carol")))

    fil = client.get("/activite", headers=_h(jeton)).json()
    assert {e["type"] for e in fil} == {"serie_suivie", "film_vu", "avis"}
    assert all(e["acteur"]["pseudo"] == "bob" for e in fil)  # carol exclue
    dates = [e["date"] for e in fil]
    assert dates == sorted(dates, reverse=True)  # trié par date décroissante


def test_suivre_cree_une_notif(client, db, jeton, inscrire):
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    id_bob = _id(db, "bob")
    jeton_bob = _jeton_de(client, "bob")
    client.post(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton))  # celian suit bob

    notifs = client.get("/notifications", headers=_h(jeton_bob)).json()
    assert any(n["type"] == "abonnement" and "celian" in n["contenu"] for n in notifs)


def test_recommander_cree_une_notif(client, db, jeton, inscrire):
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    id_bob = _id(db, "bob")
    jeton_bob = _jeton_de(client, "bob")

    client.post(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton))
    r = client.post(f"/utilisateurs/{id_bob}/recommander", headers=_h(jeton),
                    json={"reference_tmdb": REF_SERIE, "type": "serie"})
    assert r.status_code == 201

    notifs = client.get("/notifications", headers=_h(jeton_bob)).json()
    reco = next(n for n in notifs if n["type"] == "recommandation")
    assert "celian" in reco["contenu"]
    assert reco["reference_tmdb"] == REF_SERIE  # tap → fiche
    assert reco["cible"] == "serie"


def test_recommander_soi_meme_refuse(client, db, jeton):
    id_celian = _id(db, "celian")
    r = client.post(f"/utilisateurs/{id_celian}/recommander", headers=_h(jeton),
                    json={"reference_tmdb": REF_SERIE, "type": "serie"})
    assert r.status_code == 400


def test_progression_abonnements(client, db, jeton, inscrire):
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    id_bob = _id(db, "bob")
    client.post(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton))  # celian suit bob
    jeton_bob = _jeton_de(client, "bob")
    client.post(f"/series/{REF_SERIE}/suivre", headers=_h(jeton_bob))  # cache les épisodes

    # bob regarde le 1er épisode
    saisons = client.get(f"/series/{REF_SERIE}/saisons", headers=_h(jeton_bob)).json()
    id_ep1 = saisons[0]["episodes"][0]["id_episode"]
    client.post(f"/episodes/{id_ep1}/vu", headers=_h(jeton_bob))

    prog = client.get(f"/series/{REF_SERIE}/progression-abonnements",
                      headers=_h(jeton)).json()
    assert len(prog) == 1
    assert prog[0]["pseudo"] == "bob"
    assert prog[0]["episodes_vus"] == 1
    assert prog[0]["total_episodes"] >= 1
    assert prog[0]["prochain_code"] is not None  # bob n'a pas fini


def test_social_exige_authentification(client, db, jeton, inscrire):
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    id_bob = _id(db, "bob")
    assert client.post(f"/utilisateurs/{id_bob}/abonner").status_code == 401
    assert client.get("/search/utilisateurs", params={"q": "bob"}).status_code == 401


def test_recommander_a_un_inconnu_refuse(client, db, jeton, inscrire):
    """Sans lien social, on pourrait faire sonner le téléphone de n'importe qui."""
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    id_bob = _id(db, "bob")

    r = client.post(f"/utilisateurs/{id_bob}/recommander", headers=_h(jeton),
                    json={"reference_tmdb": REF_SERIE, "type": "serie"})
    assert r.status_code == 403
    assert client.get("/notifications", headers=_h(_jeton_de(client, "bob"))).json() == []


def test_recommander_plafonne_par_jour(client, db, jeton, inscrire):
    """Suivre quelqu'un est libre : sans plafond, le lien social ne protégerait
    de rien et la recommandation deviendrait un canal de spam."""
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    id_bob = _id(db, "bob")
    client.post(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton))

    envoi = lambda: client.post(  # noqa: E731
        f"/utilisateurs/{id_bob}/recommander", headers=_h(jeton),
        json={"reference_tmdb": REF_SERIE, "type": "serie"})

    for _ in range(3):
        assert envoi().status_code == 201
    assert envoi().status_code == 429


def test_le_plafond_est_par_destinataire(client, db, jeton, inscrire):
    # avoir saturé bob ne doit pas empêcher d'écrire à claire
    for pseudo in ("bob", "claire"):
        inscrire(pseudo=pseudo, adresse_mail=f"{pseudo}@example.com")
    id_bob, id_claire = _id(db, "bob"), _id(db, "claire")
    for cible in (id_bob, id_claire):
        client.post(f"/utilisateurs/{cible}/abonner", headers=_h(jeton))

    for _ in range(3):
        client.post(f"/utilisateurs/{id_bob}/recommander", headers=_h(jeton),
                    json={"reference_tmdb": REF_SERIE, "type": "serie"})

    r = client.post(f"/utilisateurs/{id_claire}/recommander", headers=_h(jeton),
                    json={"reference_tmdb": REF_SERIE, "type": "serie"})
    assert r.status_code == 201
