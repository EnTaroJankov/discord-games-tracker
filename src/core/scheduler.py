# src/core/scheduler.py
from __future__ import annotations

import asyncio
from typing import Callable, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

_scheduler: Optional[AsyncIOScheduler] = None

def _ensure_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
        _scheduler.start()
    return _scheduler

def schedule_daily_midnight(coro_func: Callable, *, job_id: str = "daily_midnight", hour: int = 0, minute: int = 0):
    """
    Schedule an async task to run daily at the given time.
    - coro_func can be an async function or a callable returning a coroutine.
    - job_id ensures idempotency (replace_existing=True).
    """
    sched = _ensure_scheduler()

    def _runner():
        result = coro_func()
        if asyncio.iscoroutine(result):
            asyncio.create_task(result)

    sched.add_job(
        _runner,
        CronTrigger(hour=hour, minute=minute),
        id=job_id,
        replace_existing=True
    )