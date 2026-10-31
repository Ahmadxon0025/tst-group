import pytest

from accounts.models import UserAccount


def _mk(username, name, role):
    u = UserAccount(username=username, name=name, role=role)
    u.set_password("pw-" + username)
    u.save()
    return u


@pytest.fixture
def boss(db):
    return _mk("rahbar", "Rahbar", "bosh")


@pytest.fixture
def ali(db):          # a manager
    return _mk("ali", "Ali", "menejer")


@pytest.fixture
def vali(db):         # another manager
    return _mk("vali", "Vali", "menejer")


@pytest.fixture
def worker(db):       # floor staff, for later
    return _mk("ishchi", "Ishchi", "xodim")


def login(client, user):
    r = client.post("/kirish/", {"username": user.username, "password": "pw-" + user.username})
    assert r.status_code == 302
    return client
