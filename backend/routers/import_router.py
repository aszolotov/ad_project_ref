# backend/routers/import_router.py
import io
import pandas as pd
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.routers.auth import get_current_user, require_admin, PermissionChecker
from backend.services.ldap_service import ldap_service, ldap_pool
from backend.services.audit_service import log_event
from backend.services.backup_service import backup_service
from backend.db.database import get_db
from ldap3.utils.conv import escape_filter_chars

router = APIRouter(prefix=f"{settings.API_V1_STR}", tags=["import"])


class MassUpdateItem(BaseModel):
    identifier: str  # sAMAccountName, employeeID, mail, или DN
    fields: Dict[str, Any]  # Словарь полей для обновления


class MassUpdateRequest(BaseModel):
    items: List[MassUpdateItem]


@router.post("/import-excel/")
async def import_excel(
    file: UploadFile = File(...),
    admin=Depends(PermissionChecker("import:execute")),
):
    """
    Загрузка и парсинг Excel файла для массового обновления.
    Возвращает колонки и данные для последующего маппинга.
    """
    # Проверка расширения файла
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Поддерживаются только файлы .xlsx и .xls")
    
    try:
        # Чтение файла
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
        
        # Замена NaN на пустые строки
        df = df.fillna('')
        
        # Конвертация в список словарей
        data = df.to_dict('records')
        
        # Получение списка колонок
        columns = df.columns.tolist()
        
        return {
            "status": "success",
            "columns": columns,
            "data": data,
            "rows": len(data)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка чтения Excel файла: {str(e)}")


@router.post("/mass-update-exec/")
def mass_update_exec(
    req: MassUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(PermissionChecker("import:execute")),
):
    """
    Массовое обновление пользователей AD на основе данных из Excel.
    Поддерживает rollback при ошибках.
    """
    if not req.items:
        raise HTTPException(status_code=400, detail="Список элементов для обновления пуст")
    
    # Создаем бэкап всех пользователей перед массовым обновлением
    all_dns = []
    backups = {}  # Словарь для хранения бэкапов: {dn: attributes}
    
    # Сначала находим всех пользователей и создаем бэкапы
    for item in req.items:
        user_entry = ldap_service.find_user_by_identifier(item.identifier)
        if user_entry:
            dn = user_entry.distinguishedName.value
            all_dns.append(dn)
            # Сохраняем текущие атрибуты в памяти для возможного rollback
            backups[dn] = {}
            for attr in ['department', 'title', 'mail', 'telephoneNumber', 'streetAddress', 'displayName']:
                if hasattr(user_entry, attr):
                    value = getattr(user_entry, attr)
                    if value:
                        backups[dn][attr] = str(value.value) if hasattr(value, 'value') else str(value)
    
    # Создаем файловый бэкап
    backup_filename = None
    if all_dns:
        backup_filename = backup_service.create_snapshot(all_dns, "mass_update", admin["username"])
    
    # Выполняем обновления с поддержкой rollback
    results = []
    updated_count = 0
    error_count = 0
    
    try:
        for item in req.items:
            try:
                # Поиск пользователя
                user_entry = ldap_service.find_user_by_identifier(item.identifier)
                
                if not user_entry:
                    results.append({
                        "identifier": item.identifier,
                        "status": "not_found",
                        "msg": f"Пользователь с идентификатором '{item.identifier}' не найден"
                    })
                    error_count += 1
                    continue
                
                dn = user_entry.distinguishedName.value
                
                # Подготовка изменений
                changes = {}
                for field, value in item.fields.items():
                    # Пропускаем пустые значения (если нужно обнулить - передать явно None)
                    if value is not None and str(value).strip():
                        # Маппинг полей Excel -> AD атрибуты
                        field_mapping = {
                            'department': 'department',
                            'title': 'title',
                            'mail': 'mail',
                            'email': 'mail',
                            'telephoneNumber': 'telephoneNumber',
                            'phone': 'telephoneNumber',
                            'streetAddress': 'streetAddress',
                            'address': 'streetAddress',
                            'displayName': 'displayName',
                            'name': 'displayName',
                            'givenName': 'givenName',
                            'sn': 'sn',
                            'surname': 'sn',
                        }
                        
                        ad_field = field_mapping.get(field.lower(), field)
                        changes[ad_field] = str(value).strip()
                
                if not changes:
                    results.append({
                        "identifier": item.identifier,
                        "status": "no_changes",
                        "msg": "Нет изменений для применения"
                    })
                    continue
                
                # Применяем изменения
                ldap_service.modify_user(dn, changes)
                
                results.append({
                    "identifier": item.identifier,
                    "status": "ok",
                    "dn": dn,
                    "msg": f"Успешно обновлено"
                })
                updated_count += 1
                
            except Exception as e:
                error_msg = str(e)
                results.append({
                    "identifier": item.identifier,
                    "status": "error",
                    "msg": error_msg
                })
                error_count += 1
                
                # Если слишком много ошибок - делаем rollback и останавливаемся
                if error_count > len(req.items) * 0.5:  # Более 50% ошибок
                    raise Exception(f"Критическое количество ошибок ({error_count}). Выполняется rollback.")
        
        # Если все прошло успешно - логируем
        log_event(
            db,
            user=admin["username"],
            action="MASS_UPDATE",
            target="bulk_users",
            details={
                "total": len(req.items),
                "updated": updated_count,
                "errors": error_count,
                "backup_file": backup_filename
            },
            ip=request.client.host,
            status="SUCCESS" if error_count == 0 else "PARTIAL"
        )
        
        return {
            "status": "success" if error_count == 0 else "partial",
            "updated": updated_count,
            "errors": error_count,
            "total": len(req.items),
            "log": results,
            "backup_file": backup_filename
        }
        
    except Exception as e:
        # Rollback: восстанавливаем из бэкапов
        rollback_errors = []
        for dn, original_attrs in backups.items():
            try:
                if original_attrs:
                    ldap_service.modify_user(dn, original_attrs)
            except Exception as rollback_error:
                rollback_errors.append(f"{dn}: {rollback_error}")
        
        log_event(
            db,
            user=admin["username"],
            action="MASS_UPDATE_ROLLBACK",
            target="bulk_users",
            details={
                "error": str(e),
                "rollback_errors": rollback_errors,
                "backup_file": backup_filename
            },
            ip=request.client.host,
            status="FAIL"
        )
        
        raise HTTPException(
            status_code=500,
            detail=f"Критическая ошибка при массовом обновлении. Выполнен rollback. Ошибка: {str(e)}"
        )

