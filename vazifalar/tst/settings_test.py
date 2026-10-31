# Test settings: same as production settings, with a throwaway key and a fresh SQLite database.
import os
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-secret")
os.environ["DATABASE_URL"] = "sqlite://:memory:"
from tst.settings import *  # noqa
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]   # tests only: fast
TST_BOT_TOKEN = ""          # tests never talk to the real Telegram bot, even on the server
TST_BOT_USERNAME = ""
