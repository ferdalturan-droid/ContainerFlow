#!/usr/bin/env bash
# ContainerFlow — one-shot VPS provisioning (Ubuntu 22.04+ / Debian 12+)
# Installs: Python 3.11, Node + Yarn, MongoDB 7, nginx, supervisor.
# Does NOT touch /app or .env files — that's a separate step.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo bash $0)"
  exit 1
fi

echo ">>> Updating apt"
apt-get update -y
apt-get install -y curl ca-certificates gnupg lsb-release software-properties-common ufw

echo ">>> Installing Python 3.11"
add-apt-repository -y ppa:deadsnakes/ppa || true
apt-get install -y python3.11 python3.11-venv python3-pip

echo ">>> Installing Node 20 + Yarn"
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs
npm install -g yarn

echo ">>> Installing MongoDB 7"
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
echo "deb [signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" \
  > /etc/apt/sources.list.d/mongodb-org-7.0.list
apt-get update -y
apt-get install -y mongodb-org mongodb-org-tools
systemctl enable --now mongod

echo ">>> Installing nginx + supervisor + certbot"
apt-get install -y nginx supervisor certbot python3-certbot-nginx
systemctl enable --now nginx supervisor

echo ">>> Setting up supervisor program files (you can customise these)"
cat > /etc/supervisor/conf.d/containerflow-backend.conf <<'EOF'
[program:backend]
command=/usr/bin/python3.11 -m uvicorn server:app --host 0.0.0.0 --port 8001
directory=/app/backend
autostart=true
autorestart=true
environment=PYTHONUNBUFFERED="1"
stdout_logfile=/var/log/supervisor/backend.out.log
stderr_logfile=/var/log/supervisor/backend.err.log
EOF

cat > /etc/supervisor/conf.d/containerflow-frontend.conf <<'EOF'
[program:frontend]
command=/usr/bin/yarn start
directory=/app/frontend
autostart=true
autorestart=true
environment=PORT="3000",HOST="127.0.0.1",BROWSER="none"
stdout_logfile=/var/log/supervisor/frontend.out.log
stderr_logfile=/var/log/supervisor/frontend.err.log
EOF

echo ">>> Configuring UFW firewall"
ufw allow OpenSSH || true
ufw allow 'Nginx Full' || true
ufw --force enable || true

echo
echo "VPS base ready. Next steps:"
echo "  1) cd /app && pip3 install -r backend/requirements.txt"
echo "  2) cd /app/frontend && yarn install"
echo "  3) Edit /app/backend/.env (MONGO_URL, JWT_SECRET, SUPER_ADMIN_PASSWORD)"
echo "  4) Edit /app/frontend/.env (REACT_APP_BACKEND_URL=https://your-domain)"
echo "  5) supervisorctl reread && supervisorctl update && supervisorctl restart all"
echo "  6) cp deploy/nginx/containerflow.conf /etc/nginx/sites-available/containerflow"
echo "     (see deploy/README.md for the full nginx + HTTPS guide)"
echo "  7) bash /app/scripts/setup_backup_cron.sh"
