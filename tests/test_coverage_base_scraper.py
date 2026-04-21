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


def _make_health_checker(**config_overrides) -> HealthChecker:
    config = HealthCheckConfig(enable_auto_recovery=False, **config_overrides)
    return HealthChecker(config)


def test_update_domain_health_marks_unhealthy_after_threshold():
    domain = "example.com"
    hc = _make_health_checker(failure_threshold=2)

    asyncio.run(hc.update_domain_health(domain, False))

    assert hc.is_domain_healthy(domain) is True
    assert hc.domain_health[domain]["consecutive_failures"] == 1
    assert hc.domain_health[domain]["total_failures"] == 1

    asyncio.run(hc.update_domain_health(domain, False))

    health_info = hc.domain_health[domain]
    assert health_info["healthy"] is False
    assert health_info["consecutive_failures"] == 2
    assert health_info["consecutive_successes"] == 0
    assert health_info["total_checks"] == 2
    assert health_info["total_failures"] == 2


def test_update_domain_health_recovers_after_threshold():
    domain = "recover.example.com"
    hc = _make_health_checker(failure_threshold=1, recovery_threshold=2)

    asyncio.run(hc.update_domain_health(domain, False))
    assert hc.is_domain_healthy(domain) is False

    asyncio.run(hc.update_domain_health(domain, True))

    first_recovery_attempt = hc.domain_health[domain]
    assert first_recovery_attempt["healthy"] is False
    assert first_recovery_attempt["consecutive_successes"] == 1
    assert first_recovery_attempt["consecutive_failures"] == 0

    asyncio.run(hc.update_domain_health(domain, True))

    health_info = hc.domain_health[domain]
    assert health_info["healthy"] is True
    assert health_info["consecutive_successes"] == 2
    assert health_info["consecutive_failures"] == 0
    assert health_info["total_checks"] == 3
    assert health_info["total_failures"] == 1


def test_apply_healthy_update_increments_successes():
    hc = _make_health_checker(recovery_threshold=2)
    info = {
        "healthy": False,
        "consecutive_successes": 1,
        "consecutive_failures": 2,
        "total_failures": 2,
    }

    hc._apply_healthy_update("test.com", info)

    assert info["consecutive_successes"] == 2
    assert info["consecutive_failures"] == 0
    assert info["healthy"] is True


def test_apply_unhealthy_update_increments_failures():
    hc = _make_health_checker(failure_threshold=2)
    info = {
        "healthy": True,
        "consecutive_failures": 1,
        "consecutive_successes": 0,
        "total_failures": 1,
    }

    hc._apply_unhealthy_update("test.com", info)

    assert info["consecutive_failures"] == 2
    assert info["consecutive_successes"] == 0
    assert info["total_failures"] == 2
    assert info["healthy"] is False


def test_is_domain_healthy_unknown_domain_returns_true():
    hc = _make_health_checker()

    assert hc.is_domain_healthy("unknown.example.com") is True


def test_is_domain_healthy_known_unhealthy_domain():
    domain = "down.example.com"
    hc = _make_health_checker(failure_threshold=1)

    asyncio.run(hc.update_domain_health(domain, False))

    assert hc.is_domain_healthy(domain) is False


def test_check_domain_health_returns_false_on_exception():
    class FailingSession:
        async def __aenter__(self):
            raise RuntimeError("boom")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    hc = _make_health_checker(timeout=1)

    with (
        patch("aiohttp.ClientTimeout", return_value=object()),
        patch("aiohttp.ClientSession", return_value=FailingSession()),
    ):
        result = asyncio.run(hc.check_domain_health("broken.example.com"))

    assert result is False


def test_get_health_report_domain_details_do_not_expose_domain_hint():
    domain = "nohint.example.com"
    hc = _make_health_checker(failure_threshold=1)

    asyncio.run(hc.update_domain_health(domain, False))

    report = hc.get_health_report()

    assert "_domain_hint" not in report["domain_details"][domain]
