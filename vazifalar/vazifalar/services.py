"""
vazifalar/services.py — the ONLY code that writes tasks. Web pages and the Telegram bot both call these.
# CORE: reusable — permissions come from the person's role policy (CONFIG ROLES), never from names.

Rules:
- A person whose role can_create makes tasks for anyone.
- The task's creator or a sees_all person cancels, re-dates or hands it to someone else ("manage").
- The assignee, the creator or a sees_all person marks it done, reopens it, or comments ("touch").
- Everyone sees every task except "Maxfiy" ones; a Maxfiy task is seen only by its giver, its doer and a
  sees_all person (the bosh sees everything).
- "Delete" is a cancel: the task leaves the board but stays in history (a reason is optional).
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
    if account.sees_all:
        return qs
    return qs.filter(Q(private=False) | Q(assignee=account) | Q(created_by=account))


def can_touch(account: UserAccount, task: Vazifa) -> bool:  # CORE: reusable
    return account.sees_all or task.assignee_id == account.pk or task.created_by_id == account.pk


def can_manage(account: UserAccount, task: Vazifa) -> bool:  # CORE: reusable
    return account.sees_all or (account.can_create and task.created_by_id == account.pk)


def _company(key: str) -> str:
    key = (key or "").strip()
    if key and key not in dict(cfg.COMPANIES):
        raise NotAllowed("Bunday kompaniya yo'q.")
    return key


def _category(key: str) -> str:
    key = (key or "").strip()
    if key and key not in {k for k, _, _ in cfg.CATEGORIES}:
        raise NotAllowed("Bunday yo'nalish yo'q.")
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
REPEATS = ("", "daily", "weekly", "monthly")


def _repeat(rule: str) -> str:
    rule = (rule or "").strip()
    kind, _, arg = rule.partition(":")
    ok = kind in REPEATS and (not arg or (arg.isdigit() and (
        (kind == "weekly" and 0 <= int(arg) <= 6) or (kind == "monthly" and 1 <= int(arg) <= 31))))
    if not ok:
        raise NotAllowed("Takrorlash noto'g'ri.")
    return rule


def create_task(actor: UserAccount, title: str, assignee: UserAccount, due_date: date,
                source: str = VazifaEvent.WEB, company: str = "", important: bool = False,
                repeat: str = "", private: bool = False, category: str = "") -> Vazifa:  # CORE: reusable
    if not actor.can_create:
        raise NotAllowed("Sizda vazifa qo'shish huquqi yo'q.")
    company = _company(company)
    category = _category(category)
    repeat = _repeat(repeat)
    title = " ".join((title or "").split())
    if not title:
        raise NotAllowed("Nima qilish kerakligini yozing.")
    if len(title) > cfg.TASK_TITLE_MAX:
        raise NotAllowed(f"Matn {cfg.TASK_TITLE_MAX} belgidan oshmasin.")
    if not assignee.is_active:
        raise NotAllowed("Bu odam faol emas.")
    if repeat and due_date is None:
        from core import dates
        due_date = dates.today()                     # a repeating task needs a first date
    with transaction.atomic():
        task = Vazifa.objects.create(title=title, assignee=assignee, due_date=due_date, created_by=actor,
                                     company=company, important=bool(important), repeat=repeat,
                                     private=bool(private), category=category)
        _event(task, VazifaEvent.YARATILDI, actor, source, new_due=due_date, new_assignee=assignee)
        audit.write(actor.username, "vazifa_yaratildi", "vazifa", task.pk,
                    new={"title": title, "assignee": assignee.username, "due": due_date.isoformat() if due_date else None,
                         "company": company, "important": bool(important), "repeat": repeat,
                         "private": bool(private), "category": category})
    return task


def mark_done(actor: UserAccount, task_id: int, source: str = VazifaEvent.WEB) -> Vazifa:  # CORE: reusable
    with transaction.atomic():
        task = _locked(task_id)
        if not can_touch(actor, task):
            raise NotAllowed("Bu vazifa sizniki emas.")
        if task.status == Vazifa.BEKOR:
            raise NotAllowed("O'chirilgan vazifa.")
        if task.status == Vazifa.BAJARILDI:
            return task                          # pressed twice: nothing new happens
        task.status, task.done_at = Vazifa.BAJARILDI, timezone.now()
        task.save(update_fields=["status", "done_at"])
        _event(task, VazifaEvent.BAJARILDI, actor, source)
        audit.write(actor.username, "vazifa_bajarildi", "vazifa", task.pk,
                    old={"status": Vazifa.YANGI}, new={"status": Vazifa.BAJARILDI})
        _spawn_next(task)
    return task


def _spawn_next(task: Vazifa):  # CORE: reusable — a repeating task closed → the next one, once
    if not task.repeat or task.next_repeats.exists():
        return None
    from core import dates
    from core.quickadd import next_repeat
    due = next_repeat(task.repeat, task.due_date or dates.today(), dates.today())
    if due is None:
        return None
    nxt = Vazifa.objects.create(title=task.title, assignee=task.assignee, due_date=due, created_by=task.created_by,
                                company=task.company, category=task.category, important=task.important, repeat=task.repeat, repeat_of=task,
                                private=task.private)
    _event(nxt, VazifaEvent.YARATILDI, task.created_by, VazifaEvent.REPEAT, new_due=due, new_assignee=task.assignee)
    audit.write("system", "vazifa_takror", "vazifa", nxt.pk, new={"repeat_of": task.pk, "due": due.isoformat()})
    return nxt


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
    reason = " ".join((reason or "").split()) or cfg.DELETE_REASON_DEFAULT
    with transaction.atomic():
        task = _locked(task_id)
        if not can_manage(actor, task):
            raise NotAllowed("Bu vazifani faqat uni bergan odam yoki bosh direktor o'chira oladi.")
        if task.status == Vazifa.BEKOR:
            return task
        old = task.status
        task.status = Vazifa.BEKOR
        task.save(update_fields=["status"])
        _event(task, VazifaEvent.BEKOR, actor, source, note=reason)
        audit.write(actor.username, "vazifa_bekor", "vazifa", task.pk,
                    old={"status": old}, new={"status": Vazifa.BEKOR, "reason": reason})
    return task


def change_due(actor: UserAccount, task_id: int, new_due, source: str = VazifaEvent.WEB) -> Vazifa:
    # CORE: reusable — new_due None moves the task back to "Rejasiz"
    with transaction.atomic():
        task = _locked(task_id)
        if not can_manage(actor, task):
            raise NotAllowed("Muddatni faqat vazifani bergan odam yoki bosh direktor o'zgartira oladi.")
        if task.status == Vazifa.BEKOR:
            raise NotAllowed("O'chirilgan vazifa.")
        if task.due_date == new_due:
            return task
        old = task.due_date
        task.due_date = new_due
        task.save(update_fields=["due_date"])
        _event(task, VazifaEvent.MUDDAT, actor, source, old_due=old, new_due=new_due)
        audit.write(actor.username, "vazifa_muddat", "vazifa", task.pk,
                    old={"due": old.isoformat() if old else None},
                    new={"due": new_due.isoformat() if new_due else None})
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
            raise NotAllowed("O'chirilgan vazifa.")
        if task.assignee_id == new_assignee.pk:
            return task
        old = task.assignee
        task.assignee = new_assignee
        task.save(update_fields=["assignee"])
        _event(task, VazifaEvent.KIMGA, actor, source, old_assignee=old, new_assignee=new_assignee)
        audit.write(actor.username, "vazifa_kimga", "vazifa", task.pk,
                    old={"assignee": old.username}, new={"assignee": new_assignee.username})
    return task


def change_title(actor: UserAccount, task_id: int, title: str, source: str = VazifaEvent.WEB) -> Vazifa:
    # CORE: reusable
    title = " ".join((title or "").split())
    if not title:
        raise NotAllowed("Nima qilish kerakligini yozing.")
    if len(title) > cfg.TASK_TITLE_MAX:
        raise NotAllowed(f"Matn {cfg.TASK_TITLE_MAX} belgidan oshmasin.")
    with transaction.atomic():
        task = _locked(task_id)
        if not can_manage(actor, task):
            raise NotAllowed("Nomini faqat vazifani bergan odam yoki bosh direktor o'zgartira oladi.")
        if task.status == Vazifa.BEKOR:
            raise NotAllowed("O'chirilgan vazifa.")
        if task.title == title:
            return task
        old = task.title
        task.title = title
        task.save(update_fields=["title"])
        _event(task, VazifaEvent.NOM, actor, source, note=old)
        audit.write(actor.username, "vazifa_nom", "vazifa", task.pk, old={"title": old}, new={"title": title})
    return task


UNSET = object()   # "leave as it is" (None means: no date)


def update_task(actor: UserAccount, task_id: int, *, title=None, assignee=None, due_date=UNSET, company=None,
                important=None, repeat=None, private=None, category=None,
                source: str = VazifaEvent.WEB) -> Vazifa:  # CORE: reusable — the edit window's "Saqlash"
    """Applies only what changed, all in one transaction; each change is its own history line."""
    with transaction.atomic():
        task = Vazifa.objects.select_for_update().get(pk=task_id)
        if not can_manage(actor, task):
            raise NotAllowed("Vazifani faqat uni bergan odam yoki bosh direktor o'zgartira oladi.")
        if title is not None and " ".join(title.split()) != task.title:
            change_title(actor, task_id, title, source)
        if assignee is not None and assignee.pk != task.assignee_id:
            reassign(actor, task_id, assignee, source)
        if due_date is not UNSET and due_date != task.due_date:
            change_due(actor, task_id, due_date, source)
        if company is not None and company != task.company:
            set_company(actor, task_id, company)
        if category is not None and category != task.category:
            set_category(actor, task_id, category, source)
        if important is not None and bool(important) != task.important:
            task.refresh_from_db()
            task.important = bool(important)
            task.save(update_fields=["important"])
            _event(task, VazifaEvent.MUHIM, actor, source, note="Muhim" if task.important else "Oddiy")
            audit.write(actor.username, "vazifa_muhim", "vazifa", task.pk, new={"important": task.important})
        if private is not None and bool(private) != task.private:
            task.refresh_from_db()
            task.private = bool(private)
            task.save(update_fields=["private"])
            _event(task, VazifaEvent.MAXFIY, actor, source, note="Maxfiy" if task.private else "Hammaga ko'rinadi")
            audit.write(actor.username, "vazifa_maxfiy", "vazifa", task.pk, new={"private": task.private})
        if repeat is not None and _repeat(repeat) != task.repeat:
            task.refresh_from_db()
            old = task.repeat
            task.repeat = _repeat(repeat)
            task.save(update_fields=["repeat"])
            if task.repeat and task.due_date is None:
                from core import dates
                change_due(actor, task_id, dates.today(), source)
                task.refresh_from_db()
            _event(task, VazifaEvent.TAKROR, actor, source, note=task.repeat_label or "Takrorlanmaydi")
            audit.write(actor.username, "vazifa_takror_ozgardi", "vazifa", task.pk,
                        old={"repeat": old}, new={"repeat": task.repeat})
        task.refresh_from_db()
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


def set_category(actor: UserAccount, task_id: int, category: str,
                 source: str = VazifaEvent.WEB) -> Vazifa:  # CORE: reusable — the task's "Yo'nalish"
    category = _category(category)
    with transaction.atomic():
        task = _locked(task_id)
        if not can_manage(actor, task):
            raise NotAllowed("Yo'nalishni faqat vazifani bergan odam yoki bosh direktor o'zgartira oladi.")
        if task.category == category:
            return task
        old = task.category
        task.category = category
        task.save(update_fields=["category"])
        _event(task, VazifaEvent.YONALISH, actor, source, note=task.category_label or "—")
        audit.write(actor.username, "vazifa_yonalish", "vazifa", task.pk, old={"category": old}, new={"category": category})
    return task
