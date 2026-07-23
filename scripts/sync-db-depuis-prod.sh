#!/usr/bin/env bash
# Écrase le contenu de la base locale (container "postgres") avec un dump
# de la base de prod (Neon). À lancer à la demande, jamais automatiquement.
#
# Prérequis : api/.env.prod avec DATABASE_URL=<url Neon>, jamais committé.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env.prod ]; then
  echo "Erreur : .env.prod introuvable (doit contenir DATABASE_URL=<url Neon>)." >&2
  exit 1
fi

# extraction sans passer par "source" : les URLs Neon contiennent des "&"
# que le shell interpréterait comme opérateur de tâche de fond
lire_url() { grep -m1 '^DATABASE_URL=' "$1" | cut -d= -f2-; }
URL_PROD="$(lire_url .env.prod)"
URL_LOCAL="$(lire_url .env)"

# GARDE-FOU : ce script ÉCRIT dans URL_LOCAL (restauration --clean = DROP puis recréation).
# On refuse catégoriquement si la cible ressemble à une base distante / de prod : c'est
# exactement ce qui a détruit la prod une fois (restauration pointée sur Neon par erreur).
if echo "$URL_LOCAL" | grep -qiE "neon\.tech|render\.com|amazonaws|\.cloud"; then
  echo "STOP : la CIBLE (URL_LOCAL) ressemble à une base distante/prod." >&2
  echo "       Ce script ne restaure QUE dans une base locale. Abandon." >&2
  exit 1
fi

masquer() { echo "$1" | sed -E 's#(://[^:/@]+:)[^@]+(@)#\1***\2#'; }

echo "Source (prod)  : $(masquer "$URL_PROD")"
echo "Cible  (local) : $(masquer "$URL_LOCAL")"
echo "Cette opération écrase entièrement le contenu de la base locale."
read -r -p "Continuer ? [y/N] " confirmation
if [[ ! "$confirmation" =~ ^[yY]$ ]]; then
  echo "Annulé."
  exit 1
fi

# Neon tourne en Postgres 18 ; le container local "postgres" est en 16, et
# pg_dump refuse de dumper un serveur plus récent que lui. On dump donc via
# une image jetable postgres:18 (réseau seulement, aucune donnée persistée),
# puis on restaure dans le container local existant.
DUMP="$(mktemp)"
trap 'rm -f "$DUMP"' EXIT

echo "Dump de la base de prod…"
container run --rm postgres:18-alpine \
  pg_dump "$URL_PROD" --no-owner --no-privileges --clean --if-exists > "$DUMP"

echo "Restauration en local…"
container exec -i postgres psql "$URL_LOCAL" --quiet < "$DUMP"

echo "Sync terminée."
