from sqlalchemy.orm import Session
from backend.db.models import ApprovalRequest
from backend.services.audit_service import log_event
import json
from datetime import datetime

class ApprovalService:
    def create_request(self, db: Session, requester: str, action_type: str, payload: dict, approver: str = None):
        """Создает новый запрос на согласование"""
        req = ApprovalRequest(
            requester=requester,
            action_type=action_type,
            payload=json.dumps(payload),
            approver=approver,
            status="PENDING"
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        
        log_event(db, user=requester, action="APPROVAL_REQUEST", target="system",
                  details={"id": req.id, "type": action_type}, status="SUCCESS")
        return req

    def get_pending_requests(self, db: Session, user_role: str = None):
        """Возвращает список ожидающих заявок"""
        # В простой реализации админы видят всё
        # В сложной - фильтр по approver
        return db.query(ApprovalRequest).filter(ApprovalRequest.status == "PENDING").all()

    def process_request(self, db: Session, request_id: int, user: str, decision: str, comment: str = None):
        """Обрабатывает заявку (APPROVE/REJECT)"""
        req = db.query(ApprovalRequest).filter(ApprovalRequest.id == request_id).first()
        if not req:
            raise ValueError("Request not found")
            
        if req.status != "PENDING":
            raise ValueError("Request already processed")

        req.status = decision # APPROVED / REJECTED
        req.processed_by = user
        req.processed_at = datetime.utcnow()
        req.comment = comment
        
        db.commit()
        
        log_event(db, user=user, action=f"APPROVAL_{decision}", target="system",
                  details={"id": req.id}, status="SUCCESS")
        
        return req

approval_service = ApprovalService()
