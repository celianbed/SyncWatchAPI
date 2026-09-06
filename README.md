# SyncWatch API

API du projet SyncWatch (suivi de séries et de films : recherche via TMDB,
suivi, marquage des épisodes vus, prochain épisode à regarder, avis,
statistiques et notifications de diffusion).

L'application mobile (Flutter) qui consomme cette API vit dans un dépôt
séparé, `SyncWatchApp`.

- `api/` — les routes FastAPI
- `core/`, `db/`, `models/`, `schemas/`, `services/` — configuration, accès
  base de données, modèles SQLAlchemy, schémas Pydantic, logique métier

## Stack

FastAPI · SQLAlchemy 2 · PostgreSQL (Neon en prod) · Alembic · APScheduler ·
JWT (python-jose) · bcrypt · httpx (client TMDB) — déployé sur Render.

## Lancer en local

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
# créer .env : DATABASE_URL, SECRET_KEY, TMDB_API_TOKEN
.venv/bin/alembic upgrade head
.venv/bin/uvicorn main:app --reload
```

Documentation interactive : http://127.0.0.1:8000/docs

## Connexion externe et notifications

Connexion Google (`POST /auth/google`) et Apple (`POST /auth/apple`) : le jeton
d'identité fourni par l'app est vérifié côté API, puis lié au compte de la même
adresse mail s'il existe. Apple n'envoie l'adresse qu'à la toute première
autorisation : c'est le claim `sub`, stocké dans `utilisateur.sub_apple`, qui
identifie le compte aux connexions suivantes.

Variables associées :

| Variable | Rôle |
| --- | --- |
| `GOOGLE_CLIENT_ID` | client OAuth « Web » (audience du `id_token` Google) |
| `APPLE_BUNDLE_ID` | identifiant du bundle iOS (audience du jeton Apple) |
| `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` | clé Sign in with Apple, pour révoquer l'accès quand un compte est supprimé |
| `FIREBASE_CREDENTIALS_JSON` | compte de service Firebase (push FCM → Android et APNs) |

Vides, ces variables ne cassent rien : la connexion concernée répond 503 et les
push sont seulement journalisés.

`DELETE /utilisateurs/moi` supprime définitivement le compte et tout ce qui s'y
rattache (exigence App Store 5.1.1 v) ; l'accès Apple est révoqué au passage.

## Tests

Les tests tournent sur une base Postgres dédiée (`sync_watch_test`, créée
automatiquement), chaque test dans une transaction annulée. Les appels TMDB
sont doublés — aucun accès réseau.

```bash
.venv/bin/python -m pytest tests
```

Postgres en conteneur (outil `container` d'Apple, macOS 26+), si tu n'en as pas
en local — le mot de passe doit être celui de `DATABASE_URL` dans `.env` :

```bash
container system start
container run -d --name syncwatch-postgres \
    -e POSTGRES_PASSWORD=<mot de passe du .env> -p 5432:5432 postgres:17
```

La base `sync_watch_test` est créée toute seule au premier test. La base de
développement `sync_watch`, elle, ne l'est pas : voir la synchronisation depuis
la prod plus bas.

## Synchroniser la base locale depuis la prod

```bash
# créer .env.prod (jamais committé) : DATABASE_URL=<url Neon>
./scripts/sync-db-depuis-prod.sh
```

Écrase le contenu de la base locale avec un dump de la base de prod (Neon).
À lancer à la demande — jamais automatique.

## Déploiement

Le service tourne sur Render. `render.yaml` sert de référence pour la
commande de démarrage et les variables attendues ; **les valeurs font foi
dans le tableau de bord Render**, à renseigner là.

Variables : `DATABASE_URL` (Neon, avec `?sslmode=require`), `TMDB_API_TOKEN`,
`SECRET_KEY`, `CRON_SECRET`, `FIREBASE_CREDENTIALS_JSON`, et
`NOTIFICATIONS_PLANIFIEES=false` (voir ci-dessous).

### Tâches cron externes

Elles ne sont pas gérées par Render : **sans elles, aucune notification de
diffusion ne part**. Deux tâches, sur cron-job.org ou équivalent.

| Tâche | Appel | Fréquence |
|---|---|---|
| Maintien en éveil | `GET /health` | toutes les 10 min |
| Scan des diffusions | `POST /taches/scan-diffusions`, en-tête `X-Cron-Secret` | une fois par jour |

Le maintien en éveil n'est pas un confort : le plan gratuit endort le service
après 15 min d'inactivité et le réveil prend près d'une minute (mesuré à
56,7 s), au-delà du délai maximal de cron-job.org — la tâche de scan
échouerait donc systématiquement. Effet de bord bienvenu : `/health` fait un
`SELECT 1`, ce qui garde aussi le compute Neon éveillé et supprime l'attente
au premier lancement de l'app. Coût : environ 730 h/mois sur les 750 h
offertes, donc plus de place pour un second service gratuit.

La valeur de `X-Cron-Secret` est celle de `CRON_SECRET` **dans le tableau de
bord Render** — elle y est générée, et n'est écrite nulle part dans le dépôt.

### Pourquoi pas le planificateur interne

APScheduler est présent dans `main.py` mais doit rester désactivé
(`NOTIFICATIONS_PLANIFIEES=false`). Il vit dans le processus : un
redéploiement à l'heure du job fait perdre la journée, sans rattrapage. Et
surtout, `job_quotidien` ne resynchronise pas le cache TMDB, contrairement à
`POST /taches/scan-diffusions` — le scan tournerait alors sur un cache qui
n'apprend jamais les nouveaux épisodes, et ne créerait aucune notification
sans lever la moindre erreur.
