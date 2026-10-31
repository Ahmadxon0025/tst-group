"""
bot/models.py — what the Telegram bot needs to remember.
# CORE: reusable.

- LinkCode: a one-time code that links a person's Telegram to his account (hashed at rest, 15-minute life).
- Outbox: every message the bot must send, written in the SAME transaction as the change that caused it,
  so a message is never lost and never sent twice (unique key). The sender marks sent_at. Never deleted.
- BotSession: what a person is in the middle of in the chat (writing a comment, creating a task). Transient.
"""
from django.db import models

from accounts.models import UserAccount
from core.ledger import LedgerModel


class LinkCode(LedgerModel):  # CORE: reusable
    user = models.ForeignKey(UserAccount, on_delete=models.PROTECT, related_name="+")
    code_hash = models.CharField(max_length=128, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bot_link_code"


class Outbox(LedgerModel):  # CORE: reusable
    key = models.CharField(max_length=120, unique=True)      # dedupe: one message per key, ever
    user = models.ForeignKey(UserAccount, on_delete=models.PROTECT, related_name="+")
    chat_id = models.BigIntegerField()
    text = models.TextField()
    markup = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        db_table = "bot_outbox"
        indexes = [models.Index(fields=["sent_at", "created_at"])]


class BotSession(models.Model):  # CORE: reusable — transient chat state, may be overwritten
    user = models.OneToOneField(UserAccount, on_delete=models.CASCADE, related_name="bot_session")
    state = models.CharField(max_length=20, blank=True, default="")
    data = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bot_session"
