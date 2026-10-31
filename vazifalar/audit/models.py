# CORE: reusable — append-only audit log (LAW 7), same shape as nazorat-erp audit.AuditLog.
import uuid

from django.db import models

from core.ledger import AppendOnlyModel


class AuditLog(AppendOnlyModel):  # CORE: reusable
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.CharField(max_length=120)
    action = models.CharField(max_length=60)
    entity = models.CharField(max_length=60)
    entity_id = models.CharField(max_length=64)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)   # server time

    class Meta:
        db_table = "audit_log"
        ordering = ["-created_at"]


def write(actor: str, action: str, entity: str, entity_id, old=None, new=None):  # CORE: reusable
    return AuditLog.objects.create(actor=actor, action=action, entity=entity,
                                   entity_id=str(entity_id), old_value=old, new_value=new)
