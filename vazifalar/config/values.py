# CONFIG: TST — every TST-specific value lives here. A new company = a new copy of this file, no code change.

TIME_ZONE = "Asia/Tashkent"

PRODUCT_TITLE = "TST Vazifalar"

# Roles.
# bosh:    creates, sees and manages every task.
# menejer: creates tasks for anyone; sees tasks given to him and tasks he gave; manages the tasks he gave.
# xodim:   sees and closes only his own tasks (for later, when floor staff join).
ROLE_LABELS = {"bosh": "Bosh direktor", "menejer": "Menejer", "xodim": "Xodim"}

ROLES = {
    "bosh": {"can_create": True, "sees_all": True},
    "menejer": {"can_create": True, "sees_all": False},
    "xodim": {"can_create": False, "sees_all": False},
}

# The people are NOT in the code (the repository is public). They live in people.json next to manage.py,
# on the server only (git-ignored). Format: see people.example.json. Phone numbers are never stored here.
import json as _json
import os as _os
from pathlib import Path as _Path

PEOPLE_FILE = _os.environ.get("TST_PEOPLE_FILE") or str(_Path(__file__).resolve().parent.parent / "people.json")


def _load_people():
    try:
        with open(PEOPLE_FILE, encoding="utf-8") as f:
            return _json.load(f)
    except FileNotFoundError:
        return []


PEOPLE = _load_people()

# Each person's colour comes from people.json ("color"); anyone without one gets one from PERSON_PALETTE.
PERSON_COLORS = {p["username"]: p["color"] for p in PEOPLE if p.get("color")}
PERSON_PALETTE = ["#26348B", "#0F7A73", "#A86A12", "#7A3C78", "#4F6B2A", "#8A4B2D", "#3D5A80"]

TASK_TITLE_MAX = 300
BOARD_DAYS = 21          # days shown on the board at once (scroll sideways); ‹ › glide a week
DELETE_REASON_DEFAULT = "O'chirildi"   # used when a task is deleted without a typed reason

# Uzbek day and month names (screen wording).
DAY_SHORT = ["Du", "Se", "Chor", "Pay", "Ju", "Sha", "Yak"]
DAY_LONG = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
MONTHS_SHORT = ["yan", "fev", "mar", "apr", "may", "iyun", "iyul", "avg", "sen", "okt", "noy", "dek"]
MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul",
          "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]

# Bot schedule (used by the bot step).
MORNING_LIST_AT = "08:00"
EVENING_REMINDER_AT = "18:00"

# Which company a task belongs to (optional). Key → label.
COMPANIES = [
    ("tst", "TST"),
    ("git", "GIT"),
    ("mirshikor", "Mirshikor"),
    ("ibrat", "Ibrat"),
    ("guruh", "Guruh"),
]

# Areas of work ("Yo'nalish") — one per task, next to the company tag. Changed only by a Shtab decision.
# (key, label, extra quick-add words after "/"). Cyrillic forms are made automatically.
CATEGORIES = [
    ("bank", "Bank", ["nbu"]),
    ("moliya", "Moliya va qarzlar", ["qarz", "qarzlar", "pul", "kassa"]),
    ("huquq", "Huquq va davlat", ["sud", "soliq", "davlat", "yurist", "mib"]),
    ("ishlab", "Ishlab chiqarish", ["ishlabchiqarish", "sex", "boyoq", "bo'yoq", "tamir", "ta'mir"]),
    ("savdo", "Savdo", ["sotuv", "buyurtma", "mijoz"]),
    ("taminot", "Ta'minot", ["ta'minot", "boz", "bo'z", "kimyo"]),
    ("loyiha", "Loyihalar va investitsiya", ["loyihalar", "investitsiya", "invest", "xitoy"]),
    ("jamoa", "Jamoa va tizim", ["tizim", "kadr", "xodim"]),
]

# Writing script per person: "latn" (Lotin) or "cyrl" (Kirill). New people start with this.
DEFAULT_SCRIPT = "latn"

# Bot timing (Asia/Tashkent). A timed message is only queued inside its window after the time.
BOT_SEND_WINDOW_MINUTES = 120
WEEKLY_SUMMARY = (0, "09:00")   # Monday 09:00 → summary to the bosh, before the 10:00 Shtab
LINK_CODE_MINUTES = 15
