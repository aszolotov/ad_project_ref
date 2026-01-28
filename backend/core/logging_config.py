# backend/core/logging_config.py
import logging
import sys
from pathlib import Path
from backend.core.config import settings

# Настройка логирования
def setup_logging():
    """Настройка структурированного логирования для приложения"""
    
    # Создаем директорию для логов
    log_dir = settings.BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # Формат логов
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Базовый уровень логирования
    log_level = logging.INFO
    
    # Настройка root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Удаляем существующие handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(log_format, date_format)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (с ротацией)
    from logging.handlers import RotatingFileHandler
    log_file = log_dir / "ad_system.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(log_format, date_format)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    return root_logger

# Создаем logger для модулей
logger = logging.getLogger(__name__)

