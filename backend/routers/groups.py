import urllib.parse
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.database import get_db
from backend.routers.auth import get_current_user, require_admin, PermissionChecker
from backend.services.ldap_service import ldap_service, ldap_pool
from backend.services.audit_service import log_event

router = APIRouter(prefix=f"{settings.API_V1_STR}/ad/groups", tags=["groups"])

class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    scope: str = "Global" # Global, Universal, DomainLocal
    type: str = "Security" # Security, Distribution
    ou: Optional[str] = None # Если не задан, используется дефолтный Users

@router.get("/")
def list_groups(
    query: Optional[str] = None,
    user=Depends(PermissionChecker("groups:read"))
):
    """Список групп с фильтрацией"""
    ldap_filter = "(objectClass=group)"
    if query:
        ldap_filter = f"(&(objectClass=group)(cn=*{query}*))"
        
    entries = ldap_service.search(settings.AD_BASE_DN, ldap_filter, attributes=["cn", "description", "member", "distinguishedName"])
    
    result = []
    for e in entries:
        members = e.member.values if e.member else []
        result.append({
            "dn": e.distinguishedName.value,
            "name": str(e.cn),
            "description": str(e.description) if e.description else "",
            "member_count": len(members)
        })
        
    return result

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_group(
    req: GroupCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(PermissionChecker("groups:create"))
):
    """Создание новой группы"""
    # Определяем OU
    parent_dn = req.ou if req.ou else f"CN=Users,{settings.AD_BASE_DN}"
    dn = f"CN={req.name},{parent_dn}"
    
    attrs = {
        "objectClass": ["top", "group"],
        "cn": req.name,
        "sAMAccountName": req.name,
    }
    if req.description:
        attrs["description"] = req.description
        
    # groupType
    # Security Global = 0x80000002 = -2147483646
    # Distribution Global = 0x2 = 2
    # Это упрощенно, для полноценной поддержки нужно маппить все типы
    # Пока сделаем Security Global по умолчанию
    attrs["groupType"] = "-2147483646" 
    
    try:
        ldap_service.create_object(dn, attrs)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"LDAP Error: {e}")
        
    log_event(db, user=admin["username"], action="CREATE_GROUP", target=dn, details=req.dict(), ip=request.client.host)
    return {"dn": dn}

@router.delete("/{dn}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    dn: str,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(PermissionChecker("groups:delete"))
):
    """Удаление группы"""
    dn = urllib.parse.unquote(dn)
    try:
        ldap_service.delete_object(dn)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"LDAP Error: {e}")
        
    log_event(db, user=admin["username"], action="DELETE_GROUP", target=dn, details={}, ip=request.client.host)
    return
