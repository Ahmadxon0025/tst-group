# CORE: reusable — the off-server copy: sends last night's database dump to every linked "bosh" in Telegram
# (private chat only). The file never goes anywhere else. Run by cron after the local dump.
#   python manage.py send_backup /var/backups/tst/tst-2026-11-01.sql.gz
import os

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

import audit.models as audit
from accounts.models import UserAccount
from bot import api

TELEGRAM_FILE_LIMIT = 45 * 1024 * 1024   # Telegram bots may send up to 50 MB


class Command(BaseCommand):
    help = "Send a backup file to the bosh's Telegram"

    def add_arguments(self, parser):
        parser.add_argument("path")

    def handle(self, path, **opts):
        if not os.path.isfile(path):
            raise CommandError(f"no file: {path}")
        size = os.path.getsize(path)
        if size > TELEGRAM_FILE_LIMIT:
            raise CommandError(f"file too big for Telegram ({size} bytes) — use another off-server copy")
        sent = 0
        for u in UserAccount.objects.filter(is_active=True, telegram_user_id__isnull=False):
            if not u.sees_all:
                continue
            caption = f"TST Vazifalar zaxira nusxasi {timezone.localdate():%d.%m.%Y} ({size // 1024} KB). Saqlab qo'ying."
            api.send_document(u.telegram_user_id, path, caption)
            sent += 1
        audit.write("server", "zaxira_yuborildi", "backup", os.path.basename(path), new={"to": sent, "bytes": size})
        self.stdout.write(f"sent to {sent}")
