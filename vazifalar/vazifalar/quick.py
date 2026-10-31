# CORE: reusable — quick add glue: who and which companies the parser may recognise, and a preview for the screen.
from config import values as cfg
from core import dates
from core.quickadd import parse
from core.translit import to_cyrillic
from vazifalar import services as sv


def handles():  # CORE: reusable — "@abdurazzoq", "@fayzullo_oka", "@fayzullooka", "@абдураззоқ" …
    """Login names always work. A first name works only when no one else shares it (two "Fayzullo" → use
    @fayzullo or @fayzullo_oka)."""
    people_list = list(sv.assignable_people())
    first_count = {}
    for p in people_list:
        first = p.name.split()[0].lower()
        first_count[first] = first_count.get(first, 0) + 1
    people = {}

    def add(handle, username):
        handle = handle.lower()
        people[handle] = username
        people[to_cyrillic(handle).lower()] = username
    for p in people_list:                          # weakest first, so stronger ones overwrite
        first = p.name.split()[0].lower()
        if first_count[first] == 1:
            add(first, p.username)
        add(p.name.replace(" ", ""), p.username)
    for p in people_list:
        add(p.username.replace("_", ""), p.username)
        add(p.username, p.username)
    companies = {}
    for k, label in cfg.COMPANIES:
        for h in (k, label.lower(), to_cyrillic(label).lower()):
            companies[h] = k
    return people, companies


def parse_text(text: str):  # CORE: reusable
    people, companies = handles()
    return parse(text, dates.today(), people, companies)


def preview(text: str) -> dict:  # CORE: reusable — what the add window shows while typing
    p = parse_text(text)
    names = {u.username: u.name for u in sv.assignable_people()}
    from vazifalar.models import Vazifa
    rep = Vazifa(repeat=p.repeat).repeat_label if p.repeat else ""
    return {
        "title": p.title, "due": p.due.isoformat() if p.due else "", "due_label": dates.day_month(p.due) if p.due else "",
        "who": p.who or "", "who_name": names.get(p.who, ""), "company": p.company or "",
        "company_label": dict(cfg.COMPANIES).get(p.company, ""), "important": p.important, "private": p.private,
        "repeat": p.repeat, "repeat_label": rep,
    }
