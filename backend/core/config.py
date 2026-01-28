import os
from pathlib import Path
from typing import Optional


class Settings:
    # Базовые параметры
    PROJECT_NAME: str = "AD Enterprise Control v7.3"
    API_V1_STR: str = "/api/v6"
    
    # Безопасность: секретный ключ должен быть установлен через переменную окружения
    SECRET_KEY: str = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY must be set in environment variables")
    
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # Настройки Active Directory (все обязательные, кроме DEMO MODE)
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() == "true"
    
    AD_SERVER: str = os.getenv("AD_SERVER") or ("demo.local" if DEMO_MODE else None)
    AD_DOMAIN: str = os.getenv("AD_DOMAIN") or ("DEMO" if DEMO_MODE else None)
    AD_BASE_DN: str = os.getenv("AD_BASE_DN") or ("DC=demo,DC=local" if DEMO_MODE else None)
    AD_SYSTEM_USER: str = os.getenv("AD_SYSTEM_USER") or ("demo\\admin" if DEMO_MODE else None)
    AD_SYSTEM_PASSWORD: str = os.getenv("AD_SYSTEM_PASSWORD") or ("demo" if DEMO_MODE else None)
    
    # Валидация обязательных параметров AD (пропускаем в DEMO MODE)
    if not DEMO_MODE and not all([AD_SERVER, AD_DOMAIN, AD_BASE_DN, AD_SYSTEM_USER, AD_SYSTEM_PASSWORD]):
        raise ValueError(
            "All AD settings (AD_SERVER, AD_DOMAIN, AD_BASE_DN, AD_SYSTEM_USER, AD_SYSTEM_PASSWORD) "
            "must be set in environment variables. Or set DEMO_MODE=true for testing."
        )


    
    # Разрешенные OU для операций (защита от дурака)
    # По умолчанию разрешены все OU, но рекомендуется ограничить
    allowed_ous_str: Optional[str] = os.getenv("ALLOWED_OUS")
    ALLOWED_OUS: list = allowed_ous_str.split(";") if allowed_ous_str else []

    # Пути
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    BACKUP_DIR = BASE_DIR / "backups"
    PLUGINS_DIR = BASE_DIR / "plugins"
    WORKFLOWS_DIR = PLUGINS_DIR / "workflows"
    
    # Database (по умолчанию SQLite для dev, но рекомендуется PostgreSQL для production)
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'audit.db'}")

    # LDAP Pool настройки
    LDAP_POOL_SIZE: int = int(os.getenv("LDAP_POOL_SIZE", "10"))
    LDAP_POOL_TIMEOUT: int = int(os.getenv("LDAP_POOL_TIMEOUT", "30"))

    # Rate Limiting (опционально)
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_LOGIN: str = os.getenv("RATE_LIMIT_LOGIN", "5/minute")
    RATE_LIMIT_CREATE: str = os.getenv("RATE_LIMIT_CREATE", "10/minute")
    RATE_LIMIT_MASS_UPDATE: str = os.getenv("RATE_LIMIT_MASS_UPDATE", "3/minute")

    # Monitoring
    PROMETHEUS_ENABLED: bool = os.getenv("PROMETHEUS_ENABLED", "false").lower() == "true"
    JSON_LOGGING: bool = os.getenv("JSON_LOGGING", "false").lower() == "true"

    # Создание папок при запуске
    def create_dirs(self):
        for d in [self.BACKUP_DIR, self.PLUGINS_DIR, self.WORKFLOWS_DIR]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
