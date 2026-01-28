import json
import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.routers.auth import require_admin, PermissionChecker, get_current_user
from backend.services.workflow_engine import workflow_engine

router = APIRouter(prefix=f"{settings.API_V1_STR}/workflows", tags=["workflows"])

# --- Models ---

class WorkflowStep(BaseModel):
    type: str
    # Другие поля зависят от типа, поэтому оставляем гибкость
    # Но для валидации лучше бы расписать, пока оставим так для простоты
    # Pydantic позволяет extra fields
    class Config:
        extra = "allow"

class WorkflowModel(BaseModel):
    id: Optional[str] = None
    name: str
    trigger: str
    enabled: bool = True
    steps: List[Dict[str, Any]]

    @validator("steps")
    def validate_steps(cls, v):
        for step in v:
            if "type" not in step:
                raise ValueError("Each step must have a 'type' field")
            
            t = step["type"]
            if t == "email":
                if "to" not in step or "subject" not in step:
                    raise ValueError("Email step requires 'to' and 'subject'")
            elif t == "add_to_group":
                if "group_dn" not in step:
                    raise ValueError("Add to group step requires 'group_dn'")
            elif t == "webhook":
                if "url" not in step:
                    raise ValueError("Webhook step requires 'url'")
            elif t == "wait_for_approval":
                if "approver" not in step:
                    raise ValueError("Approval step requires 'approver'")
        return v

# --- Schema ---

STEP_SCHEMA = {
    "email": {
        "label": "Отправить Email",
        "icon": "fa-envelope",
        "fields": [
            {"name": "to", "label": "Кому", "type": "text", "placeholder": "user@example.com"},
            {"name": "subject", "label": "Тема", "type": "text", "placeholder": "Важное уведомление"},
            {"name": "body", "label": "Текст", "type": "textarea", "placeholder": "Текст сообщения..."}
        ]
    },
    "add_to_group": {
        "label": "Добавить в группу",
        "icon": "fa-users",
        "fields": [
            {"name": "group_dn", "label": "DN группы", "type": "text", "placeholder": "CN=Managers,OU=Groups..."}
        ]
    },
    "webhook": {
        "label": "Webhook",
        "icon": "fa-globe",
        "fields": [
            {"name": "url", "label": "URL", "type": "text", "placeholder": "https://api.example.com/hook"},
            {"name": "method", "label": "Метод", "type": "select", "options": ["POST", "GET", "PUT"]},
            {"name": "payload", "label": "Данные (JSON)", "type": "textarea", "placeholder": "{...}"}
        ]
    },
    "wait_for_approval": {
        "label": "Ждать согласования",
        "icon": "fa-check-double",
        "fields": [
            {"name": "approver", "label": "Согласующий (Login/Role)", "type": "text", "placeholder": "admin"}
        ]
    }
}

# --- Helpers ---

def get_workflow_path(wf_id: str):
    return settings.WORKFLOWS_DIR / f"{wf_id}.json"

def load_workflows():
    workflows = []
    if not settings.WORKFLOWS_DIR.exists():
        return workflows
    
    for f in settings.WORKFLOWS_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                # Добавляем ID из имени файла, если его нет внутри (хотя лучше хранить внутри)
                if "id" not in data:
                    data["id"] = f.stem
                workflows.append(data)
        except Exception:
            pass
    return workflows

# --- Endpoints ---

@router.get("/", response_model=List[WorkflowModel])
def list_workflows(user=Depends(PermissionChecker("workflows:read"))):
    """Список всех workflow"""
    return load_workflows()

@router.get("/schema")
def get_workflow_schema(user=Depends(PermissionChecker("workflows:read"))):
    """Схема доступных шагов для конструктора"""
    return STEP_SCHEMA

@router.post("/", response_model=WorkflowModel, status_code=status.HTTP_201_CREATED)
def create_workflow(wf: WorkflowModel, admin=Depends(PermissionChecker("workflows:manage"))):
    """Создание нового workflow"""
    if not wf.id:
        wf.id = str(uuid.uuid4())
    
    path = get_workflow_path(wf.id)
    if path.exists():
        raise HTTPException(status_code=400, detail="Workflow with this ID already exists")
    
    # Убедимся, что папка существует
    settings.WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wf.dict(), f, indent=2, ensure_ascii=False)
        
    return wf

@router.get("/{wf_id}", response_model=WorkflowModel)
def get_workflow(wf_id: str, user=Depends(PermissionChecker("workflows:read"))):
    """Получение workflow по ID"""
    path = get_workflow_path(wf_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        if "id" not in data: data["id"] = wf_id
        return data

@router.put("/{wf_id}", response_model=WorkflowModel)
def update_workflow(wf_id: str, wf: WorkflowModel, admin=Depends(PermissionChecker("workflows:manage"))):
    """Обновление workflow"""
    path = get_workflow_path(wf_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # ID в URL должен совпадать с ID в теле (или перезаписываем)
    wf.id = wf_id
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wf.dict(), f, indent=2, ensure_ascii=False)
        
    return wf

@router.delete("/{wf_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(wf_id: str, admin=Depends(PermissionChecker("workflows:manage"))):
    """Удаление workflow"""
    path = get_workflow_path(wf_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    path.unlink()
    return

@router.post("/{wf_id}/execute")
def execute_workflow(wf_id: str, context: Dict[str, Any] = {}, admin=Depends(PermissionChecker("workflows:execute"))):
    """Ручной запуск workflow"""
    path = get_workflow_path(wf_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    with open(path, "r", encoding="utf-8") as f:
        wf_data = json.load(f)
        
    # Запускаем шаги
    # В реальной ситуации лучше запускать асинхронно через workflow_engine
    # Но workflow_engine.trigger работает по событию, а тут прямой запуск шагов
    
    # Используем приватный метод _execute_steps для прямого запуска
    # Или добавим публичный метод в engine
    try:
        workflow_engine._execute_steps(wf_data.get("steps", []), context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution failed: {e}")
        
    return {"status": "executed"}

# --- Approval Endpoints ---

from backend.services.approval_service import approval_service
from backend.db.database import get_db

class ApprovalDecision(BaseModel):
    comment: Optional[str] = None

@router.get("/approvals/pending")
def list_pending_approvals(
    user: dict = Depends(PermissionChecker("approvals:read")),
    db: Session = Depends(get_db)
):
    """Список ожидающих заявок"""
    # В будущем фильтровать по user['role'] или user['username']
    return approval_service.get_pending_requests(db)

@router.post("/approvals/{req_id}/approve")
def approve_request(
    req_id: int,
    decision: ApprovalDecision,
    user: dict = Depends(PermissionChecker("approvals:action")),
    db: Session = Depends(get_db)
):
    """Подтверждение заявки"""
    try:
        req = approval_service.process_request(db, req_id, user["username"], "APPROVED", decision.comment)
        
        # Если это был шаг workflow, нужно продолжить выполнение
        # Но пока у нас простая реализация: просто меняем статус
        # В будущем: workflow_engine.resume(req.payload['workflow_id'], ...)
        
        return {"status": "approved", "id": req.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/approvals/{req_id}/reject")
def reject_request(
    req_id: int,
    decision: ApprovalDecision,
    user: dict = Depends(PermissionChecker("approvals:action")),
    db: Session = Depends(get_db)
):
    """Отклонение заявки"""
    try:
        req = approval_service.process_request(db, req_id, user["username"], "REJECTED", decision.comment)
        return {"status": "rejected", "id": req.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
