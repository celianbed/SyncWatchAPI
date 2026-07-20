# tests/test_sante.py


def test_racine(client):
    reponse = client.get("/")
    assert reponse.status_code == 200
    assert reponse.json()["documentation"] == "/docs"


def test_health(client):
    reponse = client.get("/health")
    assert reponse.status_code == 200
    assert reponse.json() == {"statut": "ok", "base_de_donnees": "accessible"}
