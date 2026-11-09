# CORE: reusable — read-only summary pages: Panel (the dashboard), Ro'yxat (drill-down) and Bajarilgan (done).
# Nothing here writes; every number is computed from the tasks this person may see (services.visible_tasks),
# and every number on the Panel links to the list of tasks behind it.
from datetime import timedelta
from urllib.parse import urlencode

from django.shortcuts import render
from django.utils import timezone

from accounts.middleware import login_required
from accounts.models import UserAccount
from config import values as cfg
from core import dates
from vazifalar import services as sv
from vazifalar.models import Vazifa, VazifaEvent
from vazifalar.views import _flags, _with_counts, category_filter, category_label

TREND_DAYS = 14                 # CORE: days shown in the done/added chart
ONTIME_WINDOW = 30              # CORE: on-time % looks at tasks done in the last N days
DONE_PERIODS = (7, 30, 90)      # CORE: choices on the Bajarilgan page
ACTIVITY_N = 15                 # CORE: lines in "So'nggi harakatlar"
REFRESH_SECONDS = 60            # CORE: the Panel reloads itself while it is on screen

BUCKETS = [("late", "Kechikkan"), ("today", "Bugun"), ("week", "Shu hafta"),
           ("later", "Keyinroq"), ("nodate", "Rejasiz")]
LIST_KINDS = dict(BUCKETS, open="Ochiq", due="Shu hafta yoki kechikkan")


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


def bucket(t, today):
    if t.due_date is None:
        return "nodate"
    if t.due_date < today:
        return "late"
    if t.due_date == today:
        return "today"
    if t.due_date <= today + timedelta(days=6):
        return "week"
    return "later"


def _split(ts, today):
    c = {k: 0 for k, _ in BUCKETS}
    for t in ts:
        c[bucket(t, today)] += 1
    return c


def _list_link(h, kim="", k="", c=""):
    return "/royxat/?" + urlencode({x: y for x, y in (("h", h), ("kim", kim), ("k", k), ("c", c)) if y})


def _done_link(kim="", k="", d=7, c=""):
    return "/bajarildi/?" + urlencode({x: y for x, y in (("d", d), ("kim", kim), ("k", k), ("c", c)) if y})


def stats(me, today, company="", category=""):
    """Everything the Panel and the Monday Telegram summary need, from what `me` may see."""
    base = sv.visible_tasks(me).exclude(status=Vazifa.BEKOR)
    if company:
        base = base.filter(company=company)
    if category:
        base = base.filter(category=category)
    open_ts = list(base.filter(status=Vazifa.YANGI))
    since = today - timedelta(days=max(TREND_DAYS, ONTIME_WINDOW) - 1)
    done_ts = list(base.filter(status=Vazifa.BAJARILDI, done_at__date__gte=since))
    wk0 = today - timedelta(days=6)                 # this 7-day window
    pw0, pw1 = today - timedelta(days=13), today - timedelta(days=7)   # the 7 days before it
    done7 = [t for t in done_ts if _done_day(t) >= wk0]
    done_prev = [t for t in done_ts if pw0 <= _done_day(t) <= pw1]
    done30 = [t for t in done_ts if _done_day(t) >= today - timedelta(days=ONTIME_WINDOW - 1)]
    created = [timezone.localtime(c).date() for c in
               base.filter(created_at__date__gte=pw0).values_list("created_at", flat=True)]
    added7 = sum(1 for d in created if d >= wk0)
    added_prev = sum(1 for d in created if d <= pw1)
    total = _split(open_ts, today)

    people = []
    for p in sv.assignable_people():
        mo = [t for t in open_ts if t.assignee_id == p.pk]
        md = [t for t in done_ts if t.assignee_id == p.pk]
        if not mo and not md:
            continue
        c = _split(mo, today)
        people.append({"p": p, "open": len(mo), "c": c, "done7": sum(1 for t in md if _done_day(t) >= wk0),
                       "ontime": _ontime([t for t in md if t in done30]),
                       "oldest": min((t.due_date for t in mo if bucket(t, today) == "late"), default=None)})
    return {"today": today, "open": open_ts, "total": total, "done7": done7, "done_prev": done_prev,
            "done30": done30, "done_ts": done_ts, "added7": added7, "added_prev": added_prev,
            "created": created, "people": people, "ontime": _ontime(done30)}


def _delta(now, before):
    d = now - before
    return {"n": abs(d), "up": d > 0, "down": d < 0}


def summary_lines(st):
    """Plain-Uzbek summary written by rules from the numbers (not AI): the same text every time for the same data."""
    lines = []
    n_done, n_prev, total = len(st["done7"]), len(st["done_prev"]), st["total"]
    if n_done or n_prev:
        more = "ko'p" if n_done > n_prev else "kam"
        trend = (f"o'tgan 7 kunda ham {n_prev} ta edi" if n_done == n_prev else
                 f"oldingi 7 kundan {abs(n_done - n_prev)} ta {more}")
        lines.append(f"So'nggi 7 kunda {n_done} ta vazifa bajarildi — {trend}.")
    else:
        lines.append("So'nggi 7 kunda bajarilgan vazifa yo'q.")
    if st["added7"] > n_done:
        lines.append(f"{st['added7']} ta yangi vazifa qo'shildi: ish bajarilishidan tezroq ko'paymoqda.")
    if total["late"]:
        worst = max(st["people"], key=lambda r: (r["c"]["late"], -(r["oldest"] or st["today"]).toordinal()))
        days = (st["today"] - worst["oldest"]).days if worst["oldest"] else 0
        lines.append(f"{total['late']} ta vazifa kechikkan; eng ko'pi {worst['p'].name}da "
                     f"({worst['c']['late']} ta, eng eskisi {days} kun).")
        by_cat = {}
        for t in st["open"]:
            if t.category and bucket(t, st["today"]) == "late":
                by_cat[t.category] = by_cat.get(t.category, 0) + 1
        if by_cat:
            k = max(by_cat, key=by_cat.get)
            lines.append(f"Eng ko'p kechikkan yo'nalish: {category_label(k)} ({by_cat[k]} ta).")
    else:
        lines.append("Kechikkan vazifa yo'q.")
    if st["ontime"] is not None:
        lines.append(f"Oxirgi 30 kunda vazifalarning {st['ontime']}% o'z vaqtida bajarildi.")
    if total["nodate"]:
        lines.append(f"{total['nodate']} ta vazifaga hali sana qo'yilmagan (Rejasiz).")
    idle = [r["p"].name for r in st["people"] if r["open"] and not r["done7"]]
    if idle:
        lines.append(f"Bu hafta hech narsa bajarmaganlar: {', '.join(idle)}.")
    return lines


def _activity(me, company, today):
    """The latest changes on tasks this person may see — ClickUp's 'Latest activity'."""
    qs = (VazifaEvent.objects.filter(vazifa__in=sv.visible_tasks(me).values("pk"))
          .select_related("actor", "vazifa", "new_assignee").order_by("-created_at", "-id"))
    if company:
        qs = qs.filter(vazifa__company=company)
    verbs = {VazifaEvent.YARATILDI: "qo'shdi", VazifaEvent.BAJARILDI: "bajardi", VazifaEvent.QAYTA_OCHILDI: "qayta ochdi",
             VazifaEvent.BEKOR: "o'chirdi", VazifaEvent.MUDDAT: "sanasini o'zgartirdi", VazifaEvent.KIMGA: "boshqaga berdi",
             VazifaEvent.NOM: "nomini o'zgartirdi", VazifaEvent.KOMPANIYA: "kompaniyasini o'zgartirdi",
             VazifaEvent.MUHIM: "muhimligini o'zgartirdi", VazifaEvent.MAXFIY: "maxfiyligini o'zgartirdi",
             VazifaEvent.TAKROR: "takrorini o'zgartirdi", VazifaEvent.IZOH: "izoh yozdi"}
    out = []
    for e in qs[:ACTIVITY_N]:
        local = timezone.localtime(e.created_at)
        d = local.date()
        when = local.strftime("%H:%M") if d == today else ("kecha" if d == today - timedelta(days=1)
                                                             else dates.day_month_short(d))
        extra = ""
        if e.kind == VazifaEvent.MUDDAT:
            extra = f"→ {dates.day_month_short(e.new_due)}"
        elif e.kind == VazifaEvent.KIMGA and e.new_assignee:
            extra = f"→ {e.new_assignee.name}"
        elif e.kind == VazifaEvent.IZOH and e.note:
            extra = f"«{e.note[:60]}{'…' if len(e.note) > 60 else ''}»"
        out.append({"e": e, "verb": verbs.get(e.kind, e.kind), "extra": extra, "when": when})
    return out


@login_required
def panel(request):
    """Dashboard: summary, totals with week-on-week change, open work by when, per person, per company,
    14-day chart, tasks due this week or late, latest activity. Every number opens its list."""
    me = request.account
    today = dates.today()
    company = _company(request)
    cat = category_filter(request)
    st = stats(me, today, company, cat)
    total, n_open = st["total"], len(st["open"])

    tiles = [
        {"label": "Ochiq", "n": n_open, "href": _list_link("open", k=company, c=cat)},
        {"label": "Kechikkan", "n": total["late"], "cls": "bad" if total["late"] else "", "href": _list_link("late", k=company, c=cat)},
        {"label": "Bugun", "n": total["today"], "href": _list_link("today", k=company, c=cat)},
        {"label": "Rejasiz", "n": total["nodate"], "href": _list_link("nodate", k=company, c=cat)},
        {"label": "Bajarildi · 7 kun", "n": len(st["done7"]), "cls": "good", "href": _done_link(k=company, c=cat),
         "delta": _delta(len(st["done7"]), len(st["done_prev"])), "good_up": True},
        {"label": "Qo'shildi · 7 kun", "n": st["added7"], "delta": _delta(st["added7"], st["added_prev"])},
        {"label": "O'z vaqtida · 30 kun", "n": st["ontime"], "pct": True, "href": _done_link(k=company, d=30, c=cat)},
    ]
    bar = [{"key": k, "label": lbl, "n": total[k], "w": (100 * total[k] / n_open) if n_open else 0,
            "href": _list_link(k, k=company, c=cat)} for k, lbl in BUCKETS]

    people = st["people"]
    biggest = max((r["open"] for r in people), default=0) or 1
    for r in people:
        u = r["p"].username
        r["segs"] = [{"key": k, "n": r["c"][k], "w": 100 * r["c"][k] / biggest} for k, _ in BUCKETS if r["c"][k]]
        r["href_open"] = _list_link("open", u, company, cat)
        r["href_late"] = _list_link("late", u, company, cat)
        r["href_today"] = _list_link("today", u, company, cat)
        r["href_done"] = _done_link(u, company, c=cat)

    companies = []
    if not company:
        for k, lbl in list(cfg.COMPANIES) + [("", "Kompaniyasiz")]:
            o = [t for t in st["open"] if t.company == k]
            d = sum(1 for t in st["done7"] if t.company == k)
            if o or d:
                companies.append({"key": k, "label": lbl, "open": len(o), "done7": d,
                                  "late": sum(1 for t in o if bucket(t, today) == "late")})

    categories = []
    if not cat:
        for k, lbl, _ in list(cfg.CATEGORIES) + [("", "Yo'nalishsiz", [])]:
            o = [t for t in st["open"] if t.category == k]
            d = sum(1 for t in st["done7"] if t.category == k)
            if o or d or k:
                categories.append({"key": k, "label": lbl, "open": len(o), "done7": d,
                                   "late": sum(1 for t in o if bucket(t, today) == "late"),
                                   "href_open": _list_link("open", k=company, c=k) if k else "",
                                   "href_late": _list_link("late", k=company, c=k) if k else "",
                                   "href": "/panel/?" + urlencode({x: y for x, y in (("k", company), ("c", k)) if y})})

    added = {}
    for d in st["created"]:
        added[d] = added.get(d, 0) + 1
    done_by = {}
    for t in st["done_ts"]:
        dd = _done_day(t)
        done_by[dd] = done_by.get(dd, 0) + 1
    trend = []
    for i in range(TREND_DAYS - 1, -1, -1):
        d = today - timedelta(days=i)
        trend.append({"dm": f"{d.day}", "wd": cfg.DAY_LONG[d.weekday()][:2], "done": done_by.get(d, 0),
                      "added": added.get(d, 0), "is_today": d == today, "is_mon": d.weekday() == 0})
    top = max([x["done"] for x in trend] + [x["added"] for x in trend] + [1])
    for x in trend:
        x["hd"] = 100 * x["done"] / top
        x["ha"] = 100 * x["added"] / top

    due = sorted((t for t in st["open"] if bucket(t, today) in ("late", "today", "week")),
                 key=lambda t: (t.due_date, not t.important))
    for t in due:
        t.dm = dates.day_month_short(t.due_date)
        t.is_late = t.due_date < today
        t.late_text = f"{(today - t.due_date).days} kun" if t.is_late else ("bugun" if t.due_date == today
                                                                          else cfg.DAY_LONG[t.due_date.weekday()])

    qs = urlencode({x: y for x, y in (("k", company), ("c", cat)) if y})
    here = "/panel/" + (f"?{qs}" if qs else "")

    def plink(**kw):
        q = {"k": company, "c": cat}
        q.update(kw)
        q = urlencode({x: y for x, y in q.items() if y})
        return "/panel/" + (f"?{q}" if q else "")
    return render(request, "vazifalar/panel.html", {
        "summary": summary_lines(st), "tiles": tiles, "bar": bar, "n_open": n_open, "people": people,
        "company_rows": companies, "category_rows": categories, "category": cat,
        "category_label": category_label(cat),
        "category_links": [{"label": "Hammasi", "href": plink(c=""), "on": not cat}] + [
            {"label": lbl, "href": plink(c=k), "on": cat == k} for k, lbl, _ in cfg.CATEGORIES], "trend": trend, "trend_done": sum(x["done"] for x in trend),
        "trend_added": sum(x["added"] for x in trend), "due": due[:12], "due_more": max(0, len(due) - 12),
        "due_href": _list_link("due", k=company, c=cat), "activity": _activity(me, company, today),
        "today_dm": dates.day_month(today), "now_hm": timezone.localtime().strftime("%H:%M"),
        "refresh": REFRESH_SECONDS, "company": company, "here": here,
        "company_label": dict(cfg.COMPANIES).get(company, ""),
        "company_links": [{"label": "Hammasi", "href": plink(k=""), "on": not company}] + [
            {"label": lbl, "href": plink(k=k), "on": company == k} for k, lbl in cfg.COMPANIES],
    })


@login_required
def royxat(request):
    """Drill-down: the tasks behind one Panel number (?h=late|today|week|later|nodate|open|due, ?kim=, ?k=)."""
    me = request.account
    today = dates.today()
    h = request.GET.get("h") or "open"
    if h not in LIST_KINDS:
        h = "open"
    company = _company(request)
    cat = category_filter(request)
    who = None
    kim = request.GET.get("kim") or ""
    if kim:
        who = UserAccount.objects.filter(username=kim, is_active=True).first()
    qs = sv.visible_tasks(me).filter(status=Vazifa.YANGI)
    if who is not None:
        qs = qs.filter(assignee=who)
    if company:
        qs = qs.filter(company=company)
    if cat:
        qs = qs.filter(category=cat)
    tasks = list(_with_counts(qs))
    if h == "due":
        tasks = [t for t in tasks if bucket(t, today) in ("late", "today", "week")]
    elif h != "open":
        tasks = [t for t in tasks if bucket(t, today) == h]
    tasks.sort(key=lambda t: (t.due_date is None, t.due_date or today, not t.important, t.created_at))
    _flags(me, tasks)
    for t in tasks:
        t.dm = dates.day_month_short(t.due_date)
        t.late = t.due_date is not None and t.due_date < today
        if t.late:
            t.late_text = f"{(today - t.due_date).days} kun kechikdi"

    def link(**kw):
        q = {"h": h, "kim": who.username if who else "", "k": company, "c": cat}
        q.update(kw)
        return "/royxat/?" + urlencode({x: y for x, y in q.items() if y})
    title = LIST_KINDS[h]
    if who:
        title += f" · {who.name}"
    if company:
        title += f" · {dict(cfg.COMPANIES)[company]}"
    if cat:
        title += f" · {category_label(cat)}"
    return render(request, "vazifalar/royxat.html", {
        "title": title, "tasks": tasks, "here": link(), "back": "/panel/?" + urlencode({x: y for x, y in (("k", company), ("c", cat)) if y}),
        "kind_links": [{"label": lbl, "href": link(h=key), "on": h == key}
                       for key, lbl in [("open", "Ochiq"), ("due", "Shu hafta yoki kechikkan")] + BUCKETS],
        "person_links": [{"label": "Hammasi", "href": link(kim=""), "on": who is None}] + [
            {"label": p.name, "href": link(kim=p.username), "on": who is not None and who.pk == p.pk}
            for p in sv.assignable_people()],
        "company_links": [{"label": "Hammasi", "href": link(k=""), "on": not company}] + [
            {"label": lbl, "href": link(k=key), "on": company == key} for key, lbl in cfg.COMPANIES],
        "category_links": [{"label": "Hammasi", "href": link(c=""), "on": not cat}] + [
            {"label": lbl, "href": link(c=key), "on": cat == key} for key, lbl, _ in cfg.CATEGORIES],
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
    cat = category_filter(request)
    who = None
    kim = request.GET.get("kim") or "all"
    if kim != "all":
        who = UserAccount.objects.filter(username=kim, is_active=True).first()

    qs = sv.visible_tasks(me).filter(status=Vazifa.BAJARILDI, done_at__date__gte=today - timedelta(days=days - 1))
    if who is not None:
        qs = qs.filter(assignee=who)
    if company:
        qs = qs.filter(company=company)
    if cat:
        qs = qs.filter(category=cat)
    tasks = _flags(me, list(_with_counts(qs).order_by("-done_at")))

    q = {"d": days, "kim": who.username if who else "all", "k": company, "c": cat}

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
        "category_links": [{"label": "Hammasi", "href": link(c=""), "on": not cat}] + [
            {"label": lbl, "href": link(c=k), "on": cat == k} for k, lbl, _ in cfg.CATEGORIES],
    })
