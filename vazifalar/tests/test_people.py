# People page: only the bosh; one-time passwords; forced change; sign-out on reset/block; guards.
import pytest

from accounts import people as ppl
from accounts.models import UserAccount
from audit.models import AuditLog
from tests.conftest import login


def test_only_bosh_sees_people_page(client, boss, ali):
    login(client, ali)
    assert client.get("/odamlar/").status_code == 404
    assert client.post(f"/odamlar/{boss.username}/parol/").status_code == 404
    client.post("/chiqish/")
    login(client, boss)
    assert client.get("/odamlar/").status_code == 200


def test_reset_password_shows_once_and_forces_change(client, boss, ali):
    other = client.__class__()
    login(other, ali)                                        # ali is signed in elsewhere
    login(client, boss)
    page = client.post(f"/odamlar/{ali.username}/parol/").content.decode()
    ali.refresh_from_db()
    assert ali.must_change_password and 'id="pw"' in page
    pw = page.split('id="pw">')[1].split("<")[0]
    assert ali.check_password(pw)
    assert other.get("/").status_code == 302                 # his old session is gone
    other.post("/kirish/", {"username": ali.username, "password": pw})
    assert other.get("/").url == "/parol/"                   # must choose his own first
    other.post("/parol/", {"old": pw, "new": "yangiparol9", "again": "yangiparol9"})
    ali.refresh_from_db()
    assert not ali.must_change_password and other.get("/").status_code == 200


def test_block_signs_out_and_keeps_tasks(client, boss, ali):
    from datetime import date
    from vazifalar import services as sv
    t = sv.create_task(boss, "x", ali, date(2026, 11, 2))
    other = client.__class__()
    login(other, ali)
    login(client, boss)
    client.post(f"/odamlar/{ali.username}/blok/")
    assert other.get("/").status_code == 302
    assert other.post("/kirish/", {"username": ali.username, "password": "pw-ali"}).status_code == 200  # refused
    t.refresh_from_db()
    assert t.assignee == ali
    client.post(f"/odamlar/{ali.username}/faol/")
    ali.refresh_from_db()
    assert ali.is_active


def test_add_person_and_guards(boss, ali):
    u, pw = ppl.add_person(boss, "shuxrat", "Shuxrat", "menejer")
    assert u.check_password(pw) and u.must_change_password
    with pytest.raises(ppl.NotAllowed):
        ppl.add_person(boss, "shuxrat", "Boshqa", "menejer")       # login taken
    with pytest.raises(ppl.NotAllowed):
        ppl.add_person(boss, "Bad Login", "X", "menejer")
    with pytest.raises(ppl.NotAllowed):
        ppl.set_active(boss, boss, False)                          # not yourself
    with pytest.raises(ppl.NotAllowed):
        ppl.edit_person(boss, boss, "Rahbar", "menejer")           # not your own role
    with pytest.raises(ppl.NotAllowed):
        ppl.add_person(ali, "z", "Z", "menejer")                   # managers cannot
    assert AuditLog.objects.filter(action="odam_qoshildi").exists()


def test_last_boss_cannot_be_removed(boss):
    second, _ = ppl.add_person(boss, "ikkinchi", "Ikkinchi", "bosh")
    ppl.set_active(second, boss, False)                            # fine: another boss remains
    with pytest.raises(ppl.NotAllowed):
        ppl.edit_person(second, second, "Ikkinchi", "menejer")     # own role
    boss.refresh_from_db()
    ppl.set_active(second, boss, True)
    ppl.edit_person(second, boss, "Rahbar", "menejer")             # boss demoted; second remains
    boss.refresh_from_db()
    with pytest.raises(ppl.NotAllowed):
        ppl.set_active(second, second, False)


def test_unlink_telegram(boss, ali):
    ali.telegram_user_id = 111
    ali.save()
    ppl.unlink_telegram(boss, ali)
    ali.refresh_from_db()
    assert ali.telegram_user_id is None
