# Image de l'API SyncWatch.
# Version de Python figée à l'identique de la production (cf. render.yaml) : c'est
# tout l'intérêt du conteneur, reconstituer localement l'environnement de prod.
FROM python:3.12.11-slim

# PYTHONDONTWRITEBYTECODE : pas de .pyc dans le conteneur (inutiles, et gênants
# avec un volume monté). PYTHONUNBUFFERED : les logs sortent en direct, pas par blocs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Utilisateur non-root : si l'application est compromise, l'attaquant n'a pas les
# droits root sur le système de fichiers du conteneur.
RUN useradd --create-home --uid 1000 syncwatch

WORKDIR /app

# Les dépendances dans leur propre couche, AVANT le code : tant que requirements.txt
# ne change pas, Docker réutilise le cache et un rebuild ne prend que quelques secondes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=syncwatch:syncwatch . .

USER syncwatch

EXPOSE 8000

# Commande de production. docker-compose.yml la remplace en développement
# (migrations au démarrage + rechargement à chaud).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
