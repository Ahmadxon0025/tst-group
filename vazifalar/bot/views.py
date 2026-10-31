# CORE: reusable — the "Telegram" page: make a one-time link that connects this person's Telegram.
import secrets
from datetime import timedelta

from django.conf import settings
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

import audit.models as audit
from accounts.middleware import login_required
from bot.handlers import code_hash
from bot.models import LinkCode
from config import values as cfg


@login_required
@require_http_methods(["GET", "POST"])
def telegram_page(request):
    me = request.account
    link = code = None
    if request.method == "POST":
        code = secrets.token_urlsafe(12)
        LinkCode.objects.create(user=me, code_hash=code_hash(code),
                                expires_at=timezone.now() + timedelta(minutes=cfg.LINK_CODE_MINUTES))
        audit.write(me.username, "telegram_kod", "user_account", me.pk)
        username = (getattr(settings, "TST_BOT_USERNAME", "") or "").lstrip("@")
        if username:
            link = f"https://t.me/{username}?start={code}"
    return render(request, "bot/telegram.html", {
        "linked": bool(me.telegram_user_id), "link": link, "code": code, "minutes": cfg.LINK_CODE_MINUTES,
        "bot_username": (getattr(settings, "TST_BOT_USERNAME", "") or "").lstrip("@"),
    })
