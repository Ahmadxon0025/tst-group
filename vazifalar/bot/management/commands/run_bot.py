# CORE: reusable — the bot process: long polling (no public URL needed) + the outbox sender + the clock.
# Run as a systemd service. Ctrl+C / SIGTERM stops it cleanly.
import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from bot import api, handlers, schedule, sender

logger = logging.getLogger(__name__)
POLL_SECONDS = 10


class Command(BaseCommand):
    help = "Run the TST Vazifalar Telegram bot"

    def handle(self, *args, **opts):
        if not api.has_token():
            self.stderr.write("TST_BOT_TOKEN is empty — set it in .env")
            return
        api.call("setMyCommands", commands=[
            {"command": "bugun", "description": "Bugungi va kechikkan vazifalar"},
            {"command": "hafta", "description": "Keyingi 7 kun"},
            {"command": "kechikkan", "description": "Kechikkanlar"},
            {"command": "yangi", "description": "Yangi vazifa"},
        ])
        api.call("deleteWebhook")
        offset = None
        self.stdout.write("bot: running")
        while True:
            close_old_connections()
            try:
                params = {"timeout": POLL_SECONDS, "allowed_updates": ["message", "callback_query"]}
                if offset is not None:
                    params["offset"] = offset
                for upd in api.call("getUpdates", **params) or []:
                    offset = upd["update_id"] + 1
                    handlers.handle_update(upd)
            except api.SendError:
                time.sleep(3)
            try:
                schedule.tick()
                sender.flush()
            except Exception:                              # noqa: BLE001
                logger.exception("bot: tick/flush failed")
                time.sleep(3)
