import json
from sqlalchemy.orm import Session
from backend.db.models import AuditRecord

def log_event(db: Session, user: str, action: str, target: str, details: dict = None, ip: str = "127.0.0.1", status: str = "SUCCESS"):
    try:
        record = AuditRecord(
            user=user,
            action=action,
            target=target,
            details=json.dumps(details, default=str) if details else "",
            ip_address=ip,
            status=status
        )
        db.add(record)
        db.commit()
    except Exception as e:
        print(f"Audit Log Error: {e}") # Fallback logging
