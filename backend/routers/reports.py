from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from backend.core.config import settings
from backend.routers.auth import PermissionChecker
from backend.services.ldap_service import ldap_service

router = APIRouter(prefix=f"{settings.API_V1_STR}/reports", tags=["reports"])

class ReportFilter(BaseModel):
    field: str
    operator: str  # equals, contains, starts_with, ends_with, not_equals
    value: str

class ReportRequest(BaseModel):
    attributes: List[str]
    filters: List[ReportFilter]
    scope: str = "SUBTREE"  # BASE, ONELEVEL, SUBTREE
    base_dn: Optional[str] = None

@router.post("/generate")
def generate_report(req: ReportRequest, user=Depends(PermissionChecker("reports:read"))):
    """
    Генерация отчета по заданным критериям.
    Позволяет выбирать атрибуты и фильтровать объекты.
    """
    
    # 1. Строим LDAP фильтр
    ldap_filter_parts = ["(objectClass=user)"] # Пока только пользователи, можно расширить
    
    for f in req.filters:
        if f.operator == "equals":
            ldap_filter_parts.append(f"({f.field}={f.value})")
        elif f.operator == "contains":
            ldap_filter_parts.append(f"({f.field}=*{f.value}*)")
        elif f.operator == "starts_with":
            ldap_filter_parts.append(f"({f.field}={f.value}*)")
        elif f.operator == "ends_with":
            ldap_filter_parts.append(f"({f.field}=*{f.value})")
        elif f.operator == "not_equals":
            ldap_filter_parts.append(f"(!({f.field}={f.value}))")
            
    ldap_filter = f"(&{''.join(ldap_filter_parts)})"
    
    # 2. Определяем Base DN
    search_base = req.base_dn if req.base_dn else settings.LDAP_BASE_DN
    
    # 3. Выполняем поиск
    # ldap_service.search возвращает список словарей
    # Нам нужно убедиться, что запрошенные атрибуты есть в attributes списка
    
    # Добавляем 'cn' всегда для идентификации
    attrs_to_fetch = list(set(req.attributes + ["cn"]))
    
    try:
        results = ldap_service.search(
            base_dn=search_base,
            filter_str=ldap_filter,
            attributes=attrs_to_fetch
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LDAP Search failed: {str(e)}")
        
    # 4. Форматируем результат
    # Оставляем только запрошенные поля
    formatted_results = []
    for entry in results:
        row = {}
        for attr in req.attributes:
            # LDAP возвращает списки значений или одно значение
            # Приведем к строке для отчета
            val = entry.get(attr)
            if isinstance(val, list):
                row[attr] = ", ".join([str(v) for v in val])
            elif val is None:
                row[attr] = ""
            else:
                row[attr] = str(val)
        formatted_results.append(row)
        
    return {
        "count": len(formatted_results),
        "filter": ldap_filter,
        "data": formatted_results
    }

@router.get("/schema")
def get_report_schema(user=Depends(PermissionChecker("reports:read"))):
    """
    Возвращает доступные атрибуты и операторы для построения отчетов.
    """
    return {
        "attributes": [
            {"name": "cn", "label": "Common Name"},
            {"name": "sAMAccountName", "label": "Login"},
            {"name": "mail", "label": "Email"},
            {"name": "title", "label": "Job Title"},
            {"name": "department", "label": "Department"},
            {"name": "company", "label": "Company"},
            {"name": "telephoneNumber", "label": "Phone"},
            {"name": "mobile", "label": "Mobile"},
            {"name": "physicalDeliveryOfficeName", "label": "Office"},
            {"name": "userAccountControl", "label": "UAC (Status)"},
            {"name": "whenCreated", "label": "Created Date"},
            {"name": "lastLogon", "label": "Last Logon"}
        ],
        "operators": [
            {"name": "equals", "label": "Равно (=)"},
            {"name": "contains", "label": "Содержит (*val*)"},
            {"name": "starts_with", "label": "Начинается с (val*)"},
            {"name": "ends_with", "label": "Заканчивается на (*val)"},
            {"name": "not_equals", "label": "Не равно (!=)"}
        ]
    }

@router.get("/templates")
def get_report_templates(user=Depends(PermissionChecker("reports:read"))):
    """
    Возвращает список готовых шаблонов отчетов.
    """
    return [
        {
            "id": "locked_users",
            "name": "Заблокированные пользователи",
            "description": "Пользователи, у которых стоит статус Locked Out",
            "attributes": ["cn", "sAMAccountName", "mail", "department", "lockoutTime"],
            "filters": [
                {"field": "lockoutTime", "operator": "not_equals", "value": "0"}
            ]
        },
        {
            "id": "password_expiring",
            "name": "Скоро истекает пароль",
            "description": "Пользователи, которым нужно сменить пароль",
            "attributes": ["cn", "sAMAccountName", "mail", "pwdLastSet"],
            "filters": [
                {"field": "pwdLastSet", "operator": "not_equals", "value": "-1"} 
            ]
        },
        {
            "id": "empty_groups",
            "name": "Пустые группы",
            "description": "Группы безопасности без участников",
            "attributes": ["cn", "description", "whenCreated"],
            "filters": [
                {"field": "member", "operator": "equals", "value": ""} # Mock logic
            ]
        },
        {
            "id": "vip_users",
            "name": "VIP Пользователи",
            "description": "Руководители и директора",
            "attributes": ["cn", "title", "telephoneNumber", "mobile"],
            "filters": [
                {"field": "title", "operator": "contains", "value": "Director"}
            ]
        }
    ]
