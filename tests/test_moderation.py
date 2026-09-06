# tests/test_moderation.py — blocage et signalement, exigés par la directive 1.2
# de l'App Store dès qu'une app laisse publier du texte visible par d'autres.
from sqlalchemy import select

from models import Abonnement, Blocage, Utilisateur
from tests.faux_tmdb import REF_SERIE


def _h(jeton):
    return {"Authorization": f"Bearer {jeton}"}


def _id(db, pseudo):
    return db.scalar(select(Utilisateur.id_utilisateur).where(
        Utilisateur.pseudo == pseudo))


def _jeton_de(client, pseudo, mdp="motdepasse123"):
    return client.post("/auth/connexion",
                       data={"username": pseudo, "password": mdp}).json()["access_token"]


def _bob(client, db, inscrire):
    inscrire(pseudo="bob", adresse_mail="bob@example.com")
    return _id(db, "bob"), _jeton_de(client, "bob")


class TestBlocage:
    def test_bloquer_rompt_les_abonnements_dans_les_deux_sens(
            self, client, db, jeton, inscrire):
        id_bob, jeton_bob = _bob(client, db, inscrire)
        id_moi = _id(db, "celian")
        client.post(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton))
        client.post(f"/utilisateurs/{id_moi}/abonner", headers=_h(jeton_bob))

        assert client.post(f"/utilisateurs/{id_bob}/bloquer",
                           headers=_h(jeton)).status_code == 201

        # laisser l'abonnement en place le garderait dans les compteurs et
        # continuerait de lui pousser mon activité
        assert db.scalars(select(Abonnement)).all() == []

    def test_une_personne_bloquee_devient_introuvable(
            self, client, db, jeton, inscrire):
        id_bob, _ = _bob(client, db, inscrire)
        client.post(f"/utilisateurs/{id_bob}/bloquer", headers=_h(jeton))

        # le même 404 que pour un compte inexistant : dire « vous êtes bloqué »
        # renseignerait la personne bloquée
        assert client.get(f"/utilisateurs/{id_bob}",
                          headers=_h(jeton)).status_code == 404
        assert client.get("/search/utilisateurs", headers=_h(jeton),
                          params={"q": "bob"}).json() == []

    def test_le_masquage_vaut_dans_les_deux_sens(self, client, db, jeton, inscrire):
        """Sans réciprocité, la personne bloquée continuerait de me lire."""
        id_bob, jeton_bob = _bob(client, db, inscrire)
        id_moi = _id(db, "celian")
        client.post(f"/utilisateurs/{id_bob}/bloquer", headers=_h(jeton))

        assert client.get(f"/utilisateurs/{id_moi}",
                          headers=_h(jeton_bob)).status_code == 404

    def test_impossible_de_s_abonner_malgre_un_blocage(
            self, client, db, jeton, inscrire):
        id_bob, jeton_bob = _bob(client, db, inscrire)
        id_moi = _id(db, "celian")
        client.post(f"/utilisateurs/{id_bob}/bloquer", headers=_h(jeton))

        assert client.post(f"/utilisateurs/{id_moi}/abonner",
                           headers=_h(jeton_bob)).status_code == 403

    def test_les_avis_d_une_personne_bloquee_disparaissent(
            self, client, db, jeton, inscrire):
        id_bob, jeton_bob = _bob(client, db, inscrire)
        client.post(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton))
        id_serie = client.post(f"/series/{REF_SERIE}/suivre",
                               headers=_h(jeton)).json()["id_serie"]
        client.post("/avis", headers=_h(jeton_bob),
                    json={"id_serie": id_serie, "note": 9, "commentaire": "Génial"})

        avant = client.get("/avis/abonnements", headers=_h(jeton),
                           params={"id_serie": id_serie}).json()
        assert len(avant) == 1

        client.post(f"/utilisateurs/{id_bob}/bloquer", headers=_h(jeton))
        apres = client.get("/avis/abonnements", headers=_h(jeton),
                           params={"id_serie": id_serie}).json()
        assert apres == []

    def test_debloquer_ne_retablit_pas_les_abonnements(
            self, client, db, jeton, inscrire):
        # rétablir présumerait d'une intention qui n'a pas été exprimée
        id_bob, _ = _bob(client, db, inscrire)
        client.post(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton))
        client.post(f"/utilisateurs/{id_bob}/bloquer", headers=_h(jeton))

        assert client.delete(f"/utilisateurs/{id_bob}/bloquer",
                             headers=_h(jeton)).status_code == 204
        assert db.scalars(select(Blocage)).all() == []
        assert db.scalars(select(Abonnement)).all() == []
        assert client.get(f"/utilisateurs/{id_bob}",
                          headers=_h(jeton)).status_code == 200

    def test_on_ne_se_bloque_pas_soi_meme(self, client, db, jeton):
        id_moi = _id(db, "celian")
        assert client.post(f"/utilisateurs/{id_moi}/bloquer",
                           headers=_h(jeton)).status_code == 400

    def test_la_liste_des_blocages_permet_de_revenir_en_arriere(
            self, client, db, jeton, inscrire):
        id_bob, _ = _bob(client, db, inscrire)
        client.post(f"/utilisateurs/{id_bob}/bloquer", headers=_h(jeton))

        liste = client.get("/utilisateurs/moi/blocages", headers=_h(jeton)).json()
        assert [u["pseudo"] for u in liste] == ["bob"]


class TestSignalement:
    def test_signaler_un_avis_le_masque_aussitot(self, client, db, jeton, inscrire):
        id_bob, jeton_bob = _bob(client, db, inscrire)
        client.post(f"/utilisateurs/{id_bob}/abonner", headers=_h(jeton))
        id_serie = client.post(f"/series/{REF_SERIE}/suivre",
                               headers=_h(jeton)).json()["id_serie"]
        avis = client.post("/avis", headers=_h(jeton_bob),
                           json={"id_serie": id_serie, "note": 2,
                                 "commentaire": "propos déplacés"}).json()

        reponse = client.post("/signalements", headers=_h(jeton),
                              json={"id_avis": avis["id_avis"], "motif": "haine"})
        assert reponse.status_code == 201
        assert reponse.json()["statut"] == "nouveau"

        # promesse tenue sans attendre d'arbitrage : il ne le reverra plus
        assert client.get("/avis/abonnements", headers=_h(jeton),
                          params={"id_serie": id_serie}).json() == []

    def test_l_editeur_est_prevenu(self, client, db, jeton, inscrire, envoyeur):
        id_bob, _ = _bob(client, db, inscrire)
        envoyeur.messages.clear()

        client.post("/signalements", headers=_h(jeton),
                    json={"id_vise": id_bob, "motif": "harcelement",
                          "precision": "messages répétés"})

        assert len(envoyeur.messages) == 1
        assert "harcelement" in envoyeur.messages[0][1]

    def test_une_cible_exactement(self, client, db, jeton, inscrire):
        id_bob, _ = _bob(client, db, inscrire)
        for corps in ({"motif": "spam"},
                      {"id_avis": 1, "id_vise": id_bob, "motif": "spam"}):
            assert client.post("/signalements", headers=_h(jeton),
                               json=corps).status_code == 422

    def test_on_ne_signale_pas_son_propre_contenu(self, client, db, jeton):
        id_moi = _id(db, "celian")
        assert client.post("/signalements", headers=_h(jeton),
                           json={"id_vise": id_moi, "motif": "spam"}).status_code == 400

    def test_motif_hors_liste_refuse(self, client, db, jeton, inscrire):
        id_bob, _ = _bob(client, db, inscrire)
        assert client.post("/signalements", headers=_h(jeton),
                           json={"id_vise": id_bob,
                                 "motif": "je n'aime pas"}).status_code == 422

    def test_signaler_exige_une_authentification(self, client):
        assert client.post("/signalements",
                           json={"id_vise": 1, "motif": "spam"}).status_code == 401


class TestFiltreLexical:
    def _serie(self, client, jeton):
        return client.post(f"/series/{REF_SERIE}/suivre",
                           headers=_h(jeton)).json()["id_serie"]

    def test_un_commentaire_injurieux_est_refuse(self, client, jeton):
        reponse = client.post("/avis", headers=_h(jeton),
                              json={"id_serie": self._serie(client, jeton),
                                    "note": 1, "commentaire": "quel c0nnard"})
        assert reponse.status_code == 422
        assert "n'acceptons pas" in reponse.json()["detail"]

    def test_un_commentaire_ordinaire_passe(self, client, jeton):
        # le filtre ne doit pas gêner l'usage normal, sans quoi il fera plus de
        # mal que de bien : « en retard » est écarté de la liste pour cette raison
        avis = client.post("/avis", headers=_h(jeton),
                           json={"id_serie": self._serie(client, jeton),
                                 "note": 8, "commentaire": "Correct"}).json()

        for texte in ("Un très bon épisode", "La saison sort en retard",
                      "Le méchant est détestable", "Une fin ratée, quel gâchis"):
            reponse = client.patch(f"/avis/{avis['id_avis']}", headers=_h(jeton),
                                   json={"commentaire": texte})
            assert reponse.status_code == 200, texte

    def test_la_modification_est_filtree_aussi(self, client, jeton):
        # sinon il suffirait de publier proprement puis d'éditer
        avis = client.post("/avis", headers=_h(jeton),
                           json={"id_serie": self._serie(client, jeton),
                                 "note": 8, "commentaire": "Correct"}).json()

        reponse = client.patch(f"/avis/{avis['id_avis']}", headers=_h(jeton),
                               json={"commentaire": "quel c0nnard"})
        assert reponse.status_code == 422
