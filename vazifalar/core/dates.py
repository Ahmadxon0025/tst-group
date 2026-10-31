# CORE: reusable — dates from the SERVER clock in the configured timezone (LAW 6), with Uzbek wording from CONFIG.
from datetime import date, timedelta

from django.utils import timezone

from config import values as cfg


def today() -> date:  # CORE: reusable
    return timezone.localdate()


def week_monday(d: date) -> date:  # CORE: reusable
    return d - timedelta(days=d.weekday())


def day_month(d: date) -> str:  # CORE: reusable — "2-noyabr"; no date → "Sanasiz"
    if d is None:
        return "Sanasiz"
    return f"{d.day}-{cfg.MONTHS[d.month - 1]}"


def day_month_short(d: date) -> str:  # CORE: reusable — "2-noy"; no date → "sanasiz"
    if d is None:
        return "sanasiz"
    return f"{d.day}-{cfg.MONTHS_SHORT[d.month - 1]}"


def week_label(monday: date) -> str:  # CORE: reusable — "26-oktabr – 1-noyabr"
    sunday = monday + timedelta(days=6)
    return f"{day_month(monday)} – {day_month(sunday)}"


def month_label(start: date, end: date) -> str:  # CORE: reusable — "Noyabr 2026" or "Oktabr – Noyabr 2026"
    a = cfg.MONTHS[start.month - 1].capitalize()
    b = cfg.MONTHS[end.month - 1].capitalize()
    if start.month == end.month:
        return f"{a} {end.year}"
    if start.year == end.year:
        return f"{a} – {b} {end.year}"
    return f"{a} {start.year} – {b} {end.year}"
