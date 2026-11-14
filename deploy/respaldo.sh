#!/usr/bin/env bash
# Respaldo diario consistente de la base (conserva los últimos 30). Copie /var/lib/pld-backups FUERA del servidor.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p /var/lib/pld-backups
docker compose -f docker-compose.prod.yml exec -T api python -m pldscreen backup --dir /data/backups --keep 30
CID=$(docker compose -f docker-compose.prod.yml ps -q api)
docker cp "$CID":/data/backups/. /var/lib/pld-backups/
echo "$(date -Is) respaldo ok"
