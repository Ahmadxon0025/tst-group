# CORE: reusable — a person who uses the system. Which roles exist is CONFIG (config.values.ROLES).
# Lean version of nazorat-erp accounts.UserAccount. Never hard-deleted: deactivate with is_active.
import uuid

from django.contrib.auth.hashers import check_password, make_password
from django.db import models

from config import values as cfg
from core.ledger import LedgerModel


class UserAccount(LedgerModel):  # CORE: reusable
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=120)                    # what the screen shows
    role = models.CharField(max_length=40)                     # key in CONFIG ROLES
    password_hash = models.CharField(max_length=255, default="!")
    is_active = models.BooleanField(default=True)
    telegram_user_id = models.BigIntegerField(null=True, blank=True, unique=True)   # linked by the bot step
    script = models.CharField(max_length=4, default="latn")    # "latn" or "cyrl" — the person's choice
    session_epoch = models.PositiveIntegerField(default=0)     # moves on at a reset/block: every device signs out
    must_change_password = models.BooleanField(default=False)  # a one-time password was given: choose your own
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_account"
        ordering = ["created_at"]

    def __str__(self):
        return self.name

    # --- role policy, read from CONFIG ----------------------------------------------------------
    def _policy(self) -> dict:  # CORE: reusable — an unknown role gets nothing (fails closed)
        return cfg.ROLES.get(self.role, {})

    @property
    def can_create(self) -> bool:
        return bool(self._policy().get("can_create"))

    @property
    def sees_all(self) -> bool:
        return bool(self._policy().get("sees_all"))

    @property
    def is_cyrl(self) -> bool:
        return self.script == "cyrl"

    @property
    def color(self) -> str:  # CORE: reusable — the colour comes from CONFIG, never from code
        c = cfg.PERSON_COLORS.get(self.username)
        if c:
            return c
        pal = cfg.PERSON_PALETTE
        return pal[sum(map(ord, self.username)) % len(pal)]

    @property
    def initial(self) -> str:
        return (self.name or self.username)[:1].upper()

    # --- password -------------------------------------------------------------------------------
    def set_password(self, raw: str):
        self.password_hash = make_password(raw)

    def check_password(self, raw: str) -> bool:
        return self.password_hash not in ("", "!") and check_password(raw, self.password_hash)
