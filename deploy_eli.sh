#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# EIL Production VPS Deployment Script
# Single-node Docker Compose stack, direct ports, no reverse proxy, no Keycloak.
# Authentication: demo/dev login (APP_ENV=demo + AUTH_MODE=dev).
###############################################################################

# ---------- Prerequisites ----------
echo "=== Installing Docker & Compose ==="
apt-get update && apt-get upgrade -y
apt-get install -y ca-certificates curl gnupg git ufw fail2ban
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \$(. /etc/os-release && echo \$VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker \$USER

echo "=== Enabling firewall (only ports 18080/18000) ==="
ufw default deny incoming
ufw allow OpenSSH
ufw allow 18080/tcp
ufw allow 18000/tcp
ufw enable

# ---------- Repository ----------
echo "=== Cloning repository ==="
mkdir -p /opt/eli
git clone <your-repo-url> /opt/eli
cd /opt/eli

# ---------- Environment ----------
echo "=== Configuring .env.prod ==="
cp .env.prod.example .env.prod
chmod 600 .env.prod
nano .env.prod   # fill in: EIL_HOST, POSTGRES_PASSWORD, DEV_JWT_SECRET, GRAFANA_ADMIN_PASSWORD

# ---------- Deploy ----------
echo "=== Starting the stack ==="
docker compose -f infra/compose/docker-compose.prod.yml --env-file .env.prod up -d --build

# ---------- Wait for health ----------
echo "=== Waiting for services ==="
docker compose -f infra/compose/docker-compose.prod.yml --env-file .env.prod ps

# ---------- Seed reference data ----------
echo "=== Seeding reference data ==="
docker compose -f infra/compose/docker-compose.prod.yml --env-file .env.prod \
  exec api python scripts/seed_reference.py

# ---------- Optional extras (MinIO/Mailpit) ----------
echo "=== Starting optional extras ==="
docker compose -f infra/compose/docker-compose.prod.yml --env-file .env.prod \
  --profile extras up -d

# ---------- Verify ----------
echo "=== Verification ==="
curl -fsS http://\${EIL_HOST}:18000/healthz
curl -fsS http://\${EIL_HOST}:18000/readyz
curl -I http://\${EIL_HOST}:18080/

echo ""
echo "=== Done! ==="
echo "Web UI:      http://\${EIL_HOST}:\${EIL_WEB_PORT:-18080}"
echo "API docs:    http://\${EIL_HOST}:\${EIL_API_PORT:-18000}/docs"
echo "Grafana (SSH tunnel): ssh -L 18030:127.0.0.1:18030 \${EIL_HOST}"
echo "Backup:      ./scripts/backup.sh"