from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.requests import Request
from sqlalchemy import text

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.core.config import settings
from backend.core.logging_config import setup_logging
from backend.db.database import Base, engine, get_db
from backend.routers import auth, users, system, import_router, workflows, groups, reports, user_templates, tags
from backend.services.plugin_manager import plugin_manager
from backend.services.ldap_service import ldap_pool
from backend.core.security_middleware import SecurityHeadersMiddleware
from backend.services.scheduler import scheduler

# Настройка логирования
logger = setup_logging()
logger.info("Starting AD Control System...")

# Создаём таблицы БД при старте (если их нет)
Base.metadata.create_all(bind=engine)

# Инициализация Rate Limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title=settings.PROJECT_NAME)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# Настройка CORS (разрешаем запросы с фронтенда, даже если он на другом порту)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене лучше указать конкретные домены
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Подключаем роутеры (API Endpoints)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(groups.router)
app.include_router(system.router)
app.include_router(import_router.router)
app.include_router(workflows.router)
app.include_router(reports.router)
app.include_router(user_templates.router)
app.include_router(tags.router)

# Событие при запуске приложения
@app.on_event("startup")
def on_startup():
    logger.info("Application startup...")
    # Создаем необходимые папки
    settings.create_dirs()
    # Загружаем плагины
    plugin_manager.load_plugins()
    # Запускаем планировщик
    scheduler.start()
    logger.info("Application started successfully")

@app.on_event("shutdown")
def on_shutdown():
    scheduler.stop()

# Монтируем папку frontend как статику
# Теперь файлы доступны по пути /static/style.css и т.д., если они там есть
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Главная страница (отдает index.html при заходе на корень сайта)
@app.get("/")
async def read_index():
    return FileResponse('frontend/index.html')

# Дополнительный маршрут для явного запроса index.html
@app.get("/index.html")
async def read_index_direct():
    return FileResponse('frontend/index.html')

# Health check endpoints (без аутентификации)
@app.get("/health")
async def health():
    """Базовый health check"""
    return JSONResponse({
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": "7.3"
    })


@app.get("/health/ldap")
async def health_ldap():
    """Проверка подключения к Active Directory"""
    try:
        conn = ldap_pool.get_connection()
        try:
            # Простой поиск для проверки подключения
            conn.search(settings.AD_BASE_DN, "(objectClass=*)", size_limit=1)
            ldap_pool.release(conn)
            return JSONResponse({
                "status": "ok",
                "ldap": "connected",
                "server": settings.AD_SERVER
            })
        except Exception as e:
            ldap_pool.release(conn)
            raise
    except Exception as e:
        logger.error(f"LDAP health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"LDAP connection failed: {str(e)}")


@app.get("/health/db")
async def health_db():
    """Проверка подключения к базе данных"""
    try:
        db = next(get_db())
        try:
            # Простой запрос для проверки подключения
            db.execute(text("SELECT 1"))
            return JSONResponse({
                "status": "ok",
                "database": "connected"
            })
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection failed: {str(e)}")


# Этот блок middleware нужен, чтобы SPA (Single Page Application) роутинг работал корректно
# (если бы у нас был React/Vue, но для текущего index.html это просто страховка)
@app.middleware("http")
async def spa_fallback(request: Request, call_next):
    response = await call_next(request)
    if response.status_code == 404 and not request.url.path.startswith("/api"):
        # Если запрашиваемый файл не найден и это не API запрос -> отдаем index.html
        # (Полезно для history mode в JS фреймворках, здесь просто для надежности)
        return FileResponse('frontend/index.html')
    return response
