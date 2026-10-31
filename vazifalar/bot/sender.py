"""
bot/sender.py — sends what is in the Outbox, oldest first. Safe to run from several places: each row is
claimed with a row lock, so a message is sent once.
# CORE: reusable.
"""
import logging

from django.db import transaction
from django.utils import timezone

from bot import api
from bot.models import Outbox

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 8       # CORE: after this a message stops retrying (visible in the admin list)
BATCH = 25


def flush() -> int:  # CORE: reusable — returns how many were sent
    sent = 0
    ids = list(Outbox.objects.filter(sent_at__isnull=True, attempts__lt=MAX_ATTEMPTS)
               .order_by("created_at").values_list("pk", flat=True)[:BATCH])
    for pk in ids:
        with transaction.atomic():
            row = Outbox.objects.select_for_update(skip_locked=True).filter(pk=pk, sent_at__isnull=True).first()
            if row is None:
                continue
            payload = {"chat_id": row.chat_id, "text": row.text, "disable_web_page_preview": True}
            if row.markup:
                payload["reply_markup"] = row.markup
            try:
                api.call("sendMessage", **payload)
                row.sent_at = timezone.now()
                row.attempts += 1
                row.save(update_fields=["sent_at", "attempts"])
                sent += 1
            except api.SendError as e:
                row.attempts += 1
                row.last_error = str(e)[:300]
                row.save(update_fields=["attempts", "last_error"])
    return sent
