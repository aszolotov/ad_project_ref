import json
from datetime import datetime
from backend.core.config import settings
from backend.services.ldap_service import ldap_service

class BackupService:
    def create_snapshot(self, dns: list, operation_name: str, initiator: str):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        data = {
            "meta": {"timestamp": timestamp, "op": operation_name, "user": initiator},
            "objects": []
        }
        
        for dn in dns:
            try:
                entries = ldap_service.search(dn, "(objectClass=*)", attributes='*', scope='BASE')
                if entries:
                    # Конвертация атрибутов в dict
                    attrs = {k: str(v.value) if hasattr(v, 'value') else str(v) 
                             for k, v in entries[0].entry_attributes_as_dict.items()}
                    data["objects"].append({"dn": dn, "attributes": attrs})
            except Exception:
                pass # Object might not exist
        
        filename = f"backup_{operation_name}_{timestamp}.json"
        path = settings.BACKUP_DIR / filename
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        return filename

    def restore_snapshot(self, filename: str):
        path = settings.BACKUP_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"Backup file {filename} not found")
            
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        restored_count = 0
        for obj in data.get("objects", []):
            dn = obj.get("dn")
            attrs = obj.get("attributes", {})
            
            if not dn: continue
            
            # Попытка восстановления атрибутов
            # В LDAP восстановление - это сложная операция, так как нужно знать разницу
            # Для простоты попробуем восстановить критичные поля, если они есть в бэкапе
            # Или просто логируем, что нужно восстановить вручную
            
            # Реализуем частичное восстановление (replace)
            try:
                # Фильтруем системные атрибуты, которые нельзя менять
                safe_attrs = {}
                ignore_attrs = ['objectClass', 'cn', 'distinguishedName', 'whenCreated', 'whenChanged', 'uSNCreated', 'uSNChanged', 'objectGUID', 'objectSid']
                
                for k, v in attrs.items():
                    if k not in ignore_attrs:
                        safe_attrs[k] = v
                
                if safe_attrs:
                    ldap_service.modify_user(dn, safe_attrs)
                    restored_count += 1
            except Exception as e:
                # Если объекта нет, можно попробовать создать (но это сложно без всех обязательных атрибутов)
                pass
                
        return restored_count

backup_service = BackupService()
