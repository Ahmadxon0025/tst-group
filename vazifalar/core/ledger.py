"""
core/ledger.py — copied from nazorat-erp core/ledger/models.py (the no-delete and append-only bases).
# CORE: reusable — no client-specific assumption.
"""
from django.db import models


class HardDeleteForbidden(Exception):  # CORE: reusable
    """Raised on any attempt to hard-delete business data (LAW 1)."""


class LedgerQuerySet(models.QuerySet):  # CORE: reusable
    def delete(self, *args, **kwargs):
        raise HardDeleteForbidden("Bulk hard-delete is forbidden (LAW 1). Cancel with a reason instead.")


class LedgerManager(models.Manager.from_queryset(LedgerQuerySet)):  # CORE: reusable
    pass


class LedgerModel(models.Model):  # CORE: reusable
    """A business record: it cannot be hard-deleted."""
    objects = LedgerManager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise HardDeleteForbidden("Hard-delete is forbidden (LAW 1). Cancel with a reason instead.")


class AppendOnlyViolation(Exception):  # CORE: reusable
    """Raised on any attempt to update, delete or bulk-clear an append-only row (LAW 7)."""


class AppendOnlyQuerySet(models.QuerySet):  # CORE: reusable
    def delete(self, *args, **kwargs):
        raise AppendOnlyViolation("Bulk-delete of an append-only log is forbidden (LAW 7).")

    def update(self, *args, **kwargs):
        raise AppendOnlyViolation("Bulk-update of an append-only log is forbidden (LAW 7).")


class AppendOnlyManager(models.Manager.from_queryset(AppendOnlyQuerySet)):  # CORE: reusable
    pass


class AppendOnlyModel(models.Model):  # CORE: reusable
    """INSERT once; never UPDATE, DELETE, bulk-update or truncate."""
    objects = AppendOnlyManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyViolation("Updating an append-only record is forbidden (LAW 7).")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyViolation("Deleting an append-only record is forbidden (LAW 7).")
