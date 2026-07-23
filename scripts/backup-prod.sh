#!/usr/bin/env bash
# Sauvegarde horodatée de la base de PROD (Neon) dans backups/.
# Lecture seule sur la prod (pg_dump). À lancer à la main ou via cron.
#
# Neon est en Postgres 18 ; pg_dump local (16) refuserait → on passe par une
# image jetable postgres:18 (réseau seulement), comme le script de sync.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env.prod ] || { echo "Erreur : .env.prod introuvable." >&2; exit 1; }
URL_PROD="$(grep -m1 '^DATABASE_URL=' .env.prod | cut -d= -f2-)"

mkdir -p backups
HORODATAGE="$(date +%Y%m%d-%H%M%S)"
FICHIER="backups/syncwatch-prod-$HORODATAGE.sql"

echo "Sauvegarde de la prod → $FICHIER"
# --no-owner/--no-privileges : réimportable partout. PAS de --clean (aucun DROP dans le dump).
container run --rm postgres:18-alpine \
  pg_dump "$URL_PROD" --no-owner --no-privileges > "$FICHIER"

TAILLE="$(du -h "$FICHIER" | cut -f1)"
echo "OK — $FICHIER ($TAILLE)"
echo "Pour restaurer EN LOCAL : container exec -i postgres psql \"\$URL_LOCALE\" < $FICHIER"
