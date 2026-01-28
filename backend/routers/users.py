# backend/routers/users.py
import urllib.parse
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ldap3 import MODIFY_ADD, MODIFY_DELETE, MODIFY_REPLACE

from backend.core.config import settings
from backend.db.database import get_db
from backend.routers.auth import get_current_user, require_admin, PermissionChecker
from backend.core.security import verify_scope
# Важно: импортируем ldap_pool для прямых операций с соединением
from backend.services.ldap_service import ldap_service, ldap_pool
from backend.services.audit_service import log_event
from backend.services.backup_service import backup_service
from backend.services.workflow_engine import workflow_engine

from slowapi import Limiter
from slowapi.util import get_remote_address
import pandas as pd
import io
from starlette.responses import StreamingResponse

limiter = Limiter(key_func=get_remote_address)

# Префикс маршрута: /api/v6/ad/users
router = APIRouter(prefix=f"{settings.API_V1_STR}/ad/users", tags=["users"])

# --- Pydantic Models (Схемы данных) ---

class UserCreate(BaseModel):
    givenName: str
    sn: str
    sAMAccountName: str
    password: Optional[str] = None
    ou: str
    title: Optional[str] = None
    department: Optional[str] = None
    mail: Optional[str] = None
    enabled: bool = True

class UserUpdate(BaseModel):
    givenName: Optional[str] = None
    sn: Optional[str] = None
    title: Optional[str] = None
    department: Optional[str] = None
    mail: Optional[str] = None
    enabled: Optional[bool] = None

class PasswordResetRequest(BaseModel):
    new_password: str

class UserGroupsChangeRequest(BaseModel):
    add: List[str] = []
    remove: List[str] = []

class BulkActionRequest(BaseModel):
    dns: List[str]
    action: str  # 'enable' или 'disable'


# --- Endpoints (Обработчики запросов) ---

@router.get("/")
def list_users(
    query: Optional[str] = Query(None, alias="q"),
    filterType: Optional[str] = Query(None, alias="status"),
    ou: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    user=Depends(PermissionChecker("users:read")),
):
    """
    Получение списка пользователей с фильтрацией, поиском и пагинацией.
    """
    # 1. Оптимизация поиска: если нужен только активные, говорим об этом LDAP сервису
    active_only_search = (filterType == "active")
    entries = ldap_service.search_users(query=query or "", ou=ou, active_only=active_only_search)
    
    # 2. Пост-фильтрация (для статуса 'disabled' или уточнения)
    filtered_entries = []
    for e in entries:
        # Получаем флаги UserAccountControl (UAC)
        uac = int(e.userAccountControl.value or 0) if e.userAccountControl else 0
        is_disabled = (uac & 2) == 2  # 2-й бит отвечает за отключение
        
        if filterType == "disabled" and not is_disabled:
            continue
        if filterType == "active" and is_disabled:
            continue
            
        filtered_entries.append(e)
        
    entries = filtered_entries

    # 3. Сортировка (важно для предсказуемой пагинации)
    # Сортируем по DisplayName, если пусто - по sAMAccountName
    entries.sort(key=lambda x: (str(x.displayName) if x.displayName else str(x.sAMAccountName)).lower())

    # 4. Пагинация
    total = len(entries)
    start = (page - 1) * page_size
    end = start + page_size
    page_entries = entries[start:end]

    # 5. Формирование ответа для фронтенда
    result = []
    for e in page_entries:
        uac = int(e.userAccountControl.value or 0) if e.userAccountControl else 0
        disabled = (uac & 2) == 2
        result.append({
            "dn": e.distinguishedName.value,
            "login": str(e.sAMAccountName) if e.sAMAccountName else "",
            "displayName": str(e.displayName) if e.displayName else "",
            "mail": str(e.mail) if e.mail else "",
            "department": str(e.department) if e.department else "",
            "title": str(e.title) if e.title else "",
            "disabled": disabled,
        })

    return {
        "users": result,
        "total": total,
        "page": page,
        "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 1,
    }


@router.get("/{dn}")
def get_user(dn: str, user=Depends(PermissionChecker("users:read"))):
    """
    Получение детальной информации об одном пользователе.
    """
    dn = urllib.parse.unquote(dn) # Декодируем DN из URL (на всякий случай)

    entries = ldap_service.search(dn, "(objectClass=user)", attributes=[
        "givenName", "sn", "sAMAccountName", "title", "department",
        "mail", "userAccountControl", "distinguishedName"
    ], scope="BASE")

    if not entries:
        raise HTTPException(status_code=404, detail="User not found")

    e = entries[0]
    uac = int(e.userAccountControl.value or 0) if e.userAccountControl else 0
    
    return {
        "dn": e.distinguishedName.value,
        "givenName": str(e.givenName) if e.givenName else "",
        "sn": str(e.sn) if e.sn else "",
        "sAMAccountName": str(e.sAMAccountName) if e.sAMAccountName else "",
        "title": str(e.title) if e.title else "",
        "department": str(e.department) if e.department else "",
        "mail": str(e.mail) if e.mail else "",
        "enabled": not ((uac & 2) == 2),
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def create_user(
    req: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(PermissionChecker("users:create")),
):
    """
    Создание нового пользователя.
    """
    # Проверка безопасности: нельзя создавать пользователей где попало
    if settings.ALLOWED_OUS and not any(req.ou.endswith(x) for x in settings.ALLOWED_OUS):
        # Логируем попытку нарушения
        log_event(db, user=admin["username"], action="CREATE_USER_FAIL", target="restricted_ou", details={"ou": req.ou}, ip=request.client.host, status="FAIL")
        raise HTTPException(status_code=403, detail="Создание пользователей в этом OU запрещено настройками безопасности.")

    cn = f"{req.givenName} {req.sn}"
    dn = f"CN={cn},{req.ou}"

    # Базовые атрибуты
    attrs = {
        "objectClass": ["top", "person", "organizationalPerson", "user"],
        "givenName": req.givenName,
        "sn": req.sn,
        "displayName": cn,
        "sAMAccountName": req.sAMAccountName,
        "userPrincipalName": f"{req.sAMAccountName}@{settings.AD_DOMAIN.lower()}.local",
        # 512 = Enabled, 514 = Disabled (Normal Account + 2)
        "userAccountControl": "512" if req.enabled else "514"
    }
    if req.mail: attrs["mail"] = req.mail
    if req.title: attrs["title"] = req.title
    if req.department: attrs["department"] = req.department

    try:
        ldap_service.create_user(dn, attrs)

        # Если задан пароль, его нужно устанавливать отдельно через modify
        if req.password:
            pwd = f'"{req.password}"'.encode("utf-16-le")
            ldap_service.modify_user(dn, {"unicodePwd": pwd})
            
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"LDAP Create Error: {e}")

    # Логируем и запускаем воркфлоу
    log_event(db, user=admin["username"], action="CREATE_USER", target=dn, details=req.dict(), ip=request.client.host)
    workflow_engine.trigger("post_create", {"dn": dn, **req.dict()})
    
    return {"dn": dn}


@router.patch("/{dn}")
def update_user(
    dn: str,
    req: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(PermissionChecker("users:update")),
):
    """
    Обновление данных пользователя.
    """
    """
    dn = urllib.parse.unquote(dn)
    
    # 1. Проверка прав доступа (Scope)
    if not verify_scope(admin["username"], dn):
        raise HTTPException(status_code=403, detail="Access denied: Object is out of your scope")

    changes = {k: v for k, v in req.dict().items() if v is not None and k != "enabled"}
    
    # Логика включения/выключения аккаунта
    if req.enabled is not None:
        try:
            # Сначала читаем текущий статус
            entries = ldap_service.search(dn, "(objectClass=*)", attributes=["userAccountControl"], scope="BASE")
            if entries:
                current_uac = int(entries[0].userAccountControl.value or 0)
                if req.enabled:
                    new_uac = current_uac & ~2 # Сброс бита 2 (включить)
                else:
                    new_uac = current_uac | 2  # Установка бита 2 (выключить)
                changes["userAccountControl"] = str(new_uac)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error reading UAC: {e}", exc_info=True)

    if not changes:
        return {"status": "no_changes"}

    # 2. Получаем текущие данные для вычисления разницы (Diff)
    old_user_data = {}
    try:
        user_entry = ldap_service.get_user(dn)
        if user_entry:
            old_user_data = user_entry.entry_attributes_as_dict
    except Exception:
        pass

    try:
        # Делаем бэкап перед изменением
        backup_service.create_snapshot([dn], "update_user", admin["username"])
        ldap_service.modify_user(dn, changes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"LDAP Update Error: {e}")

    # 3. Вычисляем Diff
    diff = {}
    for key, new_val in changes.items():
        old_val = old_user_data.get(key)
        # LDAP возвращает списки, приводим к строке для сравнения
        if isinstance(old_val, list) and len(old_val) > 0:
            old_val = str(old_val[0])
        elif isinstance(old_val, list):
            old_val = ""
        else:
            old_val = str(old_val) if old_val is not None else ""
            
        if str(new_val) != old_val:
            diff[key] = {"old": old_val, "new": str(new_val)}

    log_event(db, user=admin["username"], action="UPDATE_USER", target=dn, details=diff, ip=request.client.host)
    workflow_engine.trigger("post_modify", {"dn": dn, **changes})
    
    return {"status": "ok"}


@router.delete("/{dn}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    dn: str,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(PermissionChecker("users:delete")),
):
    """
    Удаление пользователя.
    """
    dn = urllib.parse.unquote(dn)
    
    # 1. Проверка прав доступа (Scope)
    if not verify_scope(admin["username"], dn):
        raise HTTPException(status_code=403, detail="Access denied: Object is out of your scope")
    
    # Бэкап перед удалением обязателен
    backup_service.create_snapshot([dn], "delete_user", admin["username"])
    
    try:
        ldap_service.delete_object(dn)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"LDAP Delete Error: {e}")

    log_event(db, user=admin["username"], action="DELETE_USER", target=dn, details={}, ip=request.client.host)
    workflow_engine.trigger("post_delete", {"dn": dn})
    return


@router.post("/{dn}/reset-password")
def reset_password(
    dn: str,
    req: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(PermissionChecker("users:reset_password")),
):
    """
    Сброс пароля пользователя.
    """
    """
    dn = urllib.parse.unquote(dn)

    # 1. Проверка прав доступа (Scope)
    if not verify_scope(admin["username"], dn):
        raise HTTPException(status_code=403, detail="Access denied: Object is out of your scope")
    
    # Пароль в AD должен быть в кавычках и в кодировке UTF-16LE
    pwd = f'"{req.new_password}"'.encode("utf-16-le")
    
    try:
        # Меняем пароль и сразу сбрасываем флаг "Сменить пароль при входе" (pwdLastSet=0 -> требует смену, -1 -> не требует)
        # Обычно админы хотят pwdLastSet=0, чтобы юзер сменил временный пароль
        ldap_service.modify_user(dn, {
            "unicodePwd": pwd,
            "pwdLastSet": "0" 
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"LDAP Password Error: {e}")

    log_event(db, user=admin["username"], action="RESET_PWD", target=dn, details={}, ip=request.client.host)
    return {"status": "ok"}


@router.post("/{dn}/unlock")
def unlock_account(
    dn: str,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(PermissionChecker("users:unlock")),
):
    """
    Разблокировка учетной записи.
    """
    """
    dn = urllib.parse.unquote(dn)
    
    # 1. Проверка прав доступа (Scope)
    if not verify_scope(admin["username"], dn):
        raise HTTPException(status_code=403, detail="Access denied: Object is out of your scope")

    try:
        # Разблокировка = установка lockoutTime в 0
        ldap_service.modify_user(dn, {"lockoutTime": "0"})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"LDAP Unlock Error: {e}")

    log_event(db, user=admin["username"], action="UNLOCK", target=dn, details={}, ip=request.client.host)
    return {"status": "ok"}


# --- Управление группами ---

@router.get("/{dn}/groups")
def get_user_groups(dn: str, user=Depends(PermissionChecker("users:read"))):
    """
    Получение списка групп пользователя.
    """
    dn = urllib.parse.unquote(dn)
    # Ищем группы, в которых поле 'member' содержит DN пользователя
    filter_str = f"(&(objectClass=group)(member={dn}))"
    entries = ldap_service.search(settings.AD_BASE_DN, filter_str, attributes=["cn", "distinguishedName"])
    
    groups = [{"name": str(e.cn), "dn": e.distinguishedName.value} for e in entries]
    return {"groups": groups}


@router.post("/{dn}/groups")
def change_user_groups(
    dn: str,
    req: UserGroupsChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(PermissionChecker("users:update")),
):
    """
    Добавление и удаление пользователя из групп.
    """
    dn = urllib.parse.unquote(dn)
    
    # Для массовых операций лучше взять соединение из пула вручную,
    # чтобы не делать bind/unbind на каждую группу
    conn = ldap_pool.get_connection()
    try:
        for group_dn in req.add:
            conn.modify(group_dn, {'member': [(MODIFY_ADD, [dn])]})
            
        for group_dn in req.remove:
            conn.modify(group_dn, {'member': [(MODIFY_DELETE, [dn])]})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LDAP Group Modification Error: {e}")
    finally:
        # Обязательно возвращаем соединение в пул!
        ldap_pool.release(conn)
        
    log_event(db, user=admin["username"], action="CHANGE_GROUPS", target=dn, details=req.dict(), ip=request.client.host)
    return {"status": "ok"}


# --- Массовые действия ---

@router.post("/toggle")
@limiter.limit("10/minute")
def bulk_toggle_users(
    req: BulkActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(PermissionChecker("users:update")),
):
    """
    Массовое включение/выключение пользователей.
    """
    results = []
    for dn in req.dns:
        try:
            entries = ldap_service.search(dn, "(objectClass=*)", attributes=["userAccountControl"], scope="BASE")
            if not entries:
                results.append({"dn": dn, "status": "not_found"})
                continue
                
            current_uac = int(entries[0].userAccountControl.value or 0)
            if req.action == "disable":
                new_uac = current_uac | 2
            else: # enable
                new_uac = current_uac & ~2
                
            ldap_service.modify_user(dn, {"userAccountControl": str(new_uac)})
            results.append({"dn": dn, "status": "ok"})
        except Exception as e:
            results.append({"dn": dn, "status": f"error: {e}"})

    log_event(
        db, 
        user=admin["username"], 
        action=f"BULK_{req.action.upper()}", 
        target="bulk_selection", 
        details={"count": len(req.dns), "results": results}, 
        ip=request.client.host
    )
    
    return {"results": results}


@router.get("/export")
def export_users(
    format: str = Query("csv", regex="^(csv|xlsx)$"),
    query: Optional[str] = Query(None, alias="q"),
    filterType: Optional[str] = Query(None, alias="status"),
    ou: Optional[str] = None,
    user=Depends(PermissionChecker("users:read")),
):
    """
    Экспорт пользователей в CSV или Excel.
    """
    # 1. Получаем данные (аналогично list_users, но без пагинации)
    active_only_search = (filterType == "active")
    entries = ldap_service.search_users(query=query or "", ou=ou, active_only=active_only_search)
    
    filtered_entries = []
    for e in entries:
        uac = int(e.userAccountControl.value or 0) if e.userAccountControl else 0
        is_disabled = (uac & 2) == 2
        
        if filterType == "disabled" and not is_disabled:
            continue
        if filterType == "active" and is_disabled:
            continue
            
        filtered_entries.append({
            "Login": str(e.sAMAccountName) if e.sAMAccountName else "",
            "Display Name": str(e.displayName) if e.displayName else "",
            "Email": str(e.mail) if e.mail else "",
            "Department": str(e.department) if e.department else "",
            "Title": str(e.title) if e.title else "",
            "Status": "Disabled" if is_disabled else "Active",
            "DN": e.distinguishedName.value
        })
        
    df = pd.DataFrame(filtered_entries)
    
    if format == "csv":
        stream = io.StringIO()
        df.to_csv(stream, index=False)
        response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
        response.headers["Content-Disposition"] = "attachment; filename=users_export.csv"
        return response
        
    elif format == "xlsx":
        stream = io.BytesIO()
        with pd.ExcelWriter(stream, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Users')
        stream.seek(0)
        
        response = StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response.headers["Content-Disposition"] = "attachment; filename=users_export.xlsx"
        return response
