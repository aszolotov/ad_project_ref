# Enhanced Plugin Manager with OAuth, Database, and ML support
import importlib.util
import logging
import re
import subprocess
import platform
import json
import schedule
from datetime import datetime
from pathlib import Path
from backend.core.config import settings

logger = logging.getLogger(__name__)

class SafeRequests:
    """
    Безопасная обертка над requests для использования в плагинах.
    Расширенная версия с поддержкой OAuth endpoints.
    """
    ALLOWED_HOSTS = [
        "api.corp.local", 
        "localhost", 
        "127.0.0.1",
        # Microsoft
        "graph.microsoft.com",
        "login.microsoftonline.com",
        # Communication
        "api.slack.com",
        "hooks.slack.com",
        "api.telegram.org",
        # Internal services
        "smtp.corp.local",
        "ml-service.corp.local",
        "elasticsearch.corp.local"
    ]

    def __init__(self, whitelist=None):
        self.whitelist = whitelist or self.ALLOWED_HOSTS
        
    def _check_url(self, url):
        from urllib.parse import urlparse
        parsed = urlparse(url)
        hostname = parsed.hostname
        
        if not self.whitelist:
            if hostname in ["localhost", "127.0.0.1"]:
                return
            raise Exception(f"URL {url} is not in whitelist")
            
        if hostname not in self.whitelist:
             raise Exception(f"URL {url} is not in whitelist. Add to ALLOWED_HOSTS in plugin config.")

    def get(self, url, **kwargs):
        self._check_url(url)
        import requests
        return requests.get(url, **kwargs)
        
    def post(self, url, **kwargs):
        self._check_url(url)
        import requests
        return requests.post(url, **kwargs)
    
    def delete(self, url, **kwargs):
        self._check_url(url)
        import requests
        return requests.delete(url, **kwargs)
    
    def put(self, url, **kwargs):
        self._check_url(url)
        import requests
        return requests.put(url, **kwargs)

class NetworkTools:
    @staticmethod
    def ping(host: str, timeout: int = 1) -> bool:
        """
        Безопасный пинг хоста.
        Возвращает True, если хост доступен, иначе False.
        """
        if not host or not re.match(r'^[a-zA-Z0-9.-]+$', host):
            return False

        param = '-n' if platform.system().lower() == 'windows' else '-c'
        command = ['ping', param, '1', host]
        
        try:
            subprocess.check_call(
                command, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                timeout=timeout
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False
        except Exception:
            return False

class PluginDatabase:
    """
    Безопасный доступ к БД для плагинов.
    Плагины могут создавать свои таблицы и хранить данные.
    """
    def __init__(self, db_session):
        self.session = db_session
    
    def execute_query(self, query, params=None):
        """Выполнить SQL запрос (только SELECT)"""
        if not query.strip().upper().startswith('SELECT'):
            raise Exception("Only SELECT queries allowed for plugins")
        
        from sqlalchemy import text
        result = self.session.execute(text(query), params or {})
        return [dict(row) for row in result]
    
    def create_plugin_table(self, table_name, schema):
        """
        Создать таблицу для плагина.
        schema = {"column_name": "type", ...}
        """
        if not re.match(r'^plugin_[a-z0-9_]+$', table_name):
            raise Exception("Plugin table names must start with 'plugin_'")
        
        from sqlalchemy import text
        
        columns = []
        for col, typ in schema.items():
            if typ.upper() not in ['TEXT', 'INTEGER', 'REAL', 'BLOB', 'DATETIME']:
                raise Exception(f"Invalid column type: {typ}")
            columns.append(f"{col} {typ}")
        
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns)})"
        self.session.execute(text(sql))
        self.session.commit()
    
    def insert(self, table_name, data):
        """Вставить данные в таблицу плагина"""
        if not table_name.startswith('plugin_'):
            raise Exception("Can only insert into plugin tables")
        
        from sqlalchemy import text
        
        columns = ', '.join(data.keys())
        placeholders = ', '.join(f":{k}" for k in data.keys())
        sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        
        self.session.execute(text(sql), data)
        self.session.commit()
    
    def query(self, table_name, filters=None):
        """Запрос данных из таблицы плагина"""
        if not table_name.startswith('plugin_'):
            raise Exception("Can only query plugin tables")
        
        sql = f"SELECT * FROM {table_name}"
        params = {}
        
        if filters:
            where_clauses = []
            for i, (key, value) in enumerate(filters.items()):
                param_name = f"param_{i}"
                where_clauses.append(f"{key} = :{param_name}")
                params[param_name] = value
            sql += " WHERE " + " AND ".join(where_clauses)
        
        return self.execute_query(sql, params)

class PluginManager:
    def __init__(self):
        self.hooks = {
            "pre_create": [], 
            "post_create": [], 
            "pre_modify": [], 
            "post_modify": [], 
            "pre_delete": [], 
            "post_delete": [],
            "validation": [],
            "scheduler": [],
            "export_format": [],
            "enrich_computers": [],
            # New hooks
            "api_request": [],      # API request interception
            "auth_success": [],     # After successful auth
            "auth_failed": [],      # After failed auth
            "render_widget": [],    # Custom dashboard widgets
        }
        self.plugins = []
        self.plugin_configs = {}
        
        self.context = {
            "safe_requests": SafeRequests(),
            "network_tools": NetworkTools,
            "logger": logger,
            "datetime": datetime,
            "schedule": schedule,
            "json": json,
            "re": re
        }

    def set_database(self, db_session):
        """Set database session for plugins"""
        self.context["db"] = PluginDatabase(db_session)

    def validate_code(self, filepath):
        """
        Валидация кода плагина на наличие опасных конструкций.
        """
        dangerous = [
            "os.system", "subprocess.run", "subprocess.call",
            "exec(", "eval(", 
            "shutil.rmtree", "__import__('os')",
            "file(", "__builtins__",
            "compile(", "__code__",
            "pickle.loads"  # Unsafe deserialization
        ]
        
        # Allow some subprocess for NetworkTools
        allowed_patterns = [
            "subprocess.check_call",  # Used by ping
            "subprocess.DEVNULL"
        ]
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                for pattern in dangerous:
                    if pattern in content:
                        # Check if it's in allowed context
                        if not any(allowed in content for allowed in allowed_patterns):
                            logger.warning(f"Plugin blocked: '{pattern}' found in {filepath}")
                            return False
        except Exception as e:
            logger.error(f"Failed to validate plugin {filepath}: {e}")
            return False
        return True

    def load_plugins(self, db_session=None):
        """Загрузка всех плагинов из директории plugins/"""
        self.hooks = {k: [] for k in self.hooks}
        self.plugins = []
        
        if db_session:
            self.set_database(db_session)
        
        if not settings.PLUGINS_DIR.exists():
            settings.PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
            return
        
        for plugin_file in settings.PLUGINS_DIR.glob("*.py"):
            if plugin_file.name.startswith("_") or not self.validate_code(plugin_file):
                continue
            
            try:
                # Расширенные глобальные переменные для плагинов
                safe_globals = {
                    "__builtins__": {
                        "str": str, "int": int, "float": float, "bool": bool, 
                        "list": list, "dict": dict, "len": len, "print": print,
                        "True": True, "False": False, "None": None, 
                        "enumerate": enumerate, "range": range, "min": min, "max": max,
                        "sum": sum, "any": any, "all": all, "chr": chr
                    },
                    **self.context
                }
                
                with open(plugin_file, 'r', encoding='utf-8') as f:
                    code = compile(f.read(), plugin_file.name, 'exec')
                    exec(code, safe_globals)
                
                # Регистрация хуков
                if "register_hooks" in safe_globals:
                    class MockRegistrar:
                        def register_hook(s, event, func):
                            self.register_hook(event, func)
                    safe_globals["register_hooks"](MockRegistrar())
                
                # Метаданные
                meta = {"name": plugin_file.stem, "enabled": True}
                if "get_metadata" in safe_globals:
                    meta = safe_globals["get_metadata"]()
                    meta["enabled"] = True
                
                # Сохранить конфигурацию
                if "config" in meta:
                    self.plugin_configs[meta["name"]] = meta["config"]
                
                self.plugins.append(meta)
                logger.info(f"Loaded plugin: {meta.get('name')}")
                
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_file}: {e}", exc_info=True)

    def register_hook(self, event, func):
        if event not in self.hooks:
            self.hooks[event] = []
        self.hooks[event].append(func)

    def execute_hook(self, event, data, context=None):
        if event not in self.hooks:
            return data
        
        for func in self.hooks[event]:
            try:
                res = func(data)
                if res:
                    data = res
            except Exception as e:
                logger.error(f"Hook error for event {event}: {e}", exc_info=True)
        return data
    
    def get_widget_data(self):
        """Get data for custom dashboard widgets"""
        widgets = []
        for func in self.hooks.get("render_widget", []):
            try:
                widget = func({})
                if widget:
                    widgets.append(widget)
            except Exception as e:
                logger.error(f"Widget rendering error: {e}")
        return widgets

plugin_manager = PluginManager()
