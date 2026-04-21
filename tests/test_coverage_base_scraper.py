"""base_scraper.HealthChecker 測試"""
import asyncio
from unittest.mock import MagicMock, patch

from src.scrapers.base_scraper import HealthChecker, HealthCheckConfig


def test_start_health_check_task_schedules_coroutine():
    """_start_health_check_task 應該在 event loop 上排程背景任務"""
    scheduled_tasks = []

    def _capture_task(coro):
        scheduled_tasks.append(coro)
        return MagicMock(name="health_check_task")

    loop = MagicMock()
    loop.create_task.side_effect = _capture_task

    config = HealthCheckConfig(enable_auto_recovery=True)
    hc = HealthChecker.__new__(HealthChecker)  # 繞過 __init__ 避免提早觸發
    hc.config = config
    hc.domain_health = {}
    hc.lock = asyncio.Lock()

    with patch("asyncio.get_running_loop", return_value=loop):
        hc._start_health_check_task()

    assert loop.create_task.called, "_start_health_check_task 應呼叫 loop.create_task()"
    assert len(scheduled_tasks) == 1

    for coro in scheduled_tasks:
        coro.close()
