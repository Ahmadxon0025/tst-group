from datetime import date

import pytest

from core.quickadd import next_repeat, parse

SAT = date(2026, 10, 31)   # a Saturday
PEOPLE = {"ali": "ali", "vali": "vali", "rahbar": "rahbar"}
COS = {"tst": "tst", "git": "git", "guruh": "guruh"}


def P(text, today=SAT):
    return parse(text, today, PEOPLE, COS)


def test_everything_in_one_line():
    p = P("NBU ma'lumotnoma ertaga @ali #guruh !")
    assert (p.title, p.due, p.who, p.company, p.important) == ("NBU ma'lumotnoma", date(2026, 11, 1), "ali", "guruh", True)


@pytest.mark.parametrize("text,due", [
    ("x bugun", SAT), ("x ertaga", date(2026, 11, 1)), ("x indinga", date(2026, 11, 2)),
    ("x dushanba", date(2026, 11, 2)), ("x shanba", date(2026, 11, 7)), ("x juma", date(2026, 11, 6)),
    ("x 3 kundan keyin", date(2026, 11, 3)), ("x 3 kun keyin", date(2026, 11, 3)),
    ("x 5-noyabr", date(2026, 11, 5)), ("x 5 noyabr", date(2026, 11, 5)), ("x 05.11", date(2026, 11, 5)),
    ("x 15-oktabr", date(2027, 10, 15)), ("x эртага", date(2026, 11, 1)), ("x душанба", date(2026, 11, 2)),
])
def test_dates(text, due):
    p = P(text)
    assert p.due == due and p.title == "x"


def test_repeats():
    p = P("Shtab hisoboti har dushanba @vali")
    assert p.repeat == "weekly:0" and p.due == date(2026, 11, 2) and p.title == "Shtab hisoboti"
    assert P("Kassa har kuni").repeat == "daily"
    m = P("Elektr to'lovi har oy 5")
    assert m.repeat == "monthly:5" and m.due == date(2026, 11, 5)
    assert P("x har shanba").due == SAT


def test_unknown_words_stay():
    p = P("@nobody bilan uchrashuv #nope")
    assert p.who is None and p.company is None and p.title == "@nobody bilan uchrashuv #nope" and p.due is None


def test_next_repeat():
    assert next_repeat("daily", date(2026, 11, 2), date(2026, 11, 2)) == date(2026, 11, 3)
    assert next_repeat("weekly:0", date(2026, 11, 2), date(2026, 11, 2)) == date(2026, 11, 9)
    assert next_repeat("monthly:31", date(2026, 1, 31), date(2026, 1, 31)) == date(2026, 2, 28)
    # closed late: rolls forward past today
    assert next_repeat("daily", date(2026, 10, 1), SAT) == SAT


def test_handles_with_shared_first_name(db):
    from accounts.models import UserAccount
    from vazifalar.quick import handles
    for u, n, r in (("rahbar", "Rahbar", "bosh"), ("fayzullo", "Fayzullo", "menejer"),
                    ("fayzullo_oka", "Fayzullo oka", "menejer"), ("abdurazzoq", "Abdurazzoq", "menejer")):
        UserAccount.objects.create(username=u, name=n, role=r)
    people, companies = handles()
    assert people["fayzullo"] == "fayzullo" and people["fayzullo_oka"] == "fayzullo_oka"
    assert people["fayzullooka"] == "fayzullo_oka" and people["abdurazzoq"] == "abdurazzoq"
    assert people["абдураззоқ"] == "abdurazzoq" and companies["mirshikor"] == "mirshikor"


def test_quick_add_from_the_window(client, db):
    from accounts.models import UserAccount
    from django.utils import timezone
    from datetime import timedelta
    from tests.conftest import login
    from vazifalar.models import Vazifa
    boss = UserAccount(username="rahbar", name="Rahbar", role="bosh"); boss.set_password("pw-rahbar"); boss.save()
    UserAccount.objects.create(username="ali", name="Ali", role="menejer")
    login(client, boss)
    j = client.get("/vazifa/tahlil/", {"q": "Hisobot ertaga @ali #git ! har dushanba"}).json()
    assert j["who"] == "ali" and j["company"] == "git" and j["important"] and j["repeat"] == "weekly:0"
    client.post("/vazifa/yangi/", {"title": "Hisobot ertaga @ali #git !", "next": "/"})
    t = Vazifa.objects.get()
    assert (t.title, t.assignee.username, t.company, t.important) == ("Hisobot", "ali", "git", True)
    assert t.due_date == timezone.localdate() + timedelta(days=1)


def test_repeating_task_makes_the_next_one_once(db):
    from datetime import timedelta
    from django.utils import timezone
    from accounts.models import UserAccount
    from vazifalar import services as sv
    from vazifalar.models import Vazifa
    boss = UserAccount.objects.create(username="rahbar", name="Rahbar", role="bosh")
    today = timezone.localdate()
    t = sv.create_task(boss, "Kassa", boss, today, repeat="daily", important=True)
    sv.mark_done(boss, t.pk)
    sv.reopen(boss, t.pk)
    sv.mark_done(boss, t.pk)                       # done twice → still one next copy
    nxt = Vazifa.objects.exclude(pk=t.pk)
    assert nxt.count() == 1
    n = nxt.get()
    assert n.due_date == today + timedelta(days=1) and n.repeat == "daily" and n.important and n.repeat_of == t
