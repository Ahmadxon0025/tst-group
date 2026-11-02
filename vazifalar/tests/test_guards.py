# Guard tests — named after the rule each one protects. Deploy refuses on red.
from datetime import date, timedelta

import pytest
from django.utils import timezone

from audit.models import AuditLog
from core.ledger import AppendOnlyViolation, HardDeleteForbidden
from tests.conftest import login
from vazifalar import services as sv
from vazifalar.models import Vazifa, VazifaEvent

D = date(2026, 11, 2)


def test_no_hard_delete_possible(boss, ali):
    t = sv.create_task(boss, "Akt sverka", ali, D)
    with pytest.raises(HardDeleteForbidden):
        t.delete()
    with pytest.raises(HardDeleteForbidden):
        Vazifa.objects.all().delete()


def test_history_is_append_only(boss, ali):
    t = sv.create_task(boss, "Akt sverka", ali, D)
    ev = t.events.first()
    ev.note = "changed"
    with pytest.raises(AppendOnlyViolation):
        ev.save()
    with pytest.raises(AppendOnlyViolation):
        VazifaEvent.objects.all().update(note="x")
    with pytest.raises(AppendOnlyViolation):
        VazifaEvent.objects.all().delete()
    with pytest.raises(AppendOnlyViolation):
        AuditLog.objects.all().delete()


def test_managers_create_for_anyone_workers_cannot(boss, ali, vali, worker):
    t = sv.create_task(ali, "Valiga", vali, D)
    assert t.created_by == ali and t.assignee == vali
    with pytest.raises(sv.NotAllowed):
        sv.create_task(worker, "x", worker, D)


def test_only_giver_or_bosh_manages(boss, ali, vali):
    t = sv.create_task(ali, "x", vali, D)
    for fn, arg in ((sv.cancel, "kerak emas"), (sv.change_due, D + timedelta(days=1)), (sv.reassign, ali)):
        with pytest.raises(sv.NotAllowed):
            fn(vali, t.pk, arg)            # the assignee may not
    sv.change_due(ali, t.pk, D + timedelta(days=1))      # the giver may
    sv.reassign(boss, t.pk, boss)                        # the bosh may
    t.refresh_from_db()
    assert t.assignee == boss and t.due_date == D + timedelta(days=1)


def test_everyone_sees_the_board_except_maxfiy(boss, ali, vali):
    a = sv.create_task(boss, "bossdan alige", ali, D)
    b = sv.create_task(ali, "alidan valiga", vali, D)
    c = sv.create_task(boss, "bossdan valiga", vali, D)                     # open → ali sees it
    m = sv.create_task(boss, "maxfiy valiga", vali, D, private=True)       # private → ali does not
    seen_by_ali = set(sv.visible_tasks(ali).values_list("pk", flat=True))
    assert seen_by_ali == {a.pk, b.pk, c.pk}
    assert set(sv.visible_tasks(vali).values_list("pk", flat=True)) == {a.pk, b.pk, c.pk, m.pk}   # the doer
    assert set(sv.visible_tasks(boss).values_list("pk", flat=True)) == {a.pk, b.pk, c.pk, m.pk}   # the bosh
    p = sv.create_task(ali, "ali bergan maxfiy", vali, D, private=True)
    assert sv.visible_tasks(boss).filter(pk=p.pk).exists()                  # bosh sees every Maxfiy
    with pytest.raises(sv.NotAllowed):
        sv.mark_done(ali, c.pk)                                             # seeing is not touching

def test_reassign_is_recorded(boss, ali, vali):
    t = sv.create_task(boss, "x", ali, D)
    sv.reassign(boss, t.pk, vali)
    ev = t.events.last()
    assert ev.kind == "kimga" and ev.old_assignee == ali and ev.new_assignee == vali
    assert AuditLog.objects.filter(action="vazifa_kimga", entity_id=str(t.pk)).exists()


def test_company_must_be_known(boss, ali):
    with pytest.raises(sv.NotAllowed):
        sv.create_task(boss, "x", ali, D, company="nope")
    t = sv.create_task(boss, "x", ali, D, company="git")
    assert t.company_label == "GIT"
    sv.set_company(boss, t.pk, "tst")
    t.refresh_from_db()
    assert t.company == "tst" and t.events.last().kind == "kompaniya"


def test_delete_keeps_the_task_in_history(boss, ali):
    t = sv.create_task(boss, "x", ali, D)
    sv.cancel(boss, t.pk, "  ")                       # one-click delete: no reason typed
    t.refresh_from_db()
    assert t.status == Vazifa.BEKOR and Vazifa.objects.filter(pk=t.pk).exists()
    assert t.events.last().note == "O'chirildi"
    with pytest.raises(sv.NotAllowed):
        sv.mark_done(ali, t.pk)


def test_state_equals_last_event(boss, ali):
    t = sv.create_task(boss, "x", ali, D)
    sv.mark_done(ali, t.pk)
    sv.mark_done(ali, t.pk)          # pressed twice: one event only
    sv.reopen(boss, t.pk)
    sv.change_due(boss, t.pk, D + timedelta(days=3))
    sv.mark_done(ali, t.pk)
    t.refresh_from_db()
    kinds = list(t.events.values_list("kind", flat=True))
    assert kinds == ["yaratildi", "bajarildi", "qayta_ochildi", "muddat", "bajarildi"]
    assert t.status == "bajarildi"
    assert t.due_date == t.events.filter(kind="muddat").last().new_due
    assert AuditLog.objects.filter(entity="vazifa", entity_id=str(t.pk)).count() == 5


def test_timestamps_come_from_the_server(boss, ali):
    before = timezone.now()
    t = sv.create_task(boss, "x", ali, D)
    sv.mark_done(ali, t.pk)
    t.refresh_from_db()
    assert before <= t.done_at <= timezone.now()


def test_unknown_role_gets_nothing(db):
    from accounts.models import UserAccount
    u = UserAccount.objects.create(username="q", name="Q", role="nobody")
    assert not u.can_create and not u.sees_all


# --- pages ---------------------------------------------------------------------------------------
def test_pages_need_login(client):
    for url in ("/", "/mening/", "/shtab/"):
        assert client.get(url).status_code == 302


def test_week_page_and_toggle(client, boss, ali):
    login(client, boss)
    today = timezone.localdate()
    r = client.post("/vazifa/yangi/", {"title": "Top-10 debitor", "kim": ali.username,
                                       "due": today.isoformat(), "company": "tst", "next": "/"})
    assert r.status_code == 302
    t = Vazifa.objects.get()
    assert t.company == "tst"
    page = client.get("/").content.decode()
    assert "Top-10 debitor" in page
    assert "Top-10 debitor" in client.get("/?k=tst").content.decode()
    assert "Top-10 debitor" not in client.get("/?k=git").content.decode()
    client.post(f"/vazifa/{t.pk}/belgi/", {"next": "/"})
    t.refresh_from_db()
    assert t.is_done


def test_manager_page_shows_board_but_not_maxfiy(client, boss, ali, vali):
    sv.create_task(boss, "Aliniki", ali, timezone.localdate())
    sv.create_task(boss, "Valiniki", vali, timezone.localdate())
    sv.create_task(boss, "Maxfiy ish", vali, timezone.localdate(), private=True)
    login(client, ali)
    page = client.get("/").content.decode()
    assert "Aliniki" in page and "Valiniki" in page and "Maxfiy ish" not in page
    hidden = Vazifa.objects.get(title="Maxfiy ish")
    assert client.get(f"/vazifa/{hidden.pk}/").status_code == 404
    other = Vazifa.objects.get(title="Valiniki")
    html = client.get(f"/vazifa/{other.pk}/?partial=1").content.decode()
    assert "saqlash" not in html and "/izoh/" not in html                   # read-only for an onlooker

def test_worker_cannot_create_from_page(client, worker, ali):
    login(client, worker)
    assert 'id="add"' not in client.get("/").content.decode()
    client.post("/vazifa/yangi/", {"title": "z", "kim": ali.username, "due": "2026-11-02", "next": "/"})
    assert not Vazifa.objects.filter(title="z").exists()


def test_overdue_goes_to_kechikkan_not_the_day(client, boss, ali):
    sv.create_task(boss, "Eski ish", ali, timezone.localdate() - timedelta(days=3))
    login(client, boss)
    page = client.get("/").content.decode()
    assert page.count("Eski ish") == 1 and "3 kun kechikdi" in page


def test_shtab_groups_by_person(client, boss, ali, vali):
    sv.create_task(boss, "Kech qolgan", ali, timezone.localdate() - timedelta(days=1))
    sv.create_task(boss, "Shu hafta", vali, timezone.localdate() + timedelta(days=2))
    login(client, boss)
    page = client.get("/shtab/").content.decode()
    assert "Kech qolgan" in page and "Shu hafta" in page and "1 kechikkan" in page


def test_script_switch(client, ali):
    login(client, ali)
    client.post("/yozuv/", {"next": "/"})
    ali.refresh_from_db()
    assert ali.script == "cyrl"
    assert 'data-script="cyrl"' in client.get("/").content.decode()


def test_next_redirect_is_local_only(client, boss, ali):
    login(client, boss)
    r = client.post("/vazifa/yangi/", {"title": "a", "kim": ali.username, "due": "2026-11-02",
                                       "next": "https://evil.example/"})
    assert r["Location"] == "/"


def test_password_change(client, ali):
    login(client, ali)
    r = client.post("/parol/", {"old": "wrong", "new": "yangiparol1", "again": "yangiparol1"})
    ali.refresh_from_db()
    assert ali.check_password("pw-ali")
    client.post("/parol/", {"old": "pw-ali", "new": "yangiparol1", "again": "yangiparol1"})
    ali.refresh_from_db()
    assert ali.check_password("yangiparol1")


def test_rename_and_combined_edit(boss, ali, vali):
    t = sv.create_task(boss, "Eski nom", ali, D)
    sv.update_task(boss, t.pk, title="Yangi nom", assignee=vali, due_date=D + timedelta(days=2), company="git")
    t.refresh_from_db()
    assert (t.title, t.assignee, t.due_date, t.company) == ("Yangi nom", vali, D + timedelta(days=2), "git")
    kinds = list(t.events.values_list("kind", flat=True))
    assert kinds == ["yaratildi", "nom", "kimga", "muddat", "kompaniya"]
    assert t.events.get(kind="nom").note == "Eski nom"
    sv.update_task(boss, t.pk, title="Yangi nom", assignee=vali, due_date=t.due_date, company="git")
    assert t.events.count() == 5                      # nothing changed → nothing written
    with pytest.raises(sv.NotAllowed):
        sv.update_task(vali, t.pk, title="assignee may not rename")


def test_drag_to_another_day(client, boss, ali):
    today = timezone.localdate()
    t = sv.create_task(boss, "x", ali, today)
    login(client, ali)                                # the assignee may not move it
    r = client.post(f"/vazifa/{t.pk}/kunga/", {"due": (today + timedelta(days=1)).isoformat()})
    assert r.status_code == 400 and r.json()["ok"] is False
    client.post("/chiqish/")
    login(client, boss)
    r = client.post(f"/vazifa/{t.pk}/kunga/", {"due": (today - timedelta(days=1)).isoformat()})
    assert r.status_code == 400                       # not into the past
    r = client.post(f"/vazifa/{t.pk}/kunga/", {"due": (today + timedelta(days=2)).isoformat()})
    assert r.json() == {"ok": True, "due": (today + timedelta(days=2)).isoformat()}
    t.refresh_from_db()
    assert t.due_date == today + timedelta(days=2) and t.events.last().kind == "muddat"


def test_edit_window_and_save(client, boss, ali):
    t = sv.create_task(boss, "Oyna", ali, timezone.localdate())
    login(client, boss)
    html = client.get(f"/vazifa/{t.pk}/?partial=1&next=/").content.decode()
    assert 'class="tp"' in html and "<html" not in html and "saqlash" in html
    r = client.post(f"/vazifa/{t.pk}/saqlash/", {"title": "Oyna 2", "kim": ali.username,
                                                 "due": t.due_date.isoformat(), "company": "", "next": "/"})
    assert r["Location"] == "/"
    t.refresh_from_db()
    assert t.title == "Oyna 2"
    client.post(f"/vazifa/{t.pk}/bekor/", {"next": "/"})
    t.refresh_from_db()
    assert t.status == "bekor"


def test_app_manifest_and_service_worker(client):
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200 and m.json()["display"] == "standalone"
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and sw["Service-Worker-Allowed"] == "/"


def test_one_line_add_defaults_to_me_and_rejasiz(client, boss, ali):
    login(client, boss)
    assert 'id="qbar"' in client.get("/").content.decode()
    client.post("/vazifa/yangi/", {"title": "Bankka qo'ng'iroq", "next": "/"})
    client.post("/vazifa/yangi/", {"title": "Hisobot ertaga @ali #tst !", "next": "/"})
    a = Vazifa.objects.get(title="Bankka qo'ng'iroq")
    b = Vazifa.objects.get(title="Hisobot")
    assert a.assignee == boss and a.due_date is None
    assert b.assignee == ali and b.company == "tst" and b.important



def test_rejasiz_column_and_drag_both_ways(client, boss, ali):
    today = timezone.localdate()
    t = sv.create_task(boss, "Rejasiz ish", ali, None)
    login(client, boss)
    page = client.get("/").content.decode()
    assert 'class="col inbox"' in page and page.count("Rejasiz ish") == 1
    r = client.post(f"/vazifa/{t.pk}/kunga/", {"due": (today + timedelta(days=1)).isoformat()})
    assert r.json()["ok"]
    r = client.post(f"/vazifa/{t.pk}/kunga/", {"due": ""})          # back to Rejasiz
    assert r.json() == {"ok": True, "due": ""}
    t.refresh_from_db()
    assert t.due_date is None
    assert [e.kind for e in t.events.all()] == ["yaratildi", "muddat", "muddat"]


def test_undated_is_never_late_and_not_in_morning_list(boss, ali):
    from bot import schedule
    from bot.models import Outbox
    t = sv.create_task(boss, "Sanasiz", ali, None)
    assert not Vazifa.objects.filter(due_date__lt=timezone.localdate(), pk=t.pk).exists()
    ali.telegram_user_id = 111
    ali.save()
    from datetime import datetime
    from zoneinfo import ZoneInfo
    d = timezone.localdate()
    schedule.tick(datetime(d.year, d.month, d.day, 8, 5, tzinfo=ZoneInfo("Asia/Tashkent")))
    assert not Outbox.objects.filter(key__startswith="morning:").exists()


def test_edit_window_can_clear_the_date(client, boss, ali):
    t = sv.create_task(boss, "x", ali, timezone.localdate())
    login(client, boss)
    client.post(f"/vazifa/{t.pk}/saqlash/", {"title": "x", "kim": ali.username, "due": "", "company": "", "next": "/"})
    t.refresh_from_db()
    assert t.due_date is None
    assert "Sanasiz" in client.get(f"/vazifa/{t.pk}/?partial=1").content.decode()


def test_repeat_without_date_starts_today(boss):
    t = sv.create_task(boss, "Kassa", boss, None, repeat="daily")
    assert t.due_date == timezone.localdate()



def test_maxfiy_by_quick_add_and_toggle(client, boss, ali):
    login(client, boss)
    client.post("/vazifa/yangi/", {"title": "Bank strategiyasi maxfiy @ali", "next": "/"})
    t = Vazifa.objects.get()
    assert t.private and t.title == "Bank strategiyasi"
    sv.update_task(boss, t.pk, private=False)
    t.refresh_from_db()
    assert not t.private and t.events.last().kind == "maxfiy"


def test_onlooker_card_has_no_active_tick(client, boss, ali, vali):
    t = sv.create_task(boss, "Valiniki", vali, timezone.localdate())
    login(client, ali)
    page = client.get("/").content.decode()
    assert f'action="/vazifa/{t.pk}/belgi/"' not in page and 'tick ro' in page


def test_bulk_paste_makes_one_task_per_line(client, boss, ali, worker):
    login(client, boss)
    r = client.post("/vazifa/kop/", {"lines": "Birinchi ertaga @ali #tst !\n\n- Ikkinchi juma maxfiy\nUchinchi"})
    assert r.json()["made"] == 3
    a, b, c = (Vazifa.objects.get(title=t) for t in ("Birinchi", "Ikkinchi", "Uchinchi"))
    assert a.assignee == ali and a.important and a.company == "tst"
    assert b.private and b.assignee == boss and b.due_date is not None
    assert c.due_date is None
    client.post("/chiqish/")
    login(client, worker)
    assert client.post("/vazifa/kop/", {"lines": "x\ny"}).json()["made"] == 0
