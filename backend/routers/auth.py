# backend/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from ldap3 import Server, Connection, SIMPLE, ALL
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.security import create_access_token, decode_access_token
from backend.db.database import get_db
from backend.services.audit_service import log_event
from backend.services.ldap_service import ldap_service

from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import Optional
import logging

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix=settings.API_V1_STR, tags=["auth"])

def try_bind(user_dn: str, password: str) -> bool:
    """Попытка подключения к LDAP с указанными учетными данными"""
    if not password: return False
    server = Server(settings.AD_SERVER, get_info=ALL)
    try:
        # auto_bind=True выполнит попытку входа сразу при создании
        conn = Connection(
            server,
            user=user_dn,
            password=password,
            authentication=SIMPLE,
            auto_bind=True
        )
        conn.unbind()
        return True
    except Exception:
        return False

@router.post("/token")
@limiter.limit("5/minute")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    username = form_data.username.strip()
    password = form_data.password
    
    # 1. Формируем варианты логина (UPN, DOMAIN\User, просто User)
    candidates = []
    if "\\" in username or "@" in username:
        candidates.append(username)
    else:
        candidates.append(f"{settings.AD_DOMAIN}\\{username}")
        # Формируем UPN: user@domain.local
        domain_suffix = settings.AD_BASE_DN.lower().replace("dc=", "").replace(",", ".")
        candidates.append(f"{username}@{domain_suffix}")
        
    # 2. Перебираем варианты авторизации
    success_dn = None
    for candidate in candidates:
        if try_bind(candidate, password):
            success_dn = candidate
            break
            
    # 3. Если ни один не подошел
    if not success_dn:
        # ИСПРАВЛЕНО: используем параметр 'user' вместо 'username'
        log_event(db, user=username, action="LOGIN", target="system",
                  details={"reason": "invalid_credentials", "tried": candidates}, 
                  ip=request.client.host, status="FAIL")
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. Успешный вход
    role = "admin" if any(x in username.lower() for x in ["admin", "it_", "administrator"]) else "user"
    access_token = create_access_token(subject=username, role=role)
    
    # ИСПРАВЛЕНО: используем параметр 'user' вместо 'username'
    log_event(db, user=username, action="LOGIN", target="system",
              details={"role": role, "bind_as": success_dn}, 
              ip=request.client.host, status="SUCCESS")

    return {"access_token": access_token, "token_type": "bearer", "role": role}

def get_current_user(request: Request) -> dict:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    
    token = auth_header.split(" ", 1)[1]
    payload = decode_access_token(token)
    
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
    return {"username": payload["sub"], "role": payload.get("role", "user")}

    return {"username": payload["sub"], "role": payload.get("role", "user")}

from backend.core.security import ROLES

def has_permission(user_role: str, required_perm: str) -> bool:
    if user_role not in ROLES: return False
    perms = ROLES[user_role]
    if "*" in perms: return True
    return required_perm in perms

class PermissionChecker:
    def __init__(self, required_perm: str):
        self.required_perm = required_perm

    def __call__(self, user: dict = Depends(get_current_user)):
        if not has_permission(user["role"], self.required_perm):
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission denied: {self.required_perm}")
        return user

def require_admin(user: dict = Depends(get_current_user)) -> dict:
    # Backward compatibility
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user

class SelfPasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str

from pydantic import BaseModel

@router.post("/self/password")
@limiter.limit("5/minute")
def change_self_password(
    req: SelfPasswordChangeRequest,
    request: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Смена собственного пароля пользователем.
    """
    username = user["username"]
    
    # 1. Проверяем старый пароль (пытаемся сделать bind)
    # Нам нужно найти DN пользователя, чтобы сделать bind
    # В токене у нас есть username (sAMAccountName или UPN)
    
    # Ищем пользователя в AD, чтобы получить DN
    try:
        entries = ldap_service.search_users(query=username)
        if not entries:
             raise HTTPException(status_code=404, detail="User not found in AD")
        
        # Берем первого (обычно он один)
        # Но надо проверить, что sAMAccountName или UPN совпадают
        user_entry = None
        for e in entries:
            if str(e.sAMAccountName).lower() == username.lower() or \
               str(e.userPrincipalName).lower() == username.lower():
                user_entry = e
                break
        
        if not user_entry:
             # Если не нашли точного совпадения, пробуем просто первого, если поиск был точным
             user_entry = entries[0]

        user_dn = user_entry.distinguishedName.value
        
    except Exception as e:
        logger.error(f"Error finding user for pwd change: {e}")
        raise HTTPException(status_code=500, detail="Internal LDAP Error")

    # Проверяем старый пароль
    if not try_bind(user_dn, req.old_password):
        log_event(db, user=username, action="SELF_PWD_CHANGE", target="self", 
                  details={"status": "wrong_old_password"}, ip=request.client.host, status="FAIL")
        raise HTTPException(status_code=400, detail="Неверный текущий пароль")

    # 2. Меняем пароль
    new_pwd_encoded = f'"{req.new_password}"'.encode("utf-16-le")
    try:
        ldap_service.modify_user(user_dn, {
            "unicodePwd": new_pwd_encoded
        })
    except Exception as e:
        log_event(db, user=username, action="SELF_PWD_CHANGE", target="self", 
                  details={"error": str(e)}, ip=request.client.host, status="FAIL")
        raise HTTPException(status_code=400, detail=f"Ошибка смены пароля: {e}")

    log_event(db, user=username, action="SELF_PWD_CHANGE", target="self", 
              details={"status": "success"}, ip=request.client.host, status="SUCCESS")
    
    return {"status": "ok", "message": "Пароль успешно изменен"}

class UserSelfUpdate(BaseModel):
    telephoneNumber: Optional[str] = None
    physicalDeliveryOfficeName: Optional[str] = None
    description: Optional[str] = None
    # Другие безопасные поля

@router.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    """
    Получение информации о текущем пользователе.
    """
    try:
        # Ищем пользователя в AD
        entry = ldap_service.find_user_by_identifier(user["username"])
        if not entry:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Собираем данные
        user_data = {
            "username": str(entry.sAMAccountName),
            "displayName": str(entry.displayName) if entry.displayName else "",
            "mail": str(entry.mail) if entry.mail else "",
            "title": str(entry.title) if entry.title else "",
            "department": str(entry.department) if entry.department else "",
            "telephoneNumber": str(entry.telephoneNumber) if hasattr(entry, "telephoneNumber") and entry.telephoneNumber else "",
            "office": str(entry.physicalDeliveryOfficeName) if hasattr(entry, "physicalDeliveryOfficeName") and entry.physicalDeliveryOfficeName else "",
            "description": str(entry.description) if entry.description else "",
            "manager": str(entry.manager) if hasattr(entry, "manager") and entry.manager else "",
            "role": user["role"]
        }
        return user_data
    except Exception as e:
        logger.error(f"Error getting self info: {e}")
        raise HTTPException(status_code=500, detail="Internal Error")

@router.post("/me/update")
def update_me(
    req: UserSelfUpdate,
    request: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Обновление профиля пользователем.
    """
    try:
        entry = ldap_service.find_user_by_identifier(user["username"])
        if not entry:
            raise HTTPException(status_code=404, detail="User not found")
            
        dn = entry.distinguishedName.value
        
        changes = {}
        if req.telephoneNumber is not None:
            changes["telephoneNumber"] = req.telephoneNumber
        if req.physicalDeliveryOfficeName is not None:
            changes["physicalDeliveryOfficeName"] = req.physicalDeliveryOfficeName
        if req.description is not None:
            changes["description"] = req.description
            
        if not changes:
            return {"status": "ok", "message": "No changes"}
            
        ldap_service.modify_user(dn, changes)
        
        log_event(db, user=user["username"], action="SELF_UPDATE", target="self", 
                  details=changes, ip=request.client.host, status="SUCCESS")
                  
        return {"status": "ok", "message": "Профиль обновлен"}
        
    except Exception as e:
        logger.error(f"Error updating self info: {e}")
        raise HTTPException(status_code=500, detail=f"Update Error: {e}")
