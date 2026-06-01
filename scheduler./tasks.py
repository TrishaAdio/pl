"""
scheduler/tasks.py — APScheduler AsyncIOScheduler jobs
"""

from __future__ import annotations
import asyncio
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import config
from utils.logger import logger


class TaskScheduler:
    """Wraps APScheduler and manages the monitoring job."""

    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self._job_id = "monitor_job"

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started.")

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped.")

    def add_monitor_job(self, interval_seconds: int = None) -> None:
        """Add the recurring monitoring job."""
        if interval_seconds is None:
            interval_seconds = config.MONITOR_INTERVAL

        # Remove existing if any
        if self.scheduler.get_job(self._job_id):
            self.scheduler.remove_job(self._job_id)

        self.scheduler.add_job(
            _run_monitor,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=self._job_id,
            name="Keyword Monitor",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info(f"Monitor job scheduled every {interval_seconds}s.")

    def remove_monitor_job(self) -> None:
        if self.scheduler.get_job(self._job_id):
            self.scheduler.remove_job(self._job_id)
            logger.info("Monitor job removed.")

    def reschedule_monitor(self, interval_seconds: int) -> None:
        """Update the monitor interval."""
        self.add_monitor_job(interval_seconds)

    def is_running(self) -> bool:
        return self.scheduler.running

    def get_job_info(self) -> Optional[str]:
        job = self.scheduler.get_job(self._job_id)
        if job:
            return f"Next run: {job.next_run_time}"
        return None


async def _run_monitor() -> None:
    """Coroutine executed by scheduler every interval."""
    from services.monitor import monitor_service
    try:
        await monitor_service.run_once()
    except Exception as exc:
        logger.error(f"Monitor job error: {exc}")


task_scheduler = TaskScheduler()
