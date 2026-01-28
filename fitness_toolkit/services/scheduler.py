"""Scheduled sync task service - simplified for personal tool."""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from fitness_toolkit.database import (
    save_sync_task as db_save_sync_task,
    get_sync_task as db_get_sync_task,
    list_sync_tasks as db_list_sync_tasks,
    delete_sync_task as db_delete_sync_task
)
from fitness_toolkit.services.download import DownloadService

logger = logging.getLogger(__name__)


class SchedulerService:
    """Service for managing scheduled sync tasks - one per platform."""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.download_service = DownloadService()
        self._job_ids = {}
    
    def start(self):
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("Scheduler started")
        self._load_existing_tasks()
    
    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")
    
    def _load_existing_tasks(self):
        """Load and schedule existing enabled tasks."""
        tasks = db_list_sync_tasks()
        for task in tasks:
            if task.get('enabled'):
                self._schedule_task(task['platform'], task)
    
    def configure(self, platform: str, enabled: bool, cron_expression: str,
                  file_format: str = 'tcx', activity_types: Optional[str] = None):
        """Configure sync task for a platform."""
        db_save_sync_task(platform, enabled, cron_expression, file_format, activity_types)

        if enabled:
            task = db_get_sync_task(platform)
            if task is not None:
                self._schedule_task(platform, task)
        else:
            self._unschedule_task(platform)

        logger.info(f"Configured sync task for {platform}")
    
    def _schedule_task(self, platform: str, task: Dict):
        """Schedule a task for a platform."""
        job_id = f"sync_{platform}"
        
        try:
            # Remove existing job if any
            self._unschedule_task(platform)
            
            trigger = CronTrigger.from_crontab(task['cron_expression'])
            job = self.scheduler.add_job(
                func=self._execute_sync,
                trigger=trigger,
                id=job_id,
                args=[platform],
                replace_existing=True
            )
            self._job_ids[platform] = job_id
            logger.info(f"Scheduled sync for {platform}")
            
        except Exception as e:
            logger.error(f"Failed to schedule task for {platform}: {e}")
    
    def _unschedule_task(self, platform: str):
        """Unschedule task for a platform."""
        job_id = self._job_ids.get(platform)
        if job_id:
            try:
                self.scheduler.remove_job(job_id)
                del self._job_ids[platform]
            except Exception as e:
                logger.warning(f"Failed to remove job {job_id}: {e}")
    
    def _execute_sync(self, platform: str):
        """Execute sync for a platform."""
        logger.info(f"Executing scheduled sync for {platform}")
        
        try:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=7)
            
            result = self.download_service.download(
                platform=platform,
                start_date=start_date,
                end_date=end_date
            )
            
            logger.info(f"Sync for {platform} completed: {result['downloaded']} downloaded")
            
        except Exception as e:
            logger.error(f"Sync for {platform} failed: {e}")
    
    def list_tasks(self) -> List[Dict]:
        """List all sync tasks."""
        return db_list_sync_tasks()
    
    def get_task(self, platform: str) -> Optional[Dict]:
        """Get sync task for a platform."""
        return db_get_sync_task(platform)
    
    def remove_task(self, platform: str) -> bool:
        """Remove sync task for a platform."""
        self._unschedule_task(platform)
        result = db_delete_sync_task(platform)
        if result:
            logger.info(f"Removed sync task for {platform}")
        return result
    
    def create_task(self, account_id: str, name: str, cron_expression: str,
                    file_format: str = 'tcx', activity_types: Optional[str] = None) -> str:
        platform = account_id
        enabled = True
        db_save_sync_task(platform, enabled, cron_expression, file_format, activity_types)
        task = db_get_sync_task(platform)
        if task is not None and enabled:
            self._schedule_task(platform, task)
        logger.info(f"Created sync task for {platform}")
        return platform
    
    def enable_task(self, task_id) -> bool:
        platform = task_id
        task = db_get_sync_task(platform)
        if task is not None:
            task['enabled'] = True
            db_save_sync_task(platform, True, task['cron_expression'],
                            task.get('file_format', 'tcx'), task.get('activity_types'))
            self._schedule_task(platform, task)
            return True
        return False
    
    def disable_task(self, task_id) -> bool:
        platform = task_id
        task = db_get_sync_task(platform)
        if task is not None:
            db_save_sync_task(platform, False, task['cron_expression'],
                            task.get('file_format', 'tcx'), task.get('activity_types'))
            self._unschedule_task(platform)
            return True
        return False
    
    def delete_task(self, task_id) -> bool:
        platform = task_id
        return self.remove_task(platform)
