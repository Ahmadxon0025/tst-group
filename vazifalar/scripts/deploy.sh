#!/usr/bin/env bash
# TST Vazifalar — update to the newest code (run as root on the server).
# Refuses to deploy if the tests fail on the new code. Takes a database copy before changing tables.
set -euo pipefail
ROOT=/opt/tst-group
APP=$ROOT/vazifalar
CHECK=/tmp/tst-check
cd "$ROOT"
sudo -u tst git fetch -q origin
NEW="$(sudo -u tst git rev-parse origin/main)"
[ "$NEW" = "$(sudo -u tst git rev-parse HEAD)" ] && { echo "Already up to date."; exit 0; }

echo "== Testing the new code before it goes live"
rm -rf "$CHECK"; sudo -u tst git worktree prune
sudo -u tst git worktree add -q "$CHECK" "$NEW"
sudo -u tst "$APP/.venv/bin/pip" install -q -r "$CHECK/vazifalar/requirements.txt"
if ! ( cd "$CHECK/vazifalar" && sudo -u tst DJANGO_SECRET_KEY=x "$APP/.venv/bin/python" -m pytest -q ); then
  sudo -u tst git worktree remove --force "$CHECK"; echo "TESTS FAILED — nothing changed."; exit 1; fi
sudo -u tst git worktree remove --force "$CHECK"

echo "== Database copy before update"
sudo -u postgres pg_dump tst_vazifalar | gzip > "/var/backups/tst/pre-deploy-$(date +%F-%H%M).sql.gz"

echo "== Updating"
sudo -u tst git merge -q --ff-only "$NEW"
cd "$APP"
sudo -u tst .venv/bin/python manage.py migrate --noinput -v0
sudo -u tst .venv/bin/python manage.py collectstatic --noinput -v0
systemctl restart tst-web tst-bot
sleep 2
systemctl is-active --quiet tst-web && systemctl is-active --quiet tst-bot && echo "OK — running $(sudo -u tst git -C "$ROOT" rev-parse --short HEAD)" \
  || { echo "A service did not start — check: journalctl -u tst-web -u tst-bot -n 50"; exit 1; }
