# VPS deployment — direct ports, no reverse proxy

Single Ubuntu VPS deployment of the EIL Docker Compose stack using unique host
ports. There is **no Caddy, no external nginx, and no Keycloak** in this setup.
The web container's internal nginx only serves the static SPA.

Authentication is the demo/dev login (`APP_ENV=demo`, `AUTH_MODE=dev`).

> **Demo only.** Anyone who can reach the app can choose a role, including
> `admin`. HTTP also sends JWT tokens in cleartext. Restrict the public ports to
> trusted IPs or use a VPN. Do not put real data behind this setup.

## Port map

| Service | Host binding | Container | Public |
| --- | --- | --- | --- |
| Web SPA | `0.0.0.0:18080` | `80` | Yes |
| API | `0.0.0.0:18000` | `8000` | Yes |
| Postgres | none | `5432` | No |
| Redis | none | `6379` | No |
| MinIO API | `127.0.0.1:18010` | `9000` | No |
| MinIO console | `127.0.0.1:18011` | `9001` | No |
| Mailpit | `127.0.0.1:18025` | `8025` | No |
| OTel gRPC/HTTP | none | `4317/4318` | No |
| Prometheus | `127.0.0.1:18090` | `9090` | No |
| Grafana | `127.0.0.1:18030` | `3000` | No |

Only `18080` and `18000` are published on all interfaces. Everything else is
internal to the Compose network or bound to loopback.

## Prerequisites

- Ubuntu 22.04 or 24.04 VPS with a public IP.
- 2 vCPU / 4 GB RAM minimum; 8 GB recommended for the full monitoring stack.
- 40 GB disk, plus 2–4 GB swap on smaller instances.
- Docker Engine and the Docker Compose plugin.
- The VPS provider's firewall must allow the chosen ports.

## Server preparation

```bash
adduser deploy
usermod -aG sudo deploy
# copy your SSH public key to deploy, then disable password authentication

apt update && apt upgrade -y
apt install -y ca-certificates curl gnupg git ufw fail2ban

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker deploy

# Example firewall: SSH plus the two public app ports.
ufw default deny incoming
ufw allow OpenSSH
ufw allow 18080/tcp
ufw allow 18000/tcp
ufw enable
```

If the app should only be reachable from your own network, replace the two
`ufw allow` rules with source-restricted rules:

```bash
ufw allow from <YOUR_IP> to any port 18080 proto tcp
ufw allow from <YOUR_IP> to any port 18000 proto tcp
```

Also add the same ports to the provider firewall/security group. Docker
publishes ports outside UFW, so the provider firewall is an additional layer.

## Configure

```bash
sudo mkdir -p /opt/eli
sudo chown deploy:deploy /opt/eli
git clone <repo-url> /opt/eli
cd /opt/eli

cp .env.prod.example .env.prod
chmod 600 .env.prod
nano .env.prod
```

Required values:

- `EIL_HOST` — the VPS public IP or hostname, without `http://`.
- `POSTGRES_PASSWORD` — strong and URL-safe (no `@`, `:`, `/`, `#`, spaces).
- `DEV_JWT_SECRET` — long random string, at least 32 characters.
- `GRAFANA_ADMIN_PASSWORD` — strong password.

Optional values:

- `EIL_WEB_PORT` / `EIL_API_PORT` — change if 18080/18000 are taken.
- `AI_ENABLED=true` and `GROQ_API_KEY` — live AI; otherwise replay/off.
- `MINIO_ROOT_PASSWORD` — only needed with the `extras` profile.

Validate the rendered configuration:

```bash
docker compose -f infra/compose/docker-compose.prod.yml --env-file .env.prod config >/dev/null
```

## Deploy

```bash
docker compose -f infra/compose/docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f infra/compose/docker-compose.prod.yml --env-file .env.prod ps
docker compose -f infra/compose/docker-compose.prod.yml --env-file .env.prod logs -f api web
```

Migrations run automatically because the API service sets `RUN_MIGRATIONS=1`.
Seed the reference data once, after the API is healthy:

```bash
docker compose -f infra/compose/docker-compose.prod.yml --env-file .env.prod \
  exec api python scripts/seed_reference.py
```

Start the optional MinIO/Mailpit services only if needed:

```bash
docker compose -f infra/compose/docker-compose.prod.yml --env-file .env.prod \
  --profile extras up -d
```

## Verify

```bash
curl -fsS http://<VPS_IP>:18000/healthz
curl -fsS http://<VPS_IP>:18000/readyz
curl -I http://<VPS_IP>:18080/
```

In a browser:

1. Open `http://<VPS_IP>:18080`.
2. Choose a role on the dev login screen and sign in.
3. Check the dashboard, approvals, audit, and one AI/replay screen.
4. API docs are at `http://<VPS_IP>:18000/docs` (enabled by `APP_ENV=demo`).
5. Grafana is reachable only through a tunnel:

   ```bash
   ssh -L 18030:127.0.0.1:18030 deploy@<VPS_IP>
   ```

   Then open `http://localhost:18030`.

## Operations

### Backups

```bash
./scripts/backup.sh
```

The script writes a PostgreSQL custom-format dump and an archive of the
`api_objects` volume into `backups/`. Schedule it with cron and copy the files
offsite. Keep `.env.prod` in a password manager or secret store; the script does
not copy secrets.

Example cron entry:

```cron
15 2 * * * cd /opt/eli && BACKUP_DIR=/opt/eli/backups ./scripts/backup.sh >>/var/log/eli-backup.log 2>&1
```

### Updates

```bash
cd /opt/eli
./scripts/backup.sh
git pull
docker compose -f infra/compose/docker-compose.prod.yml --env-file .env.prod up -d --build
```

Migrations apply automatically. Rebuild the web image whenever `EIL_HOST` or
`EIL_API_PORT` changes, because Vite embeds the API URL at build time.

### Logs and status

```bash
docker compose -f infra/compose/docker-compose.prod.yml --env-file .env.prod ps
docker compose -f infra/compose/docker-compose.prod.yml --env-file .env.prod logs -f --tail=200
```

### Trimming the stack

To reduce memory on a small VPS:

- Remove or stop `prometheus` and `grafana`.
- Set `OTEL_ENABLED=false` and remove `otel-collector` if tracing is not needed.
- Leave MinIO/Mailpit on the `extras` profile; they are not started by default.
- Keep the API, worker, beat, web, Postgres, and Redis.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `docker compose config` fails | Missing required variables in `.env.prod` (`EIL_HOST`, `POSTGRES_PASSWORD`, `DEV_JWT_SECRET`, `GRAFANA_ADMIN_PASSWORD`) |
| API container unhealthy | `docker compose logs api`; verify `TRUSTED_HOSTS` includes `127.0.0.1` and `api`; verify Postgres is healthy |
| Web loads but API calls fail | `VITE_API_BASE_URL` must be `http://<VPS_IP>:<API_PORT>`; CORS must contain `http://<VPS_IP>:<WEB_PORT>`; port 18000 must be reachable |
| Login page has no roles | `APP_ENV` must be `demo` and `AUTH_MODE=dev`; check `GET /api/v1/auth/config` |
| Port already in use | Change `EIL_WEB_PORT` / `EIL_API_PORT` in `.env.prod` and rebuild the web image |
| Seed fails | Run it only after migrations; check the API logs first |
| Grafana unreachable | It is bound to `127.0.0.1`; use the SSH tunnel |

## Keycloak later

Keycloak is intentionally not part of this deployment. If OIDC is added later,
note that OIDC browser login over plain HTTP on a public IP fails in modern
browsers because `oidc-client-ts` uses `crypto.subtle` for PKCE, which requires
a secure context. Use HTTPS, or explicitly add `disablePKCE` to the web OIDC
configuration and accept the security downgrade.
