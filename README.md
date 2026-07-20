# SyncWatch API

API du projet SyncWatch (suivi de séries et de films : recherche via TMDB,
suivi, marquage des épisodes vus, prochain épisode à regarder, avis,
statistiques et notifications de diffusion).

L'application mobile (Flutter) qui consomme cette API vit dans un dépôt
séparé, `SyncWatchApp`.

- `api/` — l'API (FastAPI)

## Stack

FastAPI · SQLAlchemy 2 · PostgreSQL (Neon en prod) · Alembic · APScheduler ·
JWT (python-jose) · bcrypt · httpx (client TMDB) — déployé sur Render.

## Lancer en local

```bash
cd api
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
# créer api/.env : DATABASE_URL, SECRET_KEY, TMDB_API_TOKEN
.venv/bin/alembic upgrade head
cd ..
api/.venv/bin/uvicorn api.main:app --reload
```

Documentation interactive : http://127.0.0.1:8000/docs

## Tests

Les tests tournent sur une base Postgres dédiée (`sync_watch_test`, créée
automatiquement), chaque test dans une transaction annulée. Les appels TMDB
sont doublés — aucun accès réseau.

```bash
cd api && .venv/bin/python -m pytest tests
```

## Déploiement

`render.yaml` décrit le service (blueprint Render). Variables à fournir :
`DATABASE_URL` (Neon, avec `?sslmode=require`) et `TMDB_API_TOKEN`.
Le pipeline quotidien de notifications (`POST /taches/scan-diffusions`,
header `X-Cron-Secret`) est déclenché par un cron externe car le plan
gratuit Render endort le service.
