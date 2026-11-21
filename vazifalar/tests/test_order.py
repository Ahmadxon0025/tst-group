# Hand-set order inside a day: a card dropped between two others stays there.
from datetime import timedelta

import pytest

from audit.models import AuditLog
from core import dates
from tests.conftest import login
from vazifalar import services as sv
from vazifalar.models import Vazifa


def titles(client, day):
    r = client.get("/")
    col = next(d for d in r.context["days"] if d["iso"] == day.isoformat())
    return [t.title for t in col["tasks"]]


def test_drop_between_two_cards_stays_there(client, boss, ali):
    today = dates.today()
    a = sv.create_task(boss, "A", ali, today)
    b = sv.create_task(boss, "B", ali, today, important=True)     # Muhim no longer jumps to the top
    c = sv.create_task(boss, "C", ali, today)
    login(client, boss)
    assert titles(client, today) == ["A", "B", "C"]
    r = client.post(f"/vazifa/{c.pk}/kunga/", {"due": today.isoformat(), "after": a.pk, "before": b.pk})
    assert r.json()["ok"] and titles(client, today) == ["A", "C", "B"]
    client.post(f"/vazifa/{b.pk}/kunga/", {"due": today.isoformat(), "after": "", "before": a.pk})    # to the top
    assert titles(client, today) == ["B", "A", "C"]
    client.post(f"/vazifa/{b.pk}/kunga/", {"due": today.isoformat(), "after": c.pk, "before": ""})    # to the bottom
    assert titles(client, today) == ["A", "C", "B"]
    assert AuditLog.objects.filter(action="vazifa_tartib").count() == 3


def test_drop_on_another_day_between_cards(client, boss, ali):
    today, tomorrow = dates.today(), dates.today() + timedelta(days=1)
    x = sv.create_task(boss, "X", ali, tomorrow)
    y = sv.create_task(boss, "Y", ali, tomorrow)
    m = sv.create_task(boss, "M", ali, today)
    login(client, boss)
    r = client.post(f"/vazifa/{m.pk}/kunga/", {"due": tomorrow.isoformat(), "after": x.pk, "before": y.pk})
    assert r.json() == {"ok": True, "due": tomorrow.isoformat()}
    assert titles(client, tomorrow) == ["X", "M", "Y"]
    client.post(f"/vazifa/{m.pk}/kunga/", {"due": "", "after": "", "before": ""})                     # back to Rejasiz
    assert [t.title for t in client.get("/").context["inbox"]] == ["M"]


def test_doer_may_reorder_but_not_change_the_date(client, boss, ali):
    today = dates.today()
    a = sv.create_task(boss, "A", ali, today)
    b = sv.create_task(boss, "B", ali, today)
    sv.place(ali, b.pk, today, None, a.pk)                        # his own tasks: order is his to set
    b.refresh_from_db(); a.refresh_from_db()
    assert b.position < a.position
    with pytest.raises(sv.NotAllowed):
        sv.place(ali, b.pk, today + timedelta(days=1), None, None)
    r = login(client, boss).post(f"/vazifa/{a.pk}/kunga/", {"due": today.isoformat(), "after": "abc"})
    assert r.status_code == 400
