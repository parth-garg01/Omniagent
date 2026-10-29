from sqlalchemy.orm import Session

from .models import AuditEvent


def audit(db: Session, actor_id: str | None, action: str, rtype: str, rid: str | None,
          outcome: str, request_id: str | None = None) -> None:
    db.add(AuditEvent(actor_id=actor_id, action=action, resource_type=rtype, resource_id=rid,
                      outcome=outcome, request_id=request_id))
    db.commit()
