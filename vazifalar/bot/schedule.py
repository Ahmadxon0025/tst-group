"""
bot/schedule.py — the timed messages. `tick(now)` runs every half minute; each message has a dated key, so
running it many times sends each message once. A message is only queued inside its window (a server that
restarts at 15:00 does not send the 08:00 list late).
# CORE: reusable — times come from CONFIG.
"""
from datetime import datetime, timedelta

from django.utils import timezone

from accounts.models import UserAccount
from bot import texts as T
from bot.notify import enqueue, render
from config import values as cfg
from core import dates
from vazifalar.models import Vazifa


def _hm(s: str):
    h, m = s.split(":")
    return int(h), int(m)


def _in_window(now_local, at: str) -> bool:
    h, m = _hm(at)
    start = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
    return start <= now_local < start + timedelta(minutes=cfg.BOT_SEND_WINDOW_MINUTES)


def _linked():
    return UserAccount.objects.filter(is_active=True, telegram_user_id__isnull=False)


def morning(today) -> None:
    for u in _linked():
        mine = Vazifa.objects.filter(assignee=u, status=Vazifa.YANGI)
        todays = list(mine.filter(due_date=today).order_by("-important", "created_at"))
        late = list(mine.filter(due_date__lt=today).order_by("-important", "due_date"))
        if not todays and not late:
            continue
        lines, buttons, n = [T.MORNING_HEAD.format(n=len(todays) + len(late))], [], 0
        for t in todays:
            n += 1
            lines.append(f"{n}. {'❗ ' if t.important else ''}{t.title}")
            buttons.append({"text": f"✓ {n}", "callback_data": f"d:{t.pk}"})
        if late:
            lines.append("")
            lines.append(T.MORNING_LATE)
            for t in late:
                n += 1
                lines.append(f"{n}. {'❗ ' if t.important else ''}{t.title} ({dates.day_month_short(t.due_date)})")
                buttons.append({"text": f"✓ {n}", "callback_data": f"d:{t.pk}"})
        rows = [buttons[i:i + 5] for i in range(0, len(buttons), 5)]
        enqueue(u, f"morning:{u.pk}:{today}", "\n".join(lines), {"inline_keyboard": rows})


def escalate(today) -> None:
    """Tasks that became late yesterday: tell the person who gave them (once)."""
    yesterday = today - timedelta(days=1)
    for t in Vazifa.objects.filter(status=Vazifa.YANGI, due_date=yesterday).select_related("assignee", "created_by"):
        if t.created_by_id == t.assignee_id:
            continue
        enqueue(t.created_by, f"late:{t.pk}:{today}",
                T.ESCALATE.format(title=t.title, who=t.assignee.name, due=dates.day_month(t.due_date)))


def evening(today) -> None:
    for t in Vazifa.objects.filter(status=Vazifa.YANGI, due_date=today).select_related("assignee", "created_by"):
        u = t.assignee
        enqueue(u, f"evening:{t.pk}:{today}", T.EVENING.format(title=t.title, giver=t.created_by.name),
                {"inline_keyboard": [[{"text": render(u, T.DONE_BTN), "callback_data": f"d:{t.pk}"},
                                      {"text": render(u, T.COMMENT_BTN), "callback_data": f"c:{t.pk}"}]]})


def weekly(today) -> None:
    start = today - timedelta(days=7)
    people = list(UserAccount.objects.filter(is_active=True).order_by("created_at"))
    lines = [T.WEEKLY_HEAD.format(start=dates.day_month_short(start), end=dates.day_month_short(today))]
    for p in people:
        mine = Vazifa.objects.filter(assignee=p)
        done = mine.filter(status=Vazifa.BAJARILDI, done_at__date__gte=start).count()
        open_n = mine.filter(status=Vazifa.YANGI).count()
        late = mine.filter(status=Vazifa.YANGI, due_date__lt=today).count()
        lines.append(T.WEEKLY_ROW.format(name=p.name, done=done, open=open_n, late=late))
    for u in _linked():
        if u.sees_all:
            enqueue(u, f"weekly:{u.pk}:{today}", "\n".join(lines))


def tick(now=None) -> None:  # CORE: reusable
    local = timezone.localtime(now or timezone.now())
    today = local.date()
    if _in_window(local, cfg.MORNING_LIST_AT):
        morning(today)
        escalate(today)
    if _in_window(local, cfg.EVENING_REMINDER_AT):
        evening(today)
    wd, at = cfg.WEEKLY_SUMMARY
    if local.weekday() == wd and _in_window(local, at):
        weekly(today)
