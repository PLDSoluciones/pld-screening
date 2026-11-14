#!/usr/bin/env bash
# Prepara un servidor Ubuntu 22.04/24.04 limpio: Docker, firewall y respaldos diarios.
# Uso (como root):  bash deploy/instalar_servidor.sh
set -euo pipefail
apt-get update -y && apt-get install -y ca-certificates curl git ufw
if ! command -v docker >/dev/null; then curl -fsSL https://get.docker.com | sh; fi
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
chmod +x "$APP_DIR/deploy/respaldo.sh"
( crontab -l 2>/dev/null | grep -v respaldo.sh; echo "30 2 * * * $APP_DIR/deploy/respaldo.sh >> /var/log/pld-respaldo.log 2>&1" ) | crontab -
echo "Listo. Siguiente: cp .env.example .env && nano .env (ponga DOMAIN=su.dominio.mx) y luego:"
echo "  docker compose -f docker-compose.prod.yml up -d --build"
