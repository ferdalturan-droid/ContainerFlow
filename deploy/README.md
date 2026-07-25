# ContainerFlow — Production Deployment Guide

This folder contains everything you need to put ContainerFlow on a real VPS
behind a domain with HTTPS.

```
deploy/
├── nginx/
│   ├── containerflow.conf       ← plain HTTP reverse proxy
│   └── containerflow-ssl.conf   ← HTTPS + HSTS (Let's Encrypt-ready)
├── install_vps.sh               ← one-shot Ubuntu/Debian provisioning script
└── README.md                    ← this file
```

The application itself does NOT need to change to be deployed — it already:

* serves the API on `127.0.0.1:8001` (supervisor-managed in dev)
* serves the React frontend on `127.0.0.1:3000`
* uses `MONGO_URL` from `backend/.env` (works for local Mongo, Mongo Atlas, etc.)

So a production VPS just needs MongoDB + nginx + (optionally) Let's Encrypt.

---

## 1. One-shot VPS installation (Ubuntu 22.04+)

```bash
# 1) SSH into your fresh server as root
# 2) git clone ContainerFlow into /app (or rsync your build)
git clone <your-repo> /app
cd /app

# 3) Run the installer (installs python, node, yarn, mongo, nginx, supervisor)
sudo bash deploy/install_vps.sh

# 4) Edit environment files
$EDITOR /app/backend/.env       # MONGO_URL, JWT_SECRET, SUPER_ADMIN_PASSWORD
$EDITOR /app/frontend/.env      # REACT_APP_BACKEND_URL=https://your-domain.example.com

# 5) Reload services
sudo supervisorctl reread && sudo supervisorctl update
sudo supervisorctl restart backend frontend
```

## 2. Point your domain

Create an A-record from `your-domain.example.com` → server IP. Wait for DNS
to propagate (usually ≤ 5 min).

## 3. Plain-HTTP reverse proxy (test that nginx works)

```bash
sudo cp deploy/nginx/containerflow.conf /etc/nginx/sites-available/containerflow
sudo sed -i 's/your-domain.example.com/REAL_DOMAIN/g' /etc/nginx/sites-available/containerflow
sudo ln -sf /etc/nginx/sites-available/containerflow /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Visit `http://your-domain.example.com` — you should see the login page.

## 4. Enable HTTPS with Let's Encrypt

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.example.com
# certbot will obtain & install a free cert, then auto-renew via systemd timer
```

Or, if you prefer to use the pre-baked SSL config instead of certbot's rewrite:

```bash
sudo certbot certonly --nginx -d your-domain.example.com
sudo cp deploy/nginx/containerflow-ssl.conf /etc/nginx/sites-available/containerflow
sudo sed -i 's/your-domain.example.com/REAL_DOMAIN/g' /etc/nginx/sites-available/containerflow
sudo nginx -t && sudo systemctl reload nginx
```

Verify renewal:

```bash
sudo certbot renew --dry-run
sudo systemctl status certbot.timer
```

## 5. Backups

Backup scripts live in `/app/scripts/`. Install the daily cron job:

```bash
sudo bash /app/scripts/setup_backup_cron.sh
```

This installs the equivalent of:

```cron
# containerflow-mongo-backup
0 3 * * * /app/scripts/backup_mongo.sh >> /var/log/cf-backup.log 2>&1
```

Backups are stored under `/app/backups/YYYY-MM-DD/` as gzip-compressed Mongo
archives. The most recent backup is symlinked to `/app/backups/latest.archive.gz`.

Restore example:

```bash
sudo bash /app/scripts/restore_mongo.sh /app/backups/latest.archive.gz
# or replace existing data:
sudo bash /app/scripts/restore_mongo.sh /app/backups/latest.archive.gz --drop
```

Customise via env vars:

```bash
BACKUP_DIR=/var/backups/containerflow RETENTION_DAYS=14 \
  /app/scripts/backup_mongo.sh
```

## 6. Health checks

* Backend API: `curl https://your-domain.example.com/api/`
* Nginx itself: `curl https://your-domain.example.com/nginx-health`
* Mongo: `mongosh "$MONGO_URL/$DB_NAME" --eval 'db.runCommand({ping:1})'`

## 7. Optional hardening

* Firewall: `ufw allow 22,80,443/tcp && ufw enable`
* Mongo bind only to `127.0.0.1` (already default on most distros)
* Set strong `JWT_SECRET` and `SUPER_ADMIN_PASSWORD` in `/app/backend/.env`
* Rotate Super Admin password right after first login

---

For multi-region / load-balanced deployments, point a load balancer at the
HTTP/HTTPS port and let MongoDB run on a managed cluster (Atlas) — the app
config stays identical: just update `MONGO_URL` in `backend/.env`.
