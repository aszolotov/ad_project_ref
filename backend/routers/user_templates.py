from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
import json
import os
from pathlib import Path
from pydantic import BaseModel

from backend.core.config import settings
from backend.routers.auth import PermissionChecker

router = APIRouter(prefix=f"{settings.API_V1_STR}/user-templates", tags=["user-templates"])

# Path to templates file
TEMPLATES_FILE = Path(__file__).parent.parent / "db" / "templates.json"

class UserTemplate(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    category: str
    default_values: Dict[str, Any]
    default_groups: List[str] = []

def load_templates() -> List[UserTemplate]:
    """Load templates from JSON file."""
    if not TEMPLATES_FILE.exists():
        return []
    
    with open(TEMPLATES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return [UserTemplate(**item) for item in data]

def save_templates(templates: List[UserTemplate]):
    """Save templates to JSON file."""
    with open(TEMPLATES_FILE, 'w', encoding='utf-8') as f:
        json.dump([t.dict() for t in templates], f, indent=2, ensure_ascii=False)

@router.get("", response_model=List[UserTemplate])
def get_user_templates(user=Depends(PermissionChecker("users:read"))):
    """
    Получить список всех шаблонов пользователей.
    """
    try:
        templates = load_templates()
        return templates
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load templates: {str(e)}")

@router.get("/{template_id}", response_model=UserTemplate)
def get_user_template(template_id: str, user=Depends(PermissionChecker("users:read"))):
    """
    Получить конкретный шаблон по ID.
    """
    templates = load_templates()
    template = next((t for t in templates if t.id == template_id), None)
    
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    
    return template

@router.post("", response_model=UserTemplate)
def create_user_template(
    template: UserTemplate,
    user=Depends(PermissionChecker("users:create"))
):
    """
    Создать новый шаблон пользователя.
    """
    templates = load_templates()
    
    # Check if ID already exists
    if any(t.id == template.id for t in templates):
        raise HTTPException(status_code=400, detail=f"Template with ID '{template.id}' already exists")
    
    templates.append(template)
    save_templates(templates)
    
    return template

@router.delete("/{template_id}")
def delete_user_template(
    template_id: str,
    user=Depends(PermissionChecker("users:delete"))
):
    """
    Удалить шаблон пользователя.
    """
    templates = load_templates()
    original_count = len(templates)
    
    templates = [t for t in templates if t.id != template_id]
    
    if len(templates) == original_count:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    
    save_templates(templates)
    
    return {"status": "success", "message": f"Template '{template_id}' deleted"}

@router.get("/categories/list")
def get_template_categories(user=Depends(PermissionChecker("users:read"))):
    """
    Получить список всех категорий шаблонов.
    """
    templates = load_templates()
    categories = list(set(t.category for t in templates))
    return {"categories": sorted(categories)}
