# CORE: reusable — the pages. Every write goes through vazifalar/services.py.
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
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


def _flags(me, tasks):
    """What this person may do with each card: done (touch), edit/delete/drag (manage)."""
    for t in tasks:
        t.can_touch = sv.can_touch(me, t) and t.status != Vazifa.BEKOR
        t.can_manage = sv.can_manage(me, t) and t.status != Vazifa.BEKOR
        t.movable = t.can_manage and t.is_open
    return tasks


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
    end = start + timedelta(days=cfg.BOARD_DAYS - 1)
    base, who, company = _filters(request, me)

    overdue = list(_with_counts(base.filter(status=Vazifa.YANGI, due_date__lt=today)).order_by("-important", "due_date"))
    for t in overdue:
        t.late_text = _late_text(t, today)
        t.dm = dates.day_month_short(t.due_date)

    def mark(ts):
        return _flags(me, ts)
    mark(overdue)

    inbox = mark(list(_with_counts(base.filter(status=Vazifa.YANGI, due_date__isnull=True))
                      .order_by("-important", "created_at")))

    week = (_with_counts(base.filter(due_date__range=(start, end)))
            .exclude(status=Vazifa.YANGI, due_date__lt=today))   # open past tasks live in Kechikkan only
    by_day = {}
    for t in week:
        by_day.setdefault(t.due_date, []).append(t)

    days = []
    for i in range(cfg.BOARD_DAYS):
        d = start + timedelta(days=i)
        on_day = by_day.get(d, [])
        tasks = mark(sorted((t for t in on_day if not t.is_done), key=lambda t: (not t.important, t.created_at)))
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
        "days": days, "overdue": overdue, "inbox": inbox, "month_label": dates.month_label(start, end), "title": title,
        "prev_link": link(w=w - 1), "next_link": link(w=w + 3), "today_link": link(w=0),
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
    overdue = list(open_qs.filter(due_date__lt=today).order_by("-important", "due_date"))
    for t in overdue:
        t.late_text = _late_text(t, today)
    groups = [
        ("Kechikkan", "late", overdue),
        ("Bugun", "today", list(open_qs.filter(due_date=today).order_by("-important", "created_at"))),
        ("Keyingi", "next", list(open_qs.filter(due_date__gt=today).order_by("due_date", "-important"))),
        ("Rejasiz", "inbox", list(open_qs.filter(due_date__isnull=True).order_by("-important", "created_at"))),
        ("Bajarilgan (7 kun)", "done",
         list(mine.filter(status=Vazifa.BAJARILDI, done_at__date__gte=today - timedelta(days=7))
              .order_by("-done_at"))),
    ]
    given = []
    if me.can_create:
        given = list(_with_counts(Vazifa.objects.filter(created_by=me, status=Vazifa.YANGI)
                                  .exclude(assignee=me).select_related("assignee")).order_by("due_date"))
        for t in given:
            if t.due_date and t.due_date < today:
                t.late_text = _late_text(t, today)
    for _, _, items in groups:
        _flags(me, items)
        for t in items:
            t.dm = dates.day_month_short(t.due_date)
    _flags(me, given)
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
        nodate = list(mine.filter(status=Vazifa.YANGI, due_date__isnull=True).order_by("-important", "created_at"))
        done = mine.filter(status=Vazifa.BAJARILDI, done_at__date__gte=today - timedelta(days=7)).count()
        for t in late:
            t.late_text = _late_text(t, today)
            t.dm = dates.day_month_short(t.due_date)
        for t in soon:
            t.dm = dates.day_month_short(t.due_date)
        for t in nodate:
            t.dm = "—"
        if late or soon or nodate or done:
            rows.append({"p": p, "late": late, "soon": soon, "nodate": nodate, "done": done})
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
    back = request.GET.get("next") or "/"
    if not back.startswith("/") or back.startswith("//"):
        back = "/"
    partial = request.GET.get("partial") == "1"
    return render(request, "vazifalar/_task_panel.html" if partial else "vazifalar/detail.html", {
        "t": task, "events": events, "due_dm": dates.day_month(task.due_date),
        "here": back if partial else f"/vazifa/{task.pk}/?next={back}", "back": back, "partial": partial,
        "can_manage": sv.can_manage(me, task), "can_touch": sv.can_touch(me, task),
        "people": sv.assignable_people(), "companies": cfg.COMPANIES, "today_iso": dates.today().isoformat(),
    })


@login_required
@require_POST
def create(request):
    """Add window. The title line may carry the details in plain Uzbek ("ertaga @ali #git !");
    anything picked in the window itself wins over what was typed."""
    from vazifalar.quick import parse_text
    me = request.account
    raw = request.POST.get("title") or ""
    parsed = parse_text(raw)
    who = request.POST.get("kim") or parsed.who or me.username      # no @name → the task is yours
    assignee = UserAccount.objects.filter(username=who, is_active=True).first()
    due = _parse_date(request.POST.get("due")) or parsed.due     # no date → "Rejasiz"
    try:
        if assignee is None:
            raise sv.NotAllowed("Kimga ekanini tanlang.")
        sv.create_task(me, parsed.title or raw, assignee, due,
                       company=request.POST.get("company") or parsed.company or "",
                       important=bool(request.POST.get("important")) or parsed.important,
                       repeat=request.POST.get("repeat") or parsed.repeat,
                       private=bool(request.POST.get("private")) or parsed.private)
        messages.success(request, "Qo'shildi.")
    except sv.NotAllowed as e:
        messages.error(request, str(e))
    return redirect(_back(request))


MAX_BULK = 60   # CORE: lines accepted in one paste


@login_required
@require_POST
def bulk_create(request):
    """Paste many lines into the bar: each non-empty line becomes one task, parsed like a single line."""
    from vazifalar.quick import parse_text
    me = request.account
    lines = [l.strip(" -•\t") for l in (request.POST.get("lines") or "").splitlines()]
    lines = [l for l in lines if l][:MAX_BULK]
    made, failed = 0, []
    for raw in lines:
        p = parse_text(raw)
        who = UserAccount.objects.filter(username=p.who or me.username, is_active=True).first()
        try:
            sv.create_task(me, p.title or raw, who, p.due, company=p.company or "", important=p.important,
                           repeat=p.repeat, private=p.private)
            made += 1
        except sv.NotAllowed as e:
            failed.append(f"{raw[:40]}: {e}")
    if made:
        messages.success(request, f"{made} ta vazifa qo'shildi.")
    for f in failed[:5]:
        messages.error(request, f)
    return JsonResponse({"ok": True, "made": made, "failed": failed})


@login_required
def quick_preview(request):
    from vazifalar.quick import preview
    return JsonResponse(preview(request.GET.get("q") or ""))


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
    messages.success(request, "O'chirildi.")


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
def save(request, pk):
    """The edit window's Saqlash: title, person, date, company in one go."""
    who = UserAccount.objects.filter(username=request.POST.get("kim") or "", is_active=True).first()
    company = request.POST.get("company")
    sv.update_task(request.account, pk, title=request.POST.get("title"), assignee=who,
                   due_date=(None if (request.POST.get("due") or "").strip() == ""
                             else (_parse_date(request.POST.get("due")) or sv.UNSET)),
                   company=(company if company is not None else None),
                   important=bool(request.POST.get("important")),
                   private=bool(request.POST.get("private")),
                   repeat=request.POST.get("repeat", None))
    messages.success(request, "Saqlandi.")


@login_required
@require_POST
def move(request, pk: int):
    """Drag-and-drop on the board: a new date, answered in JSON (the page moves the card itself)."""
    raw = (request.POST.get("due") or "").strip()
    new_due = _parse_date(raw) if raw else None          # "" → back to Rejasiz
    try:
        if raw and new_due is None:
            raise sv.NotAllowed("Sana noto'g'ri.")
        if new_due and new_due < dates.today():
            raise sv.NotAllowed("O'tgan kunga qo'yib bo'lmaydi.")
        t = sv.change_due(request.account, pk, new_due)
    except Vazifa.DoesNotExist:
        raise Http404
    except sv.NotAllowed as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    return JsonResponse({"ok": True, "due": t.due_date.isoformat() if t.due_date else ""})


@_task_action
def comment(request, pk):
    sv.add_comment(request.account, pk, request.POST.get("text"))
