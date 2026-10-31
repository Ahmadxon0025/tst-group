# Bot guard tests. Telegram is faked: every API call is recorded, nothing leaves the machine.
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from bot import api, handlers, schedule, sender
from bot.handlers import code_hash
from bot.models import LinkCode, Outbox
from vazifalar import services as sv
from vazifalar.models import Vazifa

TZ = ZoneInfo("Asia/Tashkent")


@pytest.fixture
def tg(monkeypatch):
    calls = []

    def fake(method, **payload):
        calls.append((method, payload))
        return {"ok": True}
    monkeypatch.setattr(api, "call", fake)
    return calls


def linked(user, tg_id):
    user.telegram_user_id = tg_id
    user.save()
    return user


def msg(tg_id, text, chat_type="private"):
    return {"update_id": 1, "message": {"chat": {"id": tg_id, "type": chat_type}, "from": {"id": tg_id}, "text": text}}


def cb(tg_id, data):
    return {"update_id": 2, "callback_query": {"id": "q", "from": {"id": tg_id}, "data": data,
                                                "message": {"chat": {"id": tg_id}}}}


def test_link_code_is_one_time_and_expires(tg, ali):
    LinkCode.objects.create(user=ali, code_hash=code_hash("abc"), expires_at=timezone.now() + timedelta(minutes=5))
    LinkCode.objects.create(user=ali, code_hash=code_hash("old"), expires_at=timezone.now() - timedelta(minutes=1))
    handlers.handle_update(msg(111, "/start old"))
    ali.refresh_from_db()
    assert ali.telegram_user_id is None
    handlers.handle_update(msg(111, "/start abc"))
    ali.refresh_from_db()
    assert ali.telegram_user_id == 111
    handlers.handle_update(msg(222, "/start abc"))     # reused code → refused
    ali.refresh_from_db()
    assert ali.telegram_user_id == 111


def test_assigned_message_queued_only_for_linked(tg, boss, ali, vali):
    linked(ali, 111)
    sv.create_task(boss, "Akt sverka", ali, date(2026, 11, 2))
    sv.create_task(boss, "Boshqa", vali, date(2026, 11, 2))     # vali not linked → nothing
    rows = list(Outbox.objects.all())
    assert len(rows) == 1 and rows[0].chat_id == 111 and "Akt sverka" in rows[0].text
    assert rows[0].markup["inline_keyboard"][0][0]["callback_data"].startswith("d:")


def test_message_in_persons_script(tg, boss, ali):
    linked(ali, 111)
    ali.script = "cyrl"
    ali.save()
    sv.create_task(boss, "Akt sverka", ali, date(2026, 11, 2))
    assert "Акт сверка" in Outbox.objects.get().text


def test_no_message_to_yourself(tg, boss):
    linked(boss, 999)
    sv.create_task(boss, "O'zimga", boss, date(2026, 11, 2))
    assert Outbox.objects.count() == 0


def test_sender_sends_once_and_retries_on_failure(tg, monkeypatch, boss, ali):
    linked(ali, 111)
    sv.create_task(boss, "x", ali, date(2026, 11, 2))
    def boom(method, **p):
        raise api.SendError("HTTP 502")
    monkeypatch.setattr(api, "call", boom)
    assert sender.flush() == 0
    row = Outbox.objects.get()
    assert row.sent_at is None and row.attempts == 1
    monkeypatch.setattr(api, "call", lambda m, **p: {"ok": True})
    assert sender.flush() == 1
    assert sender.flush() == 0                   # never twice


def test_done_button_from_telegram(tg, boss, ali):
    linked(ali, 111)
    linked(boss, 999)
    t = sv.create_task(boss, "x", ali, date(2026, 11, 2))
    handlers.handle_update(cb(111, f"d:{t.pk}"))
    t.refresh_from_db()
    assert t.is_done and t.events.last().source == "telegram"
    assert Outbox.objects.filter(chat_id=999, text__contains="Bajarildi").exists()   # giver told


def test_stranger_cannot_press_done(tg, boss, ali, vali):
    linked(vali, 333)
    t = sv.create_task(boss, "x", ali, date(2026, 11, 2))
    handlers.handle_update(cb(333, f"d:{t.pk}"))
    handlers.handle_update(cb(444, f"d:{t.pk}"))   # not linked at all
    t.refresh_from_db()
    assert t.is_open


def test_comment_flow(tg, boss, ali):
    linked(ali, 111)
    linked(boss, 999)
    t = sv.create_task(boss, "x", ali, date(2026, 11, 2))
    handlers.handle_update(cb(111, f"c:{t.pk}"))
    handlers.handle_update(msg(111, "Ertaga beradi"))
    ev = t.events.last()
    assert ev.kind == "izoh" and ev.note == "Ertaga beradi" and ev.source == "telegram"
    assert Outbox.objects.filter(chat_id=999, text__contains="Ertaga beradi").exists()


def test_new_task_from_telegram(tg, boss, ali):
    linked(ali, 111)                 # a manager creates
    linked(boss, 999)
    handlers.handle_update(msg(111, "/yangi"))
    handlers.handle_update(msg(111, "Bank ma'lumotnomasi"))
    handlers.handle_update(cb(111, f"nw:{boss.username}"))
    handlers.handle_update(cb(111, "nd:1"))
    handlers.handle_update(cb(111, "nc:git"))
    t = Vazifa.objects.get()
    assert t.title == "Bank ma'lumotnomasi" and t.assignee == boss and t.company == "git"
    assert t.created_by == ali and t.due_date == timezone.localdate() + timedelta(days=1)


def test_groups_are_ignored(tg, ali):
    linked(ali, 111)
    handlers.handle_update(msg(111, "/bugun", chat_type="group"))
    assert tg == []


def _at(d, hh, mm):
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=TZ)


def test_morning_list_once_and_only_in_window(tg, boss, ali):
    linked(ali, 111)
    today = timezone.localdate()
    sv.create_task(boss, "Bugungi", ali, today)
    sv.create_task(boss, "Eski", ali, today - timedelta(days=2))
    Outbox.objects.all().update(sent_at=timezone.now())   # ignore the "assigned" messages
    before = Outbox.objects.count()
    schedule.tick(_at(today, 7, 59))
    assert Outbox.objects.count() == before
    schedule.tick(_at(today, 8, 1))
    schedule.tick(_at(today, 8, 30))
    morning = Outbox.objects.filter(key__startswith="morning:")
    assert morning.count() == 1 and "Bugungi" in morning.get().text and "Eski" in morning.get().text
    schedule.tick(_at(today, 15, 0))                       # restart at 15:00 sends nothing late
    assert Outbox.objects.filter(key__startswith="morning:").count() == 1


def test_evening_reminder_and_next_day_escalation(tg, boss, ali):
    linked(ali, 111)
    linked(boss, 999)
    today = timezone.localdate()
    t = sv.create_task(boss, "Muddati bugun", ali, today)
    schedule.tick(_at(today, 18, 5))
    assert Outbox.objects.filter(key=f"evening:{t.pk}:{today}", chat_id=111).exists()
    tomorrow = today + timedelta(days=1)
    schedule.tick(_at(tomorrow, 8, 5))
    esc = Outbox.objects.get(key=f"late:{t.pk}:{tomorrow}")
    assert esc.chat_id == 999 and "Kechikdi" in esc.text


def test_weekly_summary_to_bosh_only(tg, boss, ali):
    linked(ali, 111)
    linked(boss, 999)
    d = timezone.localdate()
    monday = d - timedelta(days=d.weekday())
    schedule.tick(_at(monday, 9, 10))
    w = Outbox.objects.filter(key__startswith="weekly:")
    assert w.count() == 1 and w.get().chat_id == 999


def test_telegram_page_makes_one_time_link(client, ali, settings):
    from tests.conftest import login
    settings.TST_BOT_USERNAME = "tst_vazifa_bot"
    login(client, ali)
    page = client.post("/telegram/").content.decode()
    assert "https://t.me/tst_vazifa_bot?start=" in page
    assert LinkCode.objects.filter(user=ali, used_at__isnull=True).count() == 1


def test_backup_goes_only_to_linked_bosh(monkeypatch, tmp_path, boss, ali):
    from django.core.management import call_command
    linked(boss, 999)
    linked(ali, 111)
    sent = []
    monkeypatch.setattr(api, "send_document", lambda chat_id, path, caption="": sent.append(chat_id))
    f = tmp_path / "tst-2026-11-01.sql.gz"
    f.write_bytes(b"x" * 100)
    call_command("send_backup", str(f))
    assert sent == [999]
