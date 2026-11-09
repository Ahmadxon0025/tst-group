# Panel (dashboard) and Bajarilgan: read-only pages that must respect Maxfiy and count correctly.
from datetime import timedelta

from django.test import Client

from core import dates
from tests.conftest import login
from vazifalar import services as sv


def test_panel_counts_and_private(client, boss, ali, vali):
    today = dates.today()
    sv.create_task(boss, "Kechikkan ish", ali, today - timedelta(days=3))
    sv.create_task(boss, "Bugungi ish", ali, today)
    sv.create_task(boss, "Rejasiz ish", vali, None)
    sv.create_task(boss, "Maxfiy ish", vali, today, private=True)
    done = sv.create_task(boss, "Bajarilgan ish", ali, today)
    sv.mark_done(ali, done.pk)

    r = login(client, boss).get("/panel/")
    assert r.status_code == 200
    tiles = {t["label"]: t["n"] for t in r.context["tiles"]}
    assert tiles["Ochiq"] == 4 and tiles["Kechikkan"] == 1 and tiles["Bugun"] == 2 and tiles["Rejasiz"] == 1
    assert tiles["Bajarildi · 7 kun"] == 1
    assert tiles["O'z vaqtida · 30 kun"] == 100
    assert "Kechikkan ish" in r.content.decode()

    r = login(Client(), ali).get("/panel/")
    tiles = {t["label"]: t["n"] for t in r.context["tiles"]}
    assert tiles["Ochiq"] == 3            # Vali's Maxfiy task is not counted for Ali


def test_bajarildi_page_groups_and_reopen_link(client, boss, ali):
    today = dates.today()
    t = sv.create_task(boss, "Hisobot", ali, today - timedelta(days=2))
    sv.mark_done(ali, t.pk)
    r = login(client, ali).get("/bajarildi/?d=30")
    body = r.content.decode()
    assert r.status_code == 200 and "Hisobot" in body and "Bugun" in body and "2 kun kech" in body
    assert r.context["ontime"] == 0
    assert client.get("/bajarildi/?d=999").context["days"] == 7


def test_board_shows_done_cards_under_day(client, boss, ali):
    today = dates.today()
    t = sv.create_task(boss, "Tugagan", ali, today)
    sv.mark_done(ali, t.pk)
    r = login(client, boss).get("/")
    assert "1 ta bajarildi" in r.content.decode() and "Tugagan" in r.content.decode()
