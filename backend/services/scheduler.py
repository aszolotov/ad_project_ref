import schedule
import time
import threading
import logging
from backend.core.config import settings
from backend.services.workflow_engine import workflow_engine

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self):
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("Scheduler started")
        
        # Пример задачи: очистка старых бэкапов (каждый день в 3 ночи)
        schedule.every().day.at("03:00").do(self._cleanup_backups)
        
        # Пример задачи: проверка scheduled workflows (каждую минуту)
        schedule.every(1).minutes.do(self._check_scheduled_workflows)

    def _run(self):
        while self.running:
            schedule.run_pending()
            time.sleep(1)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        logger.info("Scheduler stopped")

    def _cleanup_backups(self):
        logger.info("Running backup cleanup task...")
        # TODO: Реализовать удаление старых файлов из settings.BACKUP_DIR
        pass

    def _check_scheduled_workflows(self):
        # Запуск workflow по расписанию
        # Здесь можно сканировать папку workflows и искать те, у которых trigger="schedule"
        # и проверять cron-выражение (если бы оно было)
        # Для простоты пока просто триггерим событие 'schedule_tick'
        workflow_engine.trigger("schedule_tick", {"timestamp": time.time()})

scheduler = SchedulerService()
