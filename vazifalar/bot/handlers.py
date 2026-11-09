"""
bot/handlers.py — what the bot does with each update from Telegram.
# CORE: reusable — every write goes through vazifalar/services.py with source="telegram"; the presser is
looked up by his Telegram id (a person may only act as himself). Private chats only.
"""
import hashlib
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

import audit.models as audit
from accounts.models import UserAccount
from bot import api
from bot import texts as T
from bot.models import BotSession, LinkCode
from bot.notify import render
from config import values as cfg
from core import dates
from vazifalar import services as sv
from vazifalar.models import Vazifa, VazifaEvent

logger = logging.getLogger(__name__)
TG = VazifaEvent.TELEGRAM


def code_hash(code: str) -> str:  # CORE: reusable
    return hashlib.sha256(code.strip().encode()).hexdigest()


def _reply(chat_id, user, text, markup=None):
    payload = {"chat_id": chat_id, "text": render(user, text) if user else text}
    if markup:
        payload["reply_markup"] = markup
    try:
        api.call("sendMessage", **payload)
    except api.SendError:
        pass


def _answer(cq_id, user, text=""):
    try:
        api.call("answerCallbackQuery", callback_query_id=cq_id, text=render(user, text) if user and text else text)
    except api.SendError:
        pass


def _user(tg_id):
    return UserAccount.objects.filter(telegram_user_id=tg_id, is_active=True).first()


def _session(user):
    s, _ = BotSession.objects.get_or_create(user=user)
    return s


def _clear(user):
    BotSession.objects.filter(user=user).update(state="", data={})


# --- linking ------------------------------------------------------------------------------------
def link(tg_id: int, code: str):
    """One-time code from the website → this Telegram account belongs to that person."""
    now = timezone.now()
    with transaction.atomic():
        lc = (LinkCode.objects.select_for_update().filter(code_hash=code_hash(code), used_at__isnull=True,
                                                          expires_at__gt=now).select_related("user").first())
        if lc is None or not lc.user.is_active:
            return None
        UserAccount.objects.filter(telegram_user_id=tg_id).exclude(pk=lc.user_id).update(telegram_user_id=None)
        user = lc.user
        user.telegram_user_id = tg_id
        user.save(update_fields=["telegram_user_id"])
        lc.used_at = now
        lc.save(update_fields=["used_at"])
        audit.write(user.username, "telegram_ulandi", "user_account", user.pk)
    return user


# --- lists -----------------------------------------------------------------------------------------
def _list(user, title, tasks, today, show_who=False):
    lines, buttons = [title], []
    for i, t in enumerate(tasks, 1):
        extra = []
        if t.due_date != today:
            extra.append(dates.day_month_short(t.due_date))
        if show_who and t.assignee_id != user.pk:
            extra.append(t.assignee.name)
        lines.append(f"{i}. {t.title}" + (f" ({', '.join(extra)})" if extra else ""))
        if sv.can_touch(user, t):
            buttons.append({"text": f"✓ {i}", "callback_data": f"d:{t.pk}"})
    rows = [buttons[i:i + 5] for i in range(0, len(buttons), 5)]
    return "\n".join(lines), ({"inline_keyboard": rows} if rows else None)


def cmd_bugun(chat_id, user):
    today = dates.today()
    qs = Vazifa.objects.filter(assignee=user, status=Vazifa.YANGI, due_date__lte=today).order_by("due_date")
    tasks = list(qs.select_related("assignee"))
    if not tasks:
        return _reply(chat_id, user, T.NONE_TODAY)
    text, mk = _list(user, T.MORNING_HEAD.format(n=len(tasks)), tasks, today)
    _reply(chat_id, user, text, mk)


def cmd_hafta(chat_id, user):
    today = dates.today()
    tasks = list(Vazifa.objects.filter(assignee=user, status=Vazifa.YANGI,
                                       due_date__range=(today, today + timedelta(days=6)))
                 .order_by("due_date").select_related("assignee"))
    if not tasks:
        return _reply(chat_id, user, T.NONE_WEEK)
    text, mk = _list(user, T.WEEK_HEAD.format(n=len(tasks)), tasks, None)
    _reply(chat_id, user, text, mk)


def cmd_kechikkan(chat_id, user):
    today = dates.today()
    tasks = list(sv.visible_tasks(user).filter(status=Vazifa.YANGI, due_date__lt=today).order_by("due_date"))
    if not tasks:
        return _reply(chat_id, user, T.NONE_LATE)
    text, mk = _list(user, T.LATE_HEAD.format(n=len(tasks)), tasks, None, show_who=True)
    _reply(chat_id, user, text, mk)


# --- creating a task in the chat -------------------------------------------------------------------
def _who_keyboard(user):
    rows, row = [], []
    for p in sv.assignable_people():
        row.append({"text": render(user, p.name), "callback_data": f"nw:{p.username}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return {"inline_keyboard": rows}


def _due_keyboard(user):
    return {"inline_keyboard": [[{"text": render(user, T.DUE_TODAY), "callback_data": "nd:0"},
                                 {"text": render(user, T.DUE_TOMORROW), "callback_data": "nd:1"},
                                 {"text": render(user, T.DUE_WEEK), "callback_data": "nd:7"}]]}


def _co_keyboard(user):
    row = [{"text": render(user, T.NO_COMPANY), "callback_data": "nc:-"}]
    row += [{"text": label, "callback_data": f"nc:{k}"} for k, label in cfg.COMPANIES]
    return {"inline_keyboard": [row[:3], row[3:]]}


def quick_ask(chat_id, user, text):
    """Any plain message from a person who may create tasks → a parsed preview with Qo'shish / Yo'q."""
    from vazifalar.quick import parse_text
    p = parse_text(text)
    if not p.title:
        return _reply(chat_id, user, T.QUICK_EMPTY)
    who = UserAccount.objects.filter(username=p.who or user.username, is_active=True).first() or user
    due = p.due                                   # no date → "Rejasiz"
    s = _session(user)
    s.state = "quick"
    s.data = {"title": p.title[:cfg.TASK_TITLE_MAX], "who": who.username, "due": due.isoformat() if due else "",
              "co": p.company or "", "cat": p.category or "", "imp": p.important, "rep": p.repeat, "prv": p.private}
    s.save()
    extra = ""
    if p.company:
        extra += f" · #{dict(cfg.COMPANIES)[p.company]}"
    if p.category:
        extra += " · /" + {k: lbl for k, lbl, _ in cfg.CATEGORIES}[p.category]
    if p.important:
        extra += " · ❗"
    if p.private:
        extra += " · 🔒 Maxfiy"
    if p.repeat:
        extra += " · 🔁 " + Vazifa(repeat=p.repeat).repeat_label
    _reply(chat_id, user, T.QUICK_ASK.format(title=p.title, who=who.name, due=dates.day_month(due), extra=extra),
           {"inline_keyboard": [[{"text": render(user, T.QUICK_YES), "callback_data": "qa:y"},
                                 {"text": render(user, T.QUICK_NO), "callback_data": "qa:n"}]]})


def cmd_yangi(chat_id, user):
    if not user.can_create:
        return _reply(chat_id, user, T.NEW_NO_RIGHT)
    s = _session(user)
    s.state, s.data = "new_title", {}
    s.save()
    _reply(chat_id, user, T.NEW_ASK_TITLE)


def _finish_new(chat_id, user, s):
    d = s.data
    assignee = UserAccount.objects.filter(username=d.get("who"), is_active=True).first()
    due = dates.today() + timedelta(days=int(d.get("due", 0)))
    try:
        t = sv.create_task(user, d.get("title", ""), assignee, due, source=TG, company=d.get("co", ""))
    except sv.NotAllowed as e:
        _clear(user)
        return _reply(chat_id, user, str(e))
    _clear(user)
    _reply(chat_id, user, T.NEW_OK.format(title=t.title, who=t.assignee.name, due=dates.day_month(t.due_date)))


# --- dispatch ---------------------------------------------------------------------------------------
COMMANDS = {"/bekor", "/bugun", "/hafta", "/kechikkan", "/yangi"}


def handle_message(msg: dict) -> None:
    chat = msg.get("chat") or {}
    if chat.get("type") != "private":
        return                                            # groups are ignored
    chat_id, tg_id = chat.get("id"), (msg.get("from") or {}).get("id")
    text = (msg.get("text") or "").strip()
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            user = link(tg_id, parts[1])
            return _reply(chat_id, user, T.LINKED.format(name=user.name) if user else T.LINK_BAD)
        user = _user(tg_id)
        return _reply(chat_id, user, T.HELP if user else T.NOT_LINKED)
    user = _user(tg_id)
    if user is None:
        return _reply(chat_id, None, T.NOT_LINKED)
    cmd = text.split("@")[0].split()[0].lower() if text.startswith("/") else ""
    if cmd and cmd not in COMMANDS:
        from vazifalar.quick import category_handles
        if cmd[1:] in category_handles():
            cmd = ""                                       # "/bank NBU xati ertaga" → quick add
    if cmd == "/bekor":
        _clear(user)
        return _reply(chat_id, user, T.CANCELLED_FLOW)
    if cmd:
        _clear(user)
        return {"/bugun": cmd_bugun, "/hafta": cmd_hafta, "/kechikkan": cmd_kechikkan,
                "/yangi": cmd_yangi}.get(cmd, lambda c, u: _reply(c, u, T.HELP))(chat_id, user)
    s = BotSession.objects.filter(user=user).first()
    if s and s.state == "comment" and text:
        task_id = s.data.get("task")
        _clear(user)
        try:
            sv.add_comment(user, task_id, text, source=TG)
            return _reply(chat_id, user, T.COMMENT_OK)
        except (sv.NotAllowed, Vazifa.DoesNotExist):
            return _reply(chat_id, user, T.NOT_YOURS)
    if (not s or s.state in ("", "quick")) and text and user.can_create:   # a new line replaces a pending one
        return quick_ask(chat_id, user, text)
    if s and s.state == "new_title" and text:
        s.data = {"title": text[:cfg.TASK_TITLE_MAX]}
        s.state = "new_who"
        s.save()
        return _reply(chat_id, user, T.NEW_ASK_WHO, _who_keyboard(user))
    _reply(chat_id, user, T.HELP)


def handle_callback(cq: dict) -> None:
    tg_id = (cq.get("from") or {}).get("id")
    msg = cq.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    data = cq.get("data") or ""
    user = _user(tg_id)
    if user is None:
        return _answer(cq.get("id"), None, T.NOT_LINKED)
    kind, _, arg = data.partition(":")
    if kind == "d":
        try:
            task = Vazifa.objects.get(pk=int(arg))
            if not task.is_open:
                return _answer(cq["id"], user, T.ALREADY)
            sv.mark_done(user, task.pk, source=TG)
            return _answer(cq["id"], user, T.DONE_OK)
        except (ValueError, Vazifa.DoesNotExist, sv.NotAllowed):
            return _answer(cq["id"], user, T.NOT_YOURS)
    if kind == "c":
        task = Vazifa.objects.filter(pk=int(arg) if arg.isdigit() else 0).first()
        if task is None or not sv.can_touch(user, task):
            return _answer(cq["id"], user, T.NOT_YOURS)
        s = _session(user)
        s.state, s.data = "comment", {"task": task.pk}
        s.save()
        _answer(cq["id"], user)
        return _reply(chat_id, user, T.ASK_COMMENT.format(title=task.title))
    s = BotSession.objects.filter(user=user).first()
    if kind == "qa" and s and s.state == "quick":
        d = s.data
        _clear(user)
        _answer(cq["id"], user)
        if arg != "y":
            return _reply(chat_id, user, T.CANCELLED_FLOW)
        from datetime import date as _date
        who = UserAccount.objects.filter(username=d.get("who"), is_active=True).first()
        try:
            t = sv.create_task(user, d.get("title", ""), who, _date.fromisoformat(d["due"]) if d.get("due") else None, source=TG,
                               company=d.get("co", ""), important=bool(d.get("imp")), repeat=d.get("rep", ""),
                               private=bool(d.get("prv")), category=d.get("cat", ""))
        except (sv.NotAllowed, KeyError, ValueError) as e:
            return _reply(chat_id, user, str(e))
        return _reply(chat_id, user, T.NEW_OK.format(title=t.title, who=t.assignee.name, due=dates.day_month(t.due_date)))
    if kind == "nw" and s and s.state == "new_who":
        s.data["who"], s.state = arg, "new_due"
        s.save()
        _answer(cq["id"], user)
        return _reply(chat_id, user, T.NEW_ASK_DUE, _due_keyboard(user))
    if kind == "nd" and s and s.state == "new_due" and arg in ("0", "1", "7"):
        s.data["due"], s.state = int(arg), "new_co"
        s.save()
        _answer(cq["id"], user)
        return _reply(chat_id, user, T.NEW_ASK_CO, _co_keyboard(user))
    if kind == "nc" and s and s.state == "new_co":
        s.data["co"] = "" if arg == "-" else arg
        s.save()
        _answer(cq["id"], user)
        return _finish_new(chat_id, user, s)
    _answer(cq.get("id"), user)


def handle_update(update: dict) -> None:  # CORE: reusable — never raises into the polling loop
    try:
        if "message" in update:
            handle_message(update["message"])
        elif "callback_query" in update:
            handle_callback(update["callback_query"])
    except Exception:                                      # noqa: BLE001 — one bad update must not stop the bot
        logger.exception("bot: update %s failed", update.get("update_id"))
