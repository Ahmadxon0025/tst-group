# CORE: reusable — creates the people listed in people.json (CONFIG PEOPLE); skips anyone who already exists.
# Each new person gets a one-time password printed ONCE on the server console — never sent through chat.
import secrets

from django.core.management.base import BaseCommand, CommandError

import audit.models as audit
from accounts.models import UserAccount
from config import values as cfg


class Command(BaseCommand):
    help = "Create the people from people.json"

    def handle(self, *args, **opts):
        if not cfg.PEOPLE:
            raise CommandError(f"No people found — create {cfg.PEOPLE_FILE} (see people.example.json)")
        for p in cfg.PEOPLE:
            if p.get("role") not in cfg.ROLES:
                raise CommandError(f"Unknown role {p.get('role')!r} for {p.get('username')!r}")
            if UserAccount.objects.filter(username=p["username"]).exists():
                self.stdout.write(f"  bor: {p['username']}")
                continue
            pw = secrets.token_urlsafe(8)
            u = UserAccount(username=p["username"], name=p["name"], role=p["role"], must_change_password=True)
            u.set_password(pw)
            u.save()
            audit.write("system", "odam_qoshildi", "user_account", u.pk, new={"username": u.username, "role": u.role})
            self.stdout.write(f"  yangi: {p['username']}  parol: {pw}")
