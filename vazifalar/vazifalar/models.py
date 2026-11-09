"""
vazifalar/models.py — one task and its history.
# CORE: reusable — no company-specific assumption (people and roles are CONFIG/data).

A task has five things: what (title), who (assignee), by when (due_date), status, and comments.
- Nothing is deleted (LAW 1): a wrong task is CANCELLED with a reason, and stays visible in history.
- Every change is an append-only VazifaEvent (LAW 7): who, what, when (server time), from web or Telegram.
- `status` and `due_date` on Vazifa are the current state; they change ONLY inside vazifalar/services.py,
  in the same transaction as the event that explains the change (guard test: state == last event).
"""
from django.db import models

from accounts.models import UserAccount
from core.ledger import AppendOnlyModel, LedgerModel


class Vazifa(LedgerModel):  # CORE: reusable
    YANGI = "yangi"
    BAJARILDI = "bajarildi"
    BEKOR = "bekor"
    STATUSES = [(YANGI, "Yangi"), (BAJARILDI, "Bajarildi"), (BEKOR, "O'chirildi")]

    id = models.BigAutoField(primary_key=True)          # short number: fits a Telegram button
    title = models.CharField(max_length=300)
    assignee = models.ForeignKey(UserAccount, on_delete=models.PROTECT, related_name="vazifalar")
    due_date = models.DateField(null=True, blank=True)   # empty = "Rejasiz": written down, not yet planned
    status = models.CharField(max_length=12, choices=STATUSES, default=YANGI)
    company = models.CharField(max_length=20, blank=True, default="")     # key from CONFIG COMPANIES, optional
    category = models.CharField(max_length=20, blank=True, default="")    # "Yo'nalish": key from CONFIG CATEGORIES
    important = models.BooleanField(default=False)                         # "Muhim": shown first, red
    private = models.BooleanField(default=False)                           # "Maxfiy": only giver, doer and bosh see it
    repeat = models.CharField(max_length=20, blank=True, default="")      # "", daily, weekly[:wd], monthly[:day]
    repeat_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT,
                                  related_name="next_repeats")             # the task this one repeats
    created_by = models.ForeignKey(UserAccount, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "vazifa"
        ordering = ["due_date", "-important", "created_at"]
        indexes = [models.Index(fields=["assignee", "status", "due_date"]),
                   models.Index(fields=["status", "due_date"])]

    def __str__(self):
        return f"#{self.pk} {self.title}"

    @property
    def repeat_label(self) -> str:
        from config import values as cfg
        kind, _, arg = (self.repeat or "").partition(":")
        if kind == "daily":
            return "Har kuni"
        if kind == "weekly":
            return f"Har {cfg.DAY_LONG[int(arg)].lower()}" if arg else "Har hafta"
        if kind == "monthly":
            return f"Har oy {arg}-kuni" if arg else "Har oy"
        return ""

    @property
    def category_label(self) -> str:
        from config import values as cfg
        return {k: lbl for k, lbl, _ in cfg.CATEGORIES}.get(self.category, "")

    @property
    def company_label(self) -> str:
        from config import values as cfg
        return dict(cfg.COMPANIES).get(self.company, "")

    @property
    def is_open(self) -> bool:
        return self.status == self.YANGI

    @property
    def is_done(self) -> bool:
        return self.status == self.BAJARILDI


class VazifaEvent(AppendOnlyModel):  # CORE: reusable — the task's history, written once, never changed
    YARATILDI = "yaratildi"
    BAJARILDI = "bajarildi"
    QAYTA_OCHILDI = "qayta_ochildi"
    BEKOR = "bekor"
    MUDDAT = "muddat"
    KIMGA = "kimga"
    NOM = "nom"
    KOMPANIYA = "kompaniya"
    MUHIM = "muhim"
    MAXFIY = "maxfiy"
    TAKROR = "takror"
    IZOH = "izoh"
    YONALISH = "yonalish"
    KINDS = [(YARATILDI, "Yaratildi"), (BAJARILDI, "Bajarildi"), (QAYTA_OCHILDI, "Qayta ochildi"),
             (BEKOR, "O'chirildi"), (MUDDAT, "Muddat o'zgardi"), (KIMGA, "Boshqaga o'tkazildi"), (NOM, "Nomi o'zgardi"),
             (KOMPANIYA, "Kompaniya o'zgardi"), (MUHIM, "Muhimlik o'zgardi"), (MAXFIY, "Maxfiylik o'zgardi"), (TAKROR, "Takrorlash o'zgardi"),
             (IZOH, "Izoh"), (YONALISH, "Yo'nalish o'zgardi")]
    WEB = "web"
    TELEGRAM = "telegram"
    REPEAT = "takror"      # created automatically when a repeating task was closed

    id = models.BigAutoField(primary_key=True)
    vazifa = models.ForeignKey(Vazifa, on_delete=models.PROTECT, related_name="events")
    kind = models.CharField(max_length=16, choices=KINDS)
    actor = models.ForeignKey(UserAccount, on_delete=models.PROTECT, related_name="+")
    note = models.TextField(blank=True, default="")      # comment text or cancel reason
    old_due = models.DateField(null=True, blank=True)
    new_due = models.DateField(null=True, blank=True)
    old_assignee = models.ForeignKey(UserAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    new_assignee = models.ForeignKey(UserAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    source = models.CharField(max_length=10, default=WEB)
    created_at = models.DateTimeField(auto_now_add=True)  # server time (LAW 6)

    class Meta:
        db_table = "vazifa_event"
        ordering = ["created_at", "id"]
