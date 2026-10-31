# CORE: reusable — the boss forgot / a manager lost his password: a new one-time password, printed ONCE here
# on the server console (never sent through chat). Usage: python manage.py reset_password menejer1
import secrets

from django.core.management.base import BaseCommand, CommandError

import audit.models as audit
from accounts.models import UserAccount


class Command(BaseCommand):
    help = "Give a person a new password (printed once)"

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, username, **opts):
        u = UserAccount.objects.filter(username=username).first()
        if u is None:
            raise CommandError(f"no such person: {username}")
        pw = secrets.token_urlsafe(8)
        u.set_password(pw)
        u.must_change_password = True
        u.session_epoch += 1
        u.save(update_fields=["password_hash", "must_change_password", "session_epoch"])
        audit.write("server", "parol_tiklandi", "user_account", u.pk)
        self.stdout.write(f"{u.username}: {pw}")
