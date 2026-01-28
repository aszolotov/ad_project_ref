from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from backend.core.config import settings
from backend.routers.auth import get_current_user
from backend.services.ldap_service import ldap_service

router = APIRouter(prefix=f"{settings.API_V1_STR}/me", tags=["self-service"])

class UserProfileUpdate(BaseModel):
    telephoneNumber: str = None
    physicalDeliveryOfficeName: str = None
    description: str = None

class PasswordChange(BaseModel):
    old_password: str
    new_password: str

@router.get("")
def get_my_profile(current_user: dict = Depends(get_current_user)):
    """
    Получение профиля текущего пользователя.
    """
    # current_user уже содержит данные из токена, но лучше получить свежие из AD
    try:
        user_dn = current_user.get("dn")
        if not user_dn:
            raise HTTPException(status_code=400, detail="User DN not found in token")
            
        user_data = ldap_service.get_user_details(user_dn)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found in AD")
            
        return user_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/update")
def update_my_profile(data: UserProfileUpdate, current_user: dict = Depends(get_current_user)):
    """
    Обновление профиля текущего пользователя (телефон, офис).
    """
    try:
        user_dn = current_user.get("dn")
        attributes = {}
        if data.telephoneNumber is not None:
            attributes["telephoneNumber"] = data.telephoneNumber
        if data.physicalDeliveryOfficeName is not None:
            attributes["physicalDeliveryOfficeName"] = data.physicalDeliveryOfficeName
        if data.description is not None:
            attributes["description"] = data.description
            
        if not attributes:
            return {"status": "no changes"}
            
        ldap_service.update_user(user_dn, attributes)
        return {"status": "success", "updated": attributes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/password")
def change_my_password(data: PasswordChange, current_user: dict = Depends(get_current_user)):
    """
    Смена собственного пароля.
    """
    try:
        user_dn = current_user.get("dn")
        # В реальной ситуации нужно проверять старый пароль через bind
        # ldap_service.verify_password(user_dn, data.old_password)
        
        ldap_service.change_password(user_dn, data.new_password)
        return {"status": "success", "message": "Password changed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
