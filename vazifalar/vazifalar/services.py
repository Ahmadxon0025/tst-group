"""
vazifalar/services.py — the ONLY code that writes tasks. Web pages and the Telegram bot both call these.
# CORE: reusable — permissions come from the person's role policy (CONFIG ROLES), never from names.

Rules:
- A person whose role can_create makes tasks for anyone.
- The task's creator or a sees_all person cancels, re-dates or hands it to someone else ("manage").
- The assignee, the creator or a sees_all person marks it done, reopens it, or comments ("touch").
- A person sees tasks given to him and tasks he gave; a sees_all person sees everything.
- A cancel needs a reason. A cancelled task cannot be changed again (it stays in history).
- Each write = state change + VazifaEvent + AuditLog, in one transaction.
"""
from datetime import date

from django.db import transaction
from django.utils import timezone

import audit.models as audit
from accounts.models import UserAccount
from config import values as cfg
from vazifalar.models import Vazifa, VazifaEvent


class NotAllowed(Exception):  # CORE: reusable — shown to the person as a plain sentence
    pass


# --- who may see what ---------------------------------------------------------------------------
def visible_tasks(account: UserAccount):  # CORE: reusable
    from django.db.models import Q
    qs = Vazifa.objects.select_related("assignee", "created_by")
    return qs if account.sees_all else qs.filter(Q(assignee=account) | Q(created_by=account))


def can_touch(account: UserAccount, task: Vazifa) -> bool:  # CORE: reusable
    return account.sees_all or task.assignee_id == account.pk or task.created_by_id == account.pk


def can_manage(account: UserAccount, task: Vazifa) -> bool:  # CORE: reusable
    return account.sees_all or (account.can_create and task.created_by_id == account.pk)


def _company(key: str) -> str:
    key = (key or "").strip()
    if key and key not in dict(cfg.COMPANIES):
        raise NotAllowed("Bunday kompaniya yo'q.")
    return key


def assignable_people():  # CORE: reusable
    return UserAccount.objects.filter(is_active=True).order_by("created_at")


def _locked(task_id) -> Vazifa:
    return Vazifa.objects.select_for_update().get(pk=task_id)


def _event(task, kind, actor, source, **kw):
    """Write the history line and queue its Telegram messages — same transaction (bot/notify.py)."""
    ev = VazifaEvent.objects.create(vazifa=task, kind=kind, actor=actor, source=source, **kw)
    from bot.notify import on_event
    on_event(ev)
    return ev


# --- writes -------------------------------------------------------------------------------------
def create_task(actor: UserAccount, title: str, assignee: UserAccount, due_date: date,
                source: str = VazifaEvent.WEB, company: str = "") -> Vazifa:  # CORE: reusable
    if not actor.can_create:
        raise NotAllowed("Sizda vazifa qo'shish huquqi yo'q.")
    company = _company(company)
    title = " ".join((title or "").split())
    if not title:
        raise NotAllowed("Nima qilish kerakligini yozing.")
    if len(title) > cfg.TASK_TITLE_MAX:
        raise NotAllowed(f"Matn {cfg.TASK_TITLE_MAX} belgidan oshmasin.")
    if not assignee.is_active:
        raise NotAllowed("Bu odam faol emas.")
    if due_date is None:
        raise NotAllowed("Muddatni tanlang.")
    with transaction.atomic():
        task = Vazifa.objects.create(title=title, assignee=assignee, due_date=due_date, created_by=actor,
                                     company=company)
        _event(task, VazifaEvent.YARATILDI, actor, source, new_due=due_date, new_assignee=assignee)
        audit.write(actor.username, "vazifa_yaratildi", "vazifa", task.pk,
                    new={"title": title, "assignee": assignee.username, "due": due_date.isoformat(),
                         "company": company})
    return task


def mark_done(actor: UserAccount, task_id: int, source: str = VazifaEvent.WEB) -> Vazifa:  # CORE: reusable
    with transaction.atomic():
        task = _locked(task_id)
        if not can_touch(actor, task):
            raise NotAllowed("Bu vazifa sizniki emas.")
        if task.status == Vazifa.BEKOR:
            raise NotAllowed("Bekor qilingan vazifa.")
        if task.status == Vazifa.BAJARILDI:
            return task                          # pressed twice: nothing new happens
        task.status, task.done_at = Vazifa.BAJARILDI, timezone.now()
        task.save(update_fields=["status", "done_at"])
        _event(task, VazifaEvent.BAJARILDI, actor, source)
        audit.write(actor.username, "vazifa_bajarildi", "vazifa", task.pk,
                    old={"status": Vazifa.YANGI}, new={"status": Vazifa.BAJARILDI})
    return task


def reopen(actor: UserAccount, task_id: int, source: str = VazifaEvent.WEB) -> Vazifa:  # CORE: reusable
    with transaction.atomic():
        task = _locked(task_id)
        if not can_touch(actor, task):
            raise NotAllowed("Bu vazifa sizniki emas.")
        if task.status != Vazifa.BAJARILDI:
            return task
        task.status, task.done_at = Vazifa.YANGI, None
        task.save(update_fields=["status", "done_at"])
        _event(task, VazifaEvent.QAYTA_OCHILDI, actor, source)
        audit.write(actor.username, "vazifa_qayta_ochildi", "vazifa", task.pk,
                    old={"status": Vazifa.BAJARILDI}, new={"status": Vazifa.YANGI})
    return task


def cancel(actor: UserAccount, task_id: int, reason: str, source: str = VazifaEvent.WEB) -> Vazifa:  # CORE
    reason = " ".join((reason or "").split())
    if len(reason) < cfg.CANCEL_REASON_MIN:
        raise NotAllowed("Bekor qilish sababini yozing.")
    with transaction.atomic():
        task = _locked(task_id)
        if not can_manage(actor, task):
            raise NotAllowed("Bu vazifani faqat uni bergan odam yoki bosh direktor bekor qila oladi.")
        if task.status == Vazifa.BEKOR:
            return task
        old = task.status
        task.status = Vazifa.BEKOR
        task.save(update_fields=["status"])
        _event(task, VazifaEvent.BEKOR, actor, source, note=reason)
        audit.write(actor.username, "vazifa_bekor", "vazifa", task.pk,
                    old={"status": old}, new={"status": Vazifa.BEKOR, "reason": reason})
    return task


def change_due(actor: UserAccount, task_id: int, new_due: date, source: str = VazifaEvent.WEB) -> Vazifa:
    # CORE: reusable
    if new_due is None:
        raise NotAllowed("Yangi muddatni tanlang.")
    with transaction.atomic():
        task = _locked(task_id)
        if not can_manage(actor, task):
            raise NotAllowed("Muddatni faqat vazifani bergan odam yoki bosh direktor o'zgartira oladi.")
        if task.status == Vazifa.BEKOR:
            raise NotAllowed("Bekor qilingan vazifa.")
        if task.due_date == new_due:
            return task
        old = task.due_date
        task.due_date = new_due
        task.save(update_fields=["due_date"])
        _event(task, VazifaEvent.MUDDAT, actor, source, old_due=old, new_due=new_due)
        audit.write(actor.username, "vazifa_muddat", "vazifa", task.pk,
                    old={"due": old.isoformat()}, new={"due": new_due.isoformat()})
    return task


def reassign(actor: UserAccount, task_id: int, new_assignee: UserAccount,
             source: str = VazifaEvent.WEB) -> Vazifa:  # CORE: reusable
    if new_assignee is None or not new_assignee.is_active:
        raise NotAllowed("Kimga o'tkazishni tanlang.")
    with transaction.atomic():
        task = _locked(task_id)
        if not can_manage(actor, task):
            raise NotAllowed("Vazifani faqat uni bergan odam yoki bosh direktor boshqaga o'tkaza oladi.")
        if task.status == Vazifa.BEKOR:
            raise NotAllowed("Bekor qilingan vazifa.")
        if task.assignee_id == new_assignee.pk:
            return task
        old = task.assignee
        task.assignee = new_assignee
        task.save(update_fields=["assignee"])
        _event(task, VazifaEvent.KIMGA, actor, source, old_assignee=old, new_assignee=new_assignee)
        audit.write(actor.username, "vazifa_kimga", "vazifa", task.pk,
                    old={"assignee": old.username}, new={"assignee": new_assignee.username})
    return task


def set_company(actor: UserAccount, task_id: int, company: str) -> Vazifa:  # CORE: reusable
    company = _company(company)
    with transaction.atomic():
        task = _locked(task_id)
        if not can_manage(actor, task):
            raise NotAllowed("Kompaniyani faqat vazifani bergan odam yoki bosh direktor o'zgartira oladi.")
        if task.company == company:
            return task
        old = task.company
        task.company = company
        task.save(update_fields=["company"])
        _event(task, VazifaEvent.KOMPANIYA, actor, VazifaEvent.WEB, note=task.company_label or "—")
        audit.write(actor.username, "vazifa_kompaniya", "vazifa", task.pk, old={"company": old}, new={"company": company})
    return task


def add_comment(actor: UserAccount, task_id: int, text: str, source: str = VazifaEvent.WEB) -> VazifaEvent:
    # CORE: reusable
    text = (text or "").strip()
    if not text:
        raise NotAllowed("Izoh bo'sh.")
    with transaction.atomic():
        task = _locked(task_id)
        if not can_touch(actor, task):
            raise NotAllowed("Bu vazifa sizniki emas.")
        ev = _event(task, VazifaEvent.IZOH, actor, source, note=text[:2000])
        audit.write(actor.username, "vazifa_izoh", "vazifa", task.pk, new={"note": text[:2000]})
    return ev
