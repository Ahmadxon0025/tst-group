# CORE: reusable — the pages. Every write goes through vazifalar/services.py.
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

import audit.models as audit
from accounts.middleware import login_required
from accounts.models import UserAccount
from config import values as cfg
from core import dates
from vazifalar import services as sv
from vazifalar.models import Vazifa, VazifaEvent

WEEK_OFFSET_LIMIT = 104   # CORE: about two years either way


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _parse_date(v):
    try:
        return date.fromisoformat((v or "").strip())
    except ValueError:
        return None


def _with_counts(qs):
    return qs.annotate(izoh_count=Count("events", filter=Q(events__kind=VazifaEvent.IZOH)))


def _late_text(task, today):
    return f"{(today - task.due_date).days} kun kechikdi"


def _back(request, default="/"):
    """Return to the page the form came from — only a local path."""
    nxt = request.POST.get("next") or ""
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else default


def _filters(request, me):
    """Person (?kim=) and company (?k=) filters, applied on top of what this person may see."""
    who = None
    username = request.GET.get("kim") or "all"
    if username != "all":
        who = UserAccount.objects.filter(username=username, is_active=True).first()
    company = request.GET.get("k") or ""
    if company not in dict(cfg.COMPANIES):
        company = ""
    qs = sv.visible_tasks(me).exclude(status=Vazifa.BEKOR)
    if who is not None:
        qs = qs.filter(assignee=who)
    if company:
        qs = qs.filter(company=company)
    return qs, who, company


@login_required
def hafta(request):
    """Todoist-style: the board starts TODAY and runs 7 days; ‹ › move by 7 days. Overdue is the first column."""
    me = request.account
    today = dates.today()
    w = max(-WEEK_OFFSET_LIMIT, min(WEEK_OFFSET_LIMIT, _int(request.GET.get("w"))))
    start = today + timedelta(days=7 * w)
    end = start + timedelta(days=6)
    base, who, company = _filters(request, me)

    overdue = list(_with_counts(base.filter(status=Vazifa.YANGI, due_date__lt=today)).order_by("due_date"))
    for t in overdue:
        t.late_text = _late_text(t, today)
        t.dm = dates.day_month_short(t.due_date)

    week = (_with_counts(base.filter(due_date__range=(start, end)))
            .exclude(status=Vazifa.YANGI, due_date__lt=today))   # open past tasks live in Kechikkan only
    by_day = {}
    for t in week:
        by_day.setdefault(t.due_date, []).append(t)

    days = []
    for i in range(7):
        d = start + timedelta(days=i)
        on_day = by_day.get(d, [])
        tasks = sorted((t for t in on_day if not t.is_done), key=lambda t: t.created_at)
        days.append({"iso": d.isoformat(), "dm": dates.day_month_short(d), "wd": cfg.DAY_LONG[d.weekday()],
                     "is_today": d == today, "is_past": d < today, "tasks": tasks,
                     "done_count": sum(1 for t in on_day if t.is_done)})

    q = {"w": w, "kim": who.username if who else "all"}
    if company:
        q["k"] = company
    here = f"/?{urlencode(q)}"

    def link(**kw):
        return f"/?{urlencode({k: v for k, v in dict(q, **kw).items() if v not in ('', None)})}"

    title = who.name if who else "Hafta"
    if company:
        title = f"{title} · {dict(cfg.COMPANIES)[company]}" if who else dict(cfg.COMPANIES)[company]
    return render(request, "vazifalar/hafta.html", {
        "days": days, "overdue": overdue, "month_label": dates.month_label(start, end), "title": title,
        "prev_link": link(w=w - 1), "next_link": link(w=w + 1), "today_link": link(w=0),
        "is_this_week": w == 0, "who": who, "here": here, "kim_value": q["kim"], "company": company,
        "company_links": [{"key": "", "label": "Hammasi", "href": link(k=""), "on": not company}] + [
            {"key": k, "label": lbl, "href": link(k=k), "on": company == k} for k, lbl in cfg.COMPANIES],
        "person_links": [{"username": "all", "label": "Hammasi", "href": link(kim="all"), "on": who is None}] + [
            {"username": p.username, "label": p.name, "color": p.color, "initial": p.initial,
             "href": link(kim=p.username), "on": who is not None and who.pk == p.pk}
            for p in sv.assignable_people()],
        "default_assignee": (who.username if who else ""), "default_company": company,
    })


@login_required
def mening(request):
    me = request.account
    today = dates.today()
    mine = _with_counts(Vazifa.objects.filter(assignee=me).select_related("assignee", "created_by"))
    open_qs = mine.filter(status=Vazifa.YANGI)
    overdue = list(open_qs.filter(due_date__lt=today).order_by("due_date"))
    for t in overdue:
        t.late_text = _late_text(t, today)
    groups = [
        ("Kechikkan", "late", overdue),
        ("Bugun", "today", list(open_qs.filter(due_date=today))),
        ("Keyingi", "next", list(open_qs.filter(due_date__gt=today).order_by("due_date"))),
        ("Bajarilgan (7 kun)", "done",
         list(mine.filter(status=Vazifa.BAJARILDI, done_at__date__gte=today - timedelta(days=7))
              .order_by("-done_at"))),
    ]
    given = []
    if me.can_create:
        given = list(_with_counts(Vazifa.objects.filter(created_by=me, status=Vazifa.YANGI)
                                  .exclude(assignee=me).select_related("assignee")).order_by("due_date"))
        for t in given:
            if t.due_date < today:
                t.late_text = _late_text(t, today)
    for _, _, items in groups:
        for t in items:
            t.dm = dates.day_month_short(t.due_date)
    for t in given:
        t.dm = dates.day_month_short(t.due_date)
    return render(request, "vazifalar/mening.html", {"groups": groups, "given": given, "here": "/mening/"})


@login_required
def shtab(request):
    """The Monday Shtab page: per person — overdue, due in the next 7 days, done in the last 7 days. Printable."""
    me = request.account
    today = dates.today()
    week_end = today + timedelta(days=6)
    base, _who, company = _filters(request, me)
    base = _with_counts(base)
    rows = []
    for p in sv.assignable_people():
        mine = base.filter(assignee=p)
        late = list(mine.filter(status=Vazifa.YANGI, due_date__lt=today).order_by("due_date"))
        soon = list(mine.filter(status=Vazifa.YANGI, due_date__range=(today, week_end)).order_by("due_date"))
        done = mine.filter(status=Vazifa.BAJARILDI, done_at__date__gte=today - timedelta(days=7)).count()
        for t in late:
            t.late_text = _late_text(t, today)
            t.dm = dates.day_month_short(t.due_date)
        for t in soon:
            t.dm = dates.day_month_short(t.due_date)
        if late or soon or done:
            rows.append({"p": p, "late": late, "soon": soon, "done": done})
    return render(request, "vazifalar/shtab.html", {
        "rows": rows, "today_dm": dates.day_month(today), "end_dm": dates.day_month(week_end),
        "here": "/shtab/" + (f"?k={company}" if company else ""), "company": company,
        "company_links": [{"label": "Hammasi", "href": "/shtab/", "on": not company}] + [
            {"label": lbl, "href": f"/shtab/?k={k}", "on": company == k} for k, lbl in cfg.COMPANIES],
    })


@login_required
def detail(request, pk: int):
    me = request.account
    task = sv.visible_tasks(me).filter(pk=pk).first()
    if task is None:
        raise Http404
    events = list(task.events.select_related("actor", "old_assignee", "new_assignee"))
    for e in events:
        local = timezone.localtime(e.created_at)
        e.when = dates.day_month(local.date()) + local.strftime(" %H:%M")
    return render(request, "vazifalar/detail.html", {
        "t": task, "events": events, "due_dm": dates.day_month(task.due_date),
        "here": f"/vazifa/{task.pk}/", "back": request.GET.get("next") or "/",
        "can_manage": sv.can_manage(me, task), "can_touch": sv.can_touch(me, task),
        "people": sv.assignable_people(), "companies": cfg.COMPANIES,
    })


@login_required
@require_POST
def create(request):
    me = request.account
    assignee = UserAccount.objects.filter(username=request.POST.get("kim") or "", is_active=True).first()
    try:
        if assignee is None:
            raise sv.NotAllowed("Kimga ekanini tanlang.")
        sv.create_task(me, request.POST.get("title"), assignee, _parse_date(request.POST.get("due")),
                       company=request.POST.get("company") or "")
        messages.success(request, "Qo'shildi.")
    except sv.NotAllowed as e:
        messages.error(request, str(e))
    return redirect(_back(request))


@login_required
@require_POST
def set_script(request):
    me = request.account
    new = "cyrl" if me.script != "cyrl" else "latn"
    audit.write(me.username, "yozuv", "user_account", me.pk, old={"script": me.script}, new={"script": new})
    me.script = new
    me.save(update_fields=["script"])
    return redirect(_back(request))


def _task_action(fn):
    @login_required
    @require_POST
    def view(request, pk: int):
        try:
            fn(request, pk)
        except Vazifa.DoesNotExist:
            raise Http404
        except sv.NotAllowed as e:
            messages.error(request, str(e))
        return redirect(_back(request))
    return view


@_task_action
def toggle(request, pk):
    task = Vazifa.objects.get(pk=pk)
    if task.is_done:
        sv.reopen(request.account, pk)
    else:
        sv.mark_done(request.account, pk)


@_task_action
def cancel(request, pk):
    sv.cancel(request.account, pk, request.POST.get("reason"))
    messages.success(request, "Bekor qilindi.")


@_task_action
def due(request, pk):
    sv.change_due(request.account, pk, _parse_date(request.POST.get("due")))
    messages.success(request, "Muddat o'zgardi.")


@_task_action
def kimga(request, pk):
    who = UserAccount.objects.filter(username=request.POST.get("kim") or "", is_active=True).first()
    sv.reassign(request.account, pk, who)
    messages.success(request, "O'tkazildi.")


@_task_action
def kompaniya(request, pk):
    sv.set_company(request.account, pk, request.POST.get("company") or "")
    messages.success(request, "Saqlandi.")


@_task_action
def comment(request, pk):
    sv.add_comment(request.account, pk, request.POST.get("text"))
