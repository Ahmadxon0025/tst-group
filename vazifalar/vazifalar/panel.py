# CORE: reusable — read-only summary pages: Panel (the dashboard) and Bajarilgan (done tasks).
# Nothing here writes; counts are computed from the tasks this person may see (services.visible_tasks).
from datetime import timedelta
from urllib.parse import urlencode

from django.shortcuts import render
from django.utils import timezone

from accounts.middleware import login_required
from accounts.models import UserAccount
from config import values as cfg
from core import dates
from vazifalar import services as sv
from vazifalar.models import Vazifa
from vazifalar.views import _flags, _with_counts

TREND_DAYS = 14                 # CORE: days shown in the done/added chart
ONTIME_WINDOW = 30              # CORE: on-time % looks at tasks done in the last N days
DONE_PERIODS = (7, 30, 90)      # CORE: choices on the Bajarilgan page


def _done_day(t):
    return timezone.localtime(t.done_at).date() if t.done_at else None


def _ontime(tasks):
    """Share of done tasks (with a date) finished on or before their date. None when there is nothing to judge."""
    judged = [t for t in tasks if t.due_date and t.done_at]
    if not judged:
        return None
    ok = sum(1 for t in judged if _done_day(t) <= t.due_date)
    return round(100 * ok / len(judged))


def _company(request):
    k = request.GET.get("k") or ""
    return k if k in dict(cfg.COMPANIES) else ""


@login_required
def panel(request):
    """Dashboard: totals, open work split by when it is due, per person, per company, a 14-day chart, oldest late."""
    me = request.account
    today = dates.today()
    company = _company(request)
    base = sv.visible_tasks(me).exclude(status=Vazifa.BEKOR)
    if company:
        base = base.filter(company=company)

    open_ts = list(base.filter(status=Vazifa.YANGI))
    since = today - timedelta(days=max(TREND_DAYS, ONTIME_WINDOW) - 1)
    done_ts = list(base.filter(status=Vazifa.BAJARILDI, done_at__date__gte=since))
    week_end = today + timedelta(days=6)

    def bucket(t):
        if t.due_date is None:
            return "nodate"
        if t.due_date < today:
            return "late"
        if t.due_date == today:
            return "today"
        if t.due_date <= week_end:
            return "week"
        return "later"

    BUCKETS = [("late", "Kechikkan"), ("today", "Bugun"), ("week", "Shu hafta"),
               ("later", "Keyinroq"), ("nodate", "Rejasiz")]

    def split(ts):
        c = {k: 0 for k, _ in BUCKETS}
        for t in ts:
            c[bucket(t)] += 1
        return c

    done7 = [t for t in done_ts if _done_day(t) >= today - timedelta(days=6)]
    done30 = [t for t in done_ts if _done_day(t) >= today - timedelta(days=ONTIME_WINDOW - 1)]
    added7 = base.filter(created_at__date__gte=today - timedelta(days=6)).count()
    total = split(open_ts)
    n_open = len(open_ts)

    tiles = [
        {"label": "Ochiq", "n": n_open, "cls": ""},
        {"label": "Kechikkan", "n": total["late"], "cls": "bad" if total["late"] else ""},
        {"label": "Bugun", "n": total["today"], "cls": ""},
        {"label": "Rejasiz", "n": total["nodate"], "cls": ""},
        {"label": "Bajarildi · 7 kun", "n": len(done7), "cls": "good", "sub": f"{added7} ta qo'shildi"},
        {"label": "O'z vaqtida · 30 kun", "n": _ontime(done30), "pct": True, "cls": ""},
    ]
    bar = [{"key": k, "label": lbl, "n": total[k], "w": (100 * total[k] / n_open) if n_open else 0}
           for k, lbl in BUCKETS]

    # per person
    people = []
    for p in sv.assignable_people():
        mine_open = [t for t in open_ts if t.assignee_id == p.pk]
        mine_done = [t for t in done_ts if t.assignee_id == p.pk]
        d7 = sum(1 for t in mine_done if _done_day(t) >= today - timedelta(days=6))
        if not mine_open and not mine_done:
            continue
        c = split(mine_open)
        people.append({"p": p, "open": len(mine_open), "c": c, "done7": d7,
                       "ontime": _ontime([t for t in mine_done if _done_day(t) >= today - timedelta(days=ONTIME_WINDOW - 1)]),
                       "segs": [{"key": k, "n": c[k]} for k, _ in BUCKETS if c[k]]})
    biggest = max((r["open"] for r in people), default=0) or 1
    for r in people:
        for s in r["segs"]:
            s["w"] = 100 * s["n"] / biggest

    # per company (only when not already filtered to one)
    companies = []
    if not company:
        for k, lbl in list(cfg.COMPANIES) + [("", "Kompaniyasiz")]:
            o = [t for t in open_ts if t.company == k]
            d = sum(1 for t in done7 if t.company == k)
            if o or d:
                companies.append({"key": k, "label": lbl, "open": len(o),
                                  "late": sum(1 for t in o if bucket(t) == "late"), "done7": d})

    # 14-day chart: done per day vs added per day
    added = {}
    for t in base.filter(created_at__date__gte=today - timedelta(days=TREND_DAYS - 1)).select_related(None).only("created_at"):
        dd = timezone.localtime(t.created_at).date()
        added[dd] = added.get(dd, 0) + 1
    done_by = {}
    for t in done_ts:
        dd = _done_day(t)
        done_by[dd] = done_by.get(dd, 0) + 1
    trend = []
    for i in range(TREND_DAYS - 1, -1, -1):
        d = today - timedelta(days=i)
        trend.append({"d": d, "dm": f"{d.day}", "wd": cfg.DAY_LONG[d.weekday()][:2], "done": done_by.get(d, 0),
                      "added": added.get(d, 0), "is_today": d == today, "is_mon": d.weekday() == 0})
    top = max([x["done"] for x in trend] + [x["added"] for x in trend] + [1])
    for x in trend:
        x["hd"] = 100 * x["done"] / top
        x["ha"] = 100 * x["added"] / top
    trend_done = sum(x["done"] for x in trend)
    trend_added = sum(x["added"] for x in trend)

    oldest = sorted((t for t in open_ts if bucket(t) == "late"), key=lambda t: (t.due_date, -t.important))[:8]
    for t in oldest:
        t.dm = dates.day_month_short(t.due_date)
        t.late_text = f"{(today - t.due_date).days} kun"

    here = "/panel/" + (f"?k={company}" if company else "")
    return render(request, "vazifalar/panel.html", {
        "tiles": tiles, "bar": bar, "n_open": n_open, "people": people, "company_rows": companies,
        "trend": trend, "trend_done": trend_done, "trend_added": trend_added, "oldest": oldest,
        "today_dm": dates.day_month(today), "company": company, "here": here,
        "company_label": dict(cfg.COMPANIES).get(company, ""),
        "company_links": [{"label": "Hammasi", "href": "/panel/", "on": not company}] + [
            {"label": lbl, "href": f"/panel/?k={k}", "on": company == k} for k, lbl in cfg.COMPANIES],
    })


@login_required
def bajarildi(request):
    """Done tasks, newest first, grouped by the day they were done. Filters: person, company, period."""
    me = request.account
    today = dates.today()
    try:
        days = int(request.GET.get("d") or 7)
    except ValueError:
        days = 7
    if days not in DONE_PERIODS:
        days = 7
    company = _company(request)
    who = None
    kim = request.GET.get("kim") or "all"
    if kim != "all":
        who = UserAccount.objects.filter(username=kim, is_active=True).first()

    qs = sv.visible_tasks(me).filter(status=Vazifa.BAJARILDI, done_at__date__gte=today - timedelta(days=days - 1))
    if who is not None:
        qs = qs.filter(assignee=who)
    if company:
        qs = qs.filter(company=company)
    tasks = _flags(me, list(_with_counts(qs).order_by("-done_at")))

    q = {"d": days, "kim": who.username if who else "all", "k": company}

    def link(**kw):
        return "/bajarildi/?" + urlencode({k: v for k, v in dict(q, **kw).items() if v not in ("", None)})
    here = link()

    groups, cur = [], None
    for t in tasks:
        dd = _done_day(t)
        if cur is None or cur["d"] != dd:
            if dd == today:
                label = "Bugun"
            elif dd == today - timedelta(days=1):
                label = "Kecha"
            else:
                label = f"{dates.day_month(dd)} · {cfg.DAY_LONG[dd.weekday()]}"
            cur = {"d": dd, "label": label, "items": []}
            groups.append(cur)
        t.dm = dates.day_month_short(t.due_date)
        if t.due_date and dd > t.due_date:
            t.late_text = f"{(dd - t.due_date).days} kun kech"
        else:
            t.late_text = ""
        cur["items"].append(t)

    return render(request, "vazifalar/bajarildi.html", {
        "groups": groups, "n": len(tasks), "ontime": _ontime(tasks), "days": days, "here": here, "who": who,
        "period_links": [{"label": f"{n} kun", "href": link(d=n), "on": days == n} for n in DONE_PERIODS],
        "person_links": [{"label": "Hammasi", "href": link(kim="all"), "on": who is None}] + [
            {"label": p.name, "color": p.color, "initial": p.initial, "href": link(kim=p.username),
             "on": who is not None and who.pk == p.pk} for p in sv.assignable_people()],
        "company_links": [{"label": "Hammasi", "href": link(k=""), "on": not company}] + [
            {"label": lbl, "href": link(k=k), "on": company == k} for k, lbl in cfg.COMPANIES],
    })
