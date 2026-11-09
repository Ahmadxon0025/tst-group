# Yo'nalish (area of work): one per task, set by "/bank" in quick add, the add window or the edit window.
from datetime import date, timedelta

import pytest
from django.test import Client

from audit.models import AuditLog
from bot import api, handlers
from core import dates
from core.quickadd import parse
from tests.conftest import login
from vazifalar import services as sv
from vazifalar.models import Vazifa, VazifaEvent
from vazifalar.quick import category_handles

D = date(2026, 11, 9)


def test_parser_reads_category_latin_cyrillic_and_alias():
    cats = category_handles()
    p = parse("Qaror daraxti juma /bank #guruh !", D, {}, {"guruh": "guruh"}, cats)
    assert (p.title, p.category, p.company, p.important) == ("Qaror daraxti", "bank", "guruh", True)
    assert parse("Солиқ хати /ҳуқуқ", D, {}, {}, cats).category == "huquq"
    assert parse("Elektroset to'lovi /qarz", D, {}, {}, cats).category == "moliya"
    assert parse("Bo'z qoldig'i /ta'minot", D, {}, {}, cats).category == "taminot"
    p = parse("Yo'l /noma'lum", D, {}, {}, cats)            # unknown word stays in the title
    assert p.category is None and p.title == "Yo'l /noma'lum"


def test_category_change_is_logged_and_guarded(boss, ali, vali):
    t = sv.create_task(ali, "NBU xati", vali, D, category="bank")
    assert t.category == "bank" and t.category_label == "Bank"
    sv.update_task(ali, t.pk, category="huquq")
    t.refresh_from_db()
    assert t.category == "huquq"
    ev = t.events.filter(kind=VazifaEvent.YONALISH).get()
    assert ev.note == "Huquq va davlat"
    assert AuditLog.objects.filter(action="vazifa_yonalish").exists()
    with pytest.raises(sv.NotAllowed):
        sv.set_category(vali, t.pk, "bank")                 # the doer cannot re-file it
    with pytest.raises(sv.NotAllowed):
        sv.create_task(ali, "x", vali, D, category="yoq")   # only the 8 from CONFIG


def test_repeat_keeps_category(boss, ali):
    t = sv.create_task(boss, "Kassa", ali, dates.today(), repeat="daily", category="moliya")
    sv.mark_done(ali, t.pk)
    nxt = Vazifa.objects.get(repeat_of=t)
    assert nxt.category == "moliya"


def test_web_quick_add_and_filters(client, boss, ali):
    login(client, boss)
    client.post("/vazifa/yangi/", {"title": "Bank paketi bugun @ali /bank", "next": "/"})
    client.post("/vazifa/yangi/", {"title": "Smena jurnali bugun @ali", "category": "ishlab", "next": "/"})
    assert set(Vazifa.objects.values_list("category", flat=True)) == {"bank", "ishlab"}
    body = client.get("/?c=bank").content.decode()
    assert "Bank paketi" in body and "Smena jurnali" not in body
    assert [t.title for t in client.get("/royxat/?h=open&c=ishlab").context["tasks"]] == ["Smena jurnali"]
    r = client.get("/panel/")
    rows = {c["key"]: c["open"] for c in r.context["category_rows"]}
    assert rows["bank"] == 1 and rows["ishlab"] == 1 and rows["savdo"] == 0
    assert {t["label"]: t["n"] for t in client.get("/panel/?c=bank").context["tiles"]}["Ochiq"] == 1
    assert client.get("/vazifa/tahlil/?q=x+/savdo").json()["category_label"] == "Savdo"


def test_summary_names_worst_category(client, boss, ali):
    sv.create_task(boss, "Sud xati", ali, dates.today() - timedelta(days=2), category="huquq")
    r = login(client, boss).get("/panel/")
    assert "Eng ko'p kechikkan yo'nalish: Huquq va davlat (1 ta)." in r.context["summary"]


def test_telegram_message_starting_with_category_is_a_task(monkeypatch, boss):
    monkeypatch.setattr(api, "call", lambda method, **p: {"ok": True})
    boss.telegram_user_id = 999
    boss.save()
    handlers.handle_update({"update_id": 1, "message": {"chat": {"id": 999, "type": "private"}, "from": {"id": 999},
                                                        "text": "/bank NBU xati ertaga"}})
    handlers.handle_update({"update_id": 2, "callback_query": {"id": "q", "from": {"id": 999}, "data": "qa:y",
                                                               "message": {"chat": {"id": 999}}}})
    t = Vazifa.objects.get()
    assert (t.title, t.category) == ("NBU xati", "bank")


def test_accounting_words_go_to_moliya():
    cats = category_handles()
    for w in ("/buxgalteriya", "/hisob", "/sverka", "/бухгалтерия"):
        assert parse(f"Akt sverka {w}", D, {}, {}, cats).category == "moliya", w
