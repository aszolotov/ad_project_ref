from datetime import datetime, timedelta
from typing import Optional, Union, Any
from jose import jwt
from .config import settings

def create_access_token(subject: Union[str, Any], role: str = "user") -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"exp": expire, "sub": str(subject), "role": role}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.JWTError:
        return None



# Role-Based Access Control
ROLES = {
    "admin": ["*"],
    "user": ["self:read", "self:update", "directory:read"],
    "helpdesk": [
        "users:read", "users:reset_password", "users:unlock", 
        "computers:read", "computers:disable",
        "directory:read",
        "groups:read",
        "reports:read"
    ],
    "manager": [
        "approvals:read", "approvals:action",
        "directory:read",
        "reports:read",
        "workflows:read"
    ],
    "auditor": [
        "audit:read",
        "reports:read",
        "logs:read"
    ]
}

# Mock Scopes (User -> Allowed OU DN)
# В реальной системе это хранилось бы в БД или claims токена
USER_SCOPES = {
    "helpdesk_moscow": "OU=Moscow,DC=vibe,DC=local",
    "manager_sales": "OU=Sales,DC=vibe,DC=local"
}

def verify_scope(user_dn: str, target_dn: str) -> bool:
    """
    Проверяет, имеет ли пользователь право управлять целевым объектом.
    Если у пользователя нет ограничений (нет в USER_SCOPES), возвращает True.
    Если есть ограничение, проверяет, заканчивается ли target_dn на scope_dn.
    """
    # Получаем логин из DN (упрощенно, считаем что user_dn это login или full DN)
    # В нашем mock auth мы используем login как идентификатор
    login = user_dn 
    
    if login not in USER_SCOPES:
        return True
        
    scope = USER_SCOPES[login]
    return target_dn.lower().endswith(scope.lower())
