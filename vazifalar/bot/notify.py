"""
bot/notify.py — turns task changes into Outbox rows. Called from vazifalar/services.py INSIDE the same
transaction, so the message exists exactly when the change exists.
# CORE: reusable.
"""
from accounts.models import UserAccount
from bot import texts as T
from bot.models import Outbox
from core import dates
from core.translit import to_cyrillic


def render(user: UserAccount, text: str) -> str:  # CORE: reusable — each person in his own script
    return to_cyrillic(text) if user.is_cyrl else text


def task_buttons(user: UserAccount, task_id: int, comment=True):  # CORE: reusable
    row = [{"text": render(user, T.DONE_BTN), "callback_data": f"d:{task_id}"}]
    if comment:
        row.append({"text": render(user, T.COMMENT_BTN), "callback_data": f"c:{task_id}"})
    return {"inline_keyboard": [row]}


def enqueue(user: UserAccount, key: str, text: str, markup=None) -> bool:  # CORE: reusable
    """One message per key, ever. Nothing is queued for a person who has not linked Telegram."""
    if not user or not user.telegram_user_id or not user.is_active:
        return False
    _, created = Outbox.objects.get_or_create(key=key[:120], defaults={
        "user": user, "chat_id": user.telegram_user_id, "text": render(user, text), "markup": markup})
    return created


def _co(task) -> str:
    return f"\n#{task.company_label}" if task.company else ""


def on_event(event) -> None:  # CORE: reusable — the one entry point from services
    task, actor, kind = event.vazifa, event.actor, event.kind
    key = f"ev:{event.pk}"
    due = dates.day_month(task.due_date)
    if kind == "yaratildi" and task.assignee_id != actor.pk:
        enqueue(task.assignee, f"{key}:a", T.ASSIGNED.format(title=task.title, by=actor.name, due=due, co=_co(task)),
                task_buttons(task.assignee, task.pk))
    elif kind == "kimga" and event.new_assignee_id and event.new_assignee_id != actor.pk:
        enqueue(event.new_assignee, f"{key}:a",
                T.REASSIGNED.format(title=task.title, by=actor.name, due=due, co=_co(task)),
                task_buttons(event.new_assignee, task.pk))
    elif kind == "bajarildi" and task.created_by_id != actor.pk:
        enqueue(task.created_by, f"{key}:g", T.DONE_TO_GIVER.format(title=task.title, who=actor.name))
    elif kind == "qayta_ochildi" and task.assignee_id != actor.pk:
        enqueue(task.assignee, f"{key}:a", T.REOPENED.format(title=task.title, by=actor.name),
                task_buttons(task.assignee, task.pk))
    elif kind == "muddat" and task.assignee_id != actor.pk:
        enqueue(task.assignee, f"{key}:a", T.DUE_CHANGED.format(
            title=task.title, old=dates.day_month(event.old_due), new=dates.day_month(event.new_due)))
    elif kind == "bekor" and task.assignee_id != actor.pk:
        enqueue(task.assignee, f"{key}:a", T.CANCELLED.format(title=task.title, reason=event.note))
    elif kind == "nom" and task.assignee_id != actor.pk:
        enqueue(task.assignee, f"{key}:a", T.RENAMED.format(old=event.note, new=task.title),
                task_buttons(task.assignee, task.pk))
    elif kind == "izoh":
        for other in {task.assignee, task.created_by}:
            if other.pk != actor.pk:
                enqueue(other, f"{key}:{other.pk}", T.COMMENTED.format(by=actor.name, title=task.title,
                                                                         text=event.note[:500]))
