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


def test_every_number_opens_its_list_and_respects_private(client, boss, ali, vali):
    today = dates.today()
    sv.create_task(boss, "Ali kechikkan", ali, today - timedelta(days=1))
    sv.create_task(boss, "Vali maxfiy kechikkan", vali, today - timedelta(days=2), private=True)
    sv.create_task(boss, "Kelasi oy", ali, today + timedelta(days=20))
    r = login(client, boss).get("/royxat/?h=late")
    titles = [t.title for t in r.context["tasks"]]
    assert titles == ["Vali maxfiy kechikkan", "Ali kechikkan"]
    assert [t.title for t in client.get("/royxat/?h=later").context["tasks"]] == ["Kelasi oy"]
    assert [t.title for t in client.get("/royxat/?h=late&kim=ali").context["tasks"]] == ["Ali kechikkan"]
    r2 = login(Client(), ali).get("/royxat/?h=late")
    assert [t.title for t in r2.context["tasks"]] == ["Ali kechikkan"]
    assert client.get("/royxat/?h=bogus").context["title"] == "Ochiq"


def test_summary_and_activity(client, boss, ali, vali):
    today = dates.today()
    t = sv.create_task(boss, "Hisobot", ali, today - timedelta(days=4))
    sv.create_task(boss, "Sir", vali, today, private=True)
    r = login(Client(), ali).get("/panel/")
    text = " ".join(r.context["summary"])
    assert "1 ta vazifa kechikkan; eng ko'pi Alida (1 ta, eng eskisi 4 kun)" in text
    assert "Bu hafta hech narsa bajarmaganlar: Ali." in text
    assert [a["e"].vazifa.title for a in r.context["activity"]] == ["Hisobot"]     # Vali's Maxfiy stays hidden
    sv.mark_done(ali, t.pk)
    r = login(client, boss).get("/panel/")
    assert "So'nggi 7 kunda 1 ta vazifa bajarildi" in r.context["summary"][0]
    assert r.context["activity"][0]["verb"] == "bajardi"
