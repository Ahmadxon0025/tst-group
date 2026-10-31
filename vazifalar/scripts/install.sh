#!/usr/bin/env bash
# TST Vazifalar — one-time server install (Ubuntu 24.04, run as root).
#   curl -fsSL https://raw.githubusercontent.com/Ahmadxon0025/tst-group/main/vazifalar/scripts/install.sh -o install.sh
#   bash install.sh
# It asks on the screen (never send these through chat):
#   1) the list of people (people.json) — pasted once
#   2) the Telegram bot token and bot username from @BotFather
# It installs: PostgreSQL, Python venv, gunicorn (web), the bot service, Caddy (HTTPS), daily backups, firewall.
set -euo pipefail

REPO="${REPO:-https://github.com/Ahmadxon0025/tst-group.git}"
ROOT=/opt/tst-group
APP=$ROOT/vazifalar
IP="$(curl -fsS4 https://api.ipify.org || hostname -I | awk '{print $1}')"
DOMAIN="${DOMAIN:-$(echo "$IP" | tr . -).sslip.io}"

say() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }

say "1/9 Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3-venv python3-pip postgresql git curl caddy ufw cron
timedatectl set-timezone Asia/Tashkent || true

say "Swap (safety buffer for a 1 GB server)"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap -q /swapfile && swapon /swapfile
  grep -q /swapfile /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -q vm.swappiness=20; echo 'vm.swappiness=20' > /etc/sysctl.d/99-tst.conf
fi

say "2/9 App user"
id tst >/dev/null 2>&1 || useradd --system --create-home --home-dir /home/tst --shell /bin/bash tst

say "3/9 Code"
if [ -d "$ROOT/.git" ]; then sudo -u tst git -C "$ROOT" pull -q --ff-only; else
  mkdir -p "$ROOT" && chown tst:tst "$ROOT" && sudo -u tst git clone -q "$REPO" "$ROOT"; fi

say "4/9 People (people.json — stays on this server only)"
if [ ! -f "$APP/people.json" ]; then
  echo "Paste the people list (the JSON block from the chat), then press Enter and Ctrl+D:"
  TMP="$(mktemp)"; cat > "$TMP"
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert isinstance(d,list) and d; [p['username'] and p['name'] and p['role'] for p in d]; print(len(d),'people OK')" "$TMP" \
    || { echo "That is not valid — run the script again."; rm -f "$TMP"; exit 1; }
  install -o tst -g tst -m 600 "$TMP" "$APP/people.json"; rm -f "$TMP"
fi

say "5/9 Database"
DBPASS="$(openssl rand -hex 24)"
if ! sudo -u postgres psql -tAc "select 1 from pg_roles where rolname='tst'" | grep -q 1; then
  sudo -u postgres psql -q -c "create role tst login password '$DBPASS'"
  sudo -u postgres psql -q -c "create database tst_vazifalar owner tst"
  NEWDB=1
else
  NEWDB=0
fi

say "6/9 Settings (.env)"
if [ ! -f "$APP/.env" ]; then
  [ "$NEWDB" = 1 ] || { echo "Database exists but .env is missing — restore .env from backup first."; exit 1; }
  echo "Paste the bot token from @BotFather (it will not show on screen), then Enter:"
  read -rs BOT_TOKEN; echo
  read -rp "Bot username (without @, e.g. tst_vazifa_bot): " BOT_USER
  umask 077
  cat > "$APP/.env" <<ENV
DJANGO_SECRET_KEY=$(openssl rand -hex 32)
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=$DOMAIN
DATABASE_URL=postgres://tst:$DBPASS@127.0.0.1:5432/tst_vazifalar
TST_BOT_TOKEN=$BOT_TOKEN
TST_BOT_USERNAME=$BOT_USER
ENV
  chown tst:tst "$APP/.env"; chmod 600 "$APP/.env"
fi

say "7/9 Python, tests, database tables"
sudo -u tst python3 -m venv "$APP/.venv"
sudo -u tst "$APP/.venv/bin/pip" install -q --upgrade pip
sudo -u tst "$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"
( cd "$APP" && sudo -u tst .venv/bin/python -m pytest -q ) || { echo "Tests failed — stopping."; exit 1; }
( cd "$APP" && sudo -u tst .venv/bin/python manage.py migrate --noinput -v0 \
  && sudo -u tst .venv/bin/python manage.py collectstatic --noinput -v0 )

say "8/9 Services, HTTPS, firewall, backups"
cat > /etc/systemd/system/tst-web.service <<UNIT
[Unit]
Description=TST Vazifalar web
After=network.target postgresql.service
[Service]
User=tst
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/gunicorn tst.wsgi:application --bind 127.0.0.1:8000 --workers 2 --max-requests 500 --timeout 30
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/tst-bot.service <<UNIT
[Unit]
Description=TST Vazifalar Telegram bot
After=network.target postgresql.service
[Service]
User=tst
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/python manage.py run_bot
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/caddy/Caddyfile <<CADDY
$DOMAIN {
    encode gzip
    handle_path /static/* {
        root * $APP/staticfiles
        file_server
    }
    reverse_proxy 127.0.0.1:8000
}
CADDY
mkdir -p /var/backups/tst && chown postgres:tst /var/backups/tst && chmod 770 /var/backups/tst
cat > /usr/local/bin/tst-backup <<'BK'
#!/usr/bin/env bash
# Daily: database copy on the server (kept 30 days) + the same file to the bosh's Telegram (off-server copy).
set -euo pipefail
F=/var/backups/tst/tst-$(date +%F).sql.gz
sudo -u postgres pg_dump tst_vazifalar | gzip > "$F"
chmod 640 "$F"; chgrp tst "$F"
find /var/backups/tst -name 'tst-*.sql.gz' -mtime +30 -delete
cd /opt/tst-group/vazifalar && sudo -u tst .venv/bin/python manage.py send_backup "$F"
BK
chmod 750 /usr/local/bin/tst-backup
chgrp tst /var/backups/tst && chmod 750 /var/backups/tst
cat > /etc/cron.d/tst-backup <<'CRON'
30 2 * * * root /usr/local/bin/tst-backup >> /var/log/tst-backup.log 2>&1
CRON
ufw allow OpenSSH >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw --force enable >/dev/null
systemctl daemon-reload
systemctl enable --now tst-web tst-bot >/dev/null
systemctl restart caddy

say "9/9 People"
( cd "$APP" && sudo -u tst .venv/bin/python manage.py seed_people )
echo
echo "Save these passwords now (shown once). Give each person HIS OWN, privately. They can change it at /parol/."
echo
echo "DONE. Open: https://$DOMAIN"
echo "Updates later: bash $APP/scripts/deploy.sh"
echo "Backups: every night 02:30 on the server + sent to the bosh's Telegram (after he links Telegram)."
