"""
core/quickadd.py — one line of plain Uzbek → a task's parts (Todoist-style quick add).
# CORE: reusable — words are CONFIG-free Uzbek (Latin + Cyrillic); people and companies are passed in.

    "NBU ma'lumotnoma ertaga @abdurazzoq #guruh !"   → title, due=tomorrow, who=abdurazzoq, company=guruh, important
    "Shtab hisoboti har dushanba @fayzullo"          → repeats weekly on Monday, first due = next Monday

Understood: bugun · ertaga · indinga · weekday names · "3 kundan keyin" / "3 kun" · "5-noyabr" / "5 noyabr" ·
"05.11" · "/bank" (area of work) · "har kuni" · "har hafta" · "har <weekday>" · "har oy" · "har oy 5" · "!" / "muhim" · @person · #company.
Whatever is not understood stays in the title.
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

WEEKDAYS = {  # Latin and Cyrillic → Monday=0
    "dushanba": 0, "seshanba": 1, "chorshanba": 2, "payshanba": 3, "juma": 4, "shanba": 5, "yakshanba": 6,
    "душанба": 0, "сешанба": 1, "чоршанба": 2, "пайшанба": 3, "жума": 4, "шанба": 5, "якшанба": 6,
}
MONTHS = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6, "iyul": 7, "avgust": 8,
    "sentabr": 9, "sentyabr": 9, "oktabr": 10, "oktyabr": 10, "noyabr": 11, "dekabr": 12,
    "yan": 1, "fev": 2, "mar": 3, "apr": 4, "iyn": 6, "iyl": 7, "avg": 8, "sen": 9, "okt": 10, "noy": 11, "dek": 12,
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6, "июль": 7, "август": 8,
    "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}
TODAY = {"bugun", "бугун"}
TOMORROW = {"ertaga", "эртага"}
AFTER_TOMORROW = {"indinga", "индинга"}
EVERY = {"har", "ҳар", "хар"}
DAY_WORDS = {"kuni", "кун", "куни", "kun"}
WEEK_WORDS = {"hafta", "ҳафта", "хафта"}
MONTH_WORDS = {"oy", "ой", "oyning", "ойнинг"}
IMPORTANT = {"!", "!!", "muhim", "муҳим", "мухим"}
PRIVATE = {"maxfiy", "махфий", "🔒"}
AFTER = re.compile(r"^(\d{1,3})$")
DAYS_LATER = {"kundan", "кундан"}
LATER = {"keyin", "кейин", "so'ng", "сўнг"}


@dataclass
class Parsed:  # CORE: reusable
    title: str = ""
    due: date | None = None
    who: str | None = None          # username
    company: str | None = None      # company key
    category: str | None = None     # area-of-work key ("/bank")
    important: bool = False
    private: bool = False
    repeat: str = ""                # "" | "daily" | "weekly" | "weekly:<0-6>" | "monthly" | "monthly:<1-31>"
    found: list = field(default_factory=list)   # what was understood, for the preview


def _norm(w: str) -> str:
    return w.lower().replace("ʻ", "'").replace("‘", "'").replace("’", "'").replace("`", "'").strip(".,;:")


def next_weekday(today: date, wd: int) -> date:  # CORE: reusable — the next such day, never today
    return today + timedelta(days=(wd - today.weekday() - 1) % 7 + 1)


def _month_day(today: date, day: int, month: int) -> date | None:
    for year in (today.year, today.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        if d >= today:
            return d
    return None


def next_repeat(rule: str, after: date, today: date) -> date | None:  # CORE: reusable
    """The next due date of a repeating task after `after`, never before today (a late close rolls forward)."""
    if not rule:
        return None
    kind, _, arg = rule.partition(":")
    d = after
    for _ in range(400):
        if kind == "daily":
            d = d + timedelta(days=1)
        elif kind == "weekly":
            d = next_weekday(d, int(arg)) if arg else d + timedelta(days=7)
        elif kind == "monthly":
            day = int(arg) if arg else after.day
            y, m = (d.year + (d.month // 12), d.month % 12 + 1)
            last = (date(y + (m // 12), m % 12 + 1, 1) - timedelta(days=1)).day
            d = date(y, m, min(day, last))
        else:
            return None
        if d >= today:
            return d
    return None


def parse(text: str, today: date, people: dict, companies: dict, categories: dict | None = None) -> Parsed:  # CORE: reusable
    """people: {lowercase handle: username} (usernames and first names); companies / categories: {lowercase: key}."""
    categories = categories or {}
    words = (text or "").split()
    keep = [True] * len(words)
    p = Parsed()
    norm = [_norm(w) for w in words]
    i = 0
    while i < len(words):
        if not keep[i]:              # already used as part of an earlier phrase ("har dushanba")
            i += 1
            continue
        w, n = words[i], norm[i]
        nxt = norm[i + 1] if i + 1 < len(words) else ""
        nxt2 = norm[i + 2] if i + 2 < len(words) else ""

        def eat(k, label):
            for j in range(i, i + k):
                keep[j] = False
            p.found.append(label)

        if w.startswith("@") and len(w) > 1:
            u = people.get(_norm(w[1:]))
            if u:
                p.who = u
                eat(1, "who")
        elif w.startswith("#") and len(w) > 1:
            c = companies.get(_norm(w[1:]))
            if c:
                p.company = c
                eat(1, "company")
        elif w.startswith("/") and len(w) > 1 and categories.get(_norm(w[1:])):
            p.category = categories[_norm(w[1:])]
            eat(1, "category")
        elif n in IMPORTANT:
            p.important = True
            eat(1, "important")
        elif n in PRIVATE:
            p.private = True
            eat(1, "private")
        elif n in EVERY and nxt:
            if nxt in DAY_WORDS:
                p.repeat = "daily"
                p.due = p.due or today
                eat(2, "repeat")
            elif nxt in WEEK_WORDS:
                p.repeat = "weekly"
                p.due = p.due or today
                eat(2, "repeat")
            elif nxt in WEEKDAYS:
                p.repeat = f"weekly:{WEEKDAYS[nxt]}"
                p.due = p.due or (today if today.weekday() == WEEKDAYS[nxt] else next_weekday(today, WEEKDAYS[nxt]))
                eat(2, "repeat")
            elif nxt in MONTH_WORDS:
                if nxt2.isdigit() and 1 <= int(nxt2) <= 31:
                    day = int(nxt2)
                    p.repeat = f"monthly:{day}"
                    first = _month_day(today, day, today.month) if day >= today.day else None
                    p.due = p.due or first or next_repeat(f"monthly:{day}", today, today)
                    eat(3, "repeat")
                else:
                    p.repeat = "monthly"
                    p.due = p.due or today
                    eat(2, "repeat")
        elif n in TODAY:
            p.due = today
            eat(1, "due")
        elif n in TOMORROW:
            p.due = today + timedelta(days=1)
            eat(1, "due")
        elif n in AFTER_TOMORROW:
            p.due = today + timedelta(days=2)
            eat(1, "due")
        elif n in WEEKDAYS:
            p.due = next_weekday(today, WEEKDAYS[n])
            eat(1, "due")
        elif AFTER.match(n) and (nxt in DAYS_LATER or (nxt in DAY_WORDS and nxt2 in LATER)):
            p.due = today + timedelta(days=int(n))
            eat(3 if nxt2 in LATER else 2, "due")
        elif re.match(r"^\d{1,2}[-]?[^\d\W]+$", n) and re.sub(r"^\d{1,2}-?", "", n) in MONTHS:
            day = int(re.match(r"^(\d{1,2})", n).group(1))
            d = _month_day(today, day, MONTHS[re.sub(r"^\d{1,2}-?", "", n)])
            if d:
                p.due = d
                eat(1, "due")
        elif n.isdigit() and 1 <= int(n) <= 31 and nxt in MONTHS:
            d = _month_day(today, int(n), MONTHS[nxt])
            if d:
                p.due = d
                eat(2, "due")
        elif re.match(r"^\d{1,2}\.\d{1,2}(\.\d{2,4})?$", n):
            parts = [int(x) for x in n.split(".")]
            try:
                if len(parts) == 3:
                    y = parts[2] + (2000 if parts[2] < 100 else 0)
                    d = date(y, parts[1], parts[0])
                else:
                    d = _month_day(today, parts[0], parts[1])
            except ValueError:
                d = None
            if d:
                p.due = d
                eat(1, "due")
        i += 1
    p.title = " ".join(w for w, k in zip(words, keep) if k).strip(" -—,")
    return p
