"""
accounts/people.py — the bosh manages people from the website (no server needed).
# CORE: reusable — who may do this comes from the role policy (sees_all), never from names.

Rules: only a sees_all person; nobody blocks or demotes himself; there is always at least one active sees_all
person; a new or reset password is shown ONCE to the bosh and must be changed at the person's next login;
a reset or a block signs the person out on every device. Nothing is deleted (a person is blocked, not removed).
"""
import re
import secrets

from django.db import transaction

import audit.models as audit
from accounts.models import UserAccount
from config import values as cfg

USERNAME = re.compile(r"^[a-z][a-z0-9_]{2,29}$")


class NotAllowed(Exception):
    pass


def _check(actor):
    if not actor.sees_all:
        raise NotAllowed("Bu bo'lim faqat bosh direktor uchun.")


def _new_password() -> str:
    return secrets.token_urlsafe(9)


def _last_boss_guard(target, new_role=None, new_active=None):
    becomes_non_boss = (new_role is not None and not cfg.ROLES.get(new_role, {}).get("sees_all")) or new_active is False
    if target.sees_all and target.is_active and becomes_non_boss:
        others = [u for u in UserAccount.objects.filter(is_active=True).exclude(pk=target.pk) if u.sees_all]
        if not others:
            raise NotAllowed("Kamida bitta bosh direktor qolishi kerak.")


def add_person(actor, username, name, role) -> tuple:  # CORE: reusable → (person, one-time password)
    _check(actor)
    username, name = (username or "").strip().lower(), " ".join((name or "").split())
    if not USERNAME.match(username):
        raise NotAllowed("Login: lotin harflari, raqam va _ (3–30 belgi), harf bilan boshlansin.")
    if not name:
        raise NotAllowed("Ismini yozing.")
    if role not in cfg.ROLES:
        raise NotAllowed("Lavozimni tanlang.")
    if UserAccount.objects.filter(username=username).exists():
        raise NotAllowed("Bunday login bor.")
    pw = _new_password()
    with transaction.atomic():
        u = UserAccount(username=username, name=name, role=role, must_change_password=True)
        u.set_password(pw)
        u.save()
        audit.write(actor.username, "odam_qoshildi", "user_account", u.pk, new={"username": username, "role": role})
    return u, pw


def reset_password(actor, target) -> str:  # CORE: reusable → the one-time password
    _check(actor)
    pw = _new_password()
    with transaction.atomic():
        target.set_password(pw)
        target.must_change_password = True
        target.session_epoch += 1
        target.save(update_fields=["password_hash", "must_change_password", "session_epoch"])
        audit.write(actor.username, "parol_tiklandi", "user_account", target.pk)
    return pw


def set_active(actor, target, active: bool):  # CORE: reusable
    _check(actor)
    if target.pk == actor.pk and not active:
        raise NotAllowed("O'zingizni bloklay olmaysiz.")
    _last_boss_guard(target, new_active=active)
    with transaction.atomic():
        target.is_active = bool(active)
        if not active:
            target.session_epoch += 1
        target.save(update_fields=["is_active", "session_epoch"])
        audit.write(actor.username, "faollashtirildi" if active else "bloklandi", "user_account", target.pk)


def edit_person(actor, target, name, role):  # CORE: reusable
    _check(actor)
    name = " ".join((name or "").split())
    if not name:
        raise NotAllowed("Ismini yozing.")
    if role not in cfg.ROLES:
        raise NotAllowed("Lavozimni tanlang.")
    if target.pk == actor.pk and role != target.role:
        raise NotAllowed("O'z lavozimingizni o'zgartira olmaysiz.")
    _last_boss_guard(target, new_role=role)
    old = {"name": target.name, "role": target.role}
    target.name, target.role = name, role
    target.save(update_fields=["name", "role"])
    audit.write(actor.username, "odam_ozgardi", "user_account", target.pk, old=old, new={"name": name, "role": role})


def unlink_telegram(actor, target):  # CORE: reusable — e.g. the phone was lost
    _check(actor)
    target.telegram_user_id = None
    target.save(update_fields=["telegram_user_id"])
    audit.write(actor.username, "telegram_uzildi", "user_account", target.pk)
