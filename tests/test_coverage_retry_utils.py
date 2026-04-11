"""
retry_utils.py 覆蓋率補測
目標：覆蓋純邏輯的退避與自適應併發控制，不碰外部 I/O。
"""

from src.utils.retry_utils import (
    AdaptiveConcurrencyController,
    ExponentialBackoff,
    _secure_uniform,
)


# ──────────────────────────────
# _secure_uniform
# ──────────────────────────────


def test_secure_uniform_returns_min_when_range_invalid():
    assert _secure_uniform(5.0, 5.0) == 5.0
    assert _secure_uniform(3.0, 2.0) == 3.0


# ──────────────────────────────
# ExponentialBackoff
# ──────────────────────────────


def test_exponential_backoff_steps_and_reset(monkeypatch):
    monkeypatch.setattr("src.utils.retry_utils.randbelow", lambda _: 5000)

    backoff = ExponentialBackoff(base_delay=1.0, max_delay=10.0, multiplier=2.0, jitter=True)

    first = backoff.next_delay()
    second = backoff.next_delay()
    third = backoff.next_delay()

    assert first == 1.0
    assert second == 2.0
    assert third == 4.0
    assert backoff.current_attempt() == 3

    backoff.reset()
    assert backoff.current_attempt() == 0
    assert backoff.next_delay() == 1.0


def test_exponential_backoff_respects_max_delay_without_jitter():
    backoff = ExponentialBackoff(base_delay=5.0, max_delay=6.0, multiplier=10.0, jitter=False)

    assert backoff.next_delay() == 5.0
    assert backoff.next_delay() == 6.0
    assert backoff.next_delay() == 6.0


def test_exponential_backoff_reset_keeps_configuration():
    backoff = ExponentialBackoff(base_delay=2.0, max_delay=8.0, multiplier=3.0, jitter=False)

    backoff.next_delay()
    backoff.next_delay()
    backoff.reset()

    assert backoff.base_delay == 2.0
    assert backoff.max_delay == 8.0
    assert backoff.multiplier == 3.0
    assert backoff.jitter is False
    assert backoff.current_attempt() == 0


# ──────────────────────────────
# AdaptiveConcurrencyController
# ──────────────────────────────


def test_adaptive_concurrency_controller_decreases_and_increases():
    controller = AdaptiveConcurrencyController(
        initial=10,
        minimum=3,
        maximum=12,
        decrease_threshold=2,
        increase_threshold=3,
        decrease_factor=0.5,
        increase_step=2,
    )

    controller.report_failure()
    assert controller.get_concurrency() == 10

    controller.report_failure()
    assert controller.get_concurrency() == 5

    controller.report_success()
    controller.report_success()
    controller.report_success()
    assert controller.get_concurrency() == 7

    stats = controller.get_stats()
    assert stats["current_concurrency"] == 7
    assert stats["consecutive_successes"] == 0
    assert stats["consecutive_failures"] == 0
    assert stats["minimum"] == 3
    assert stats["maximum"] == 12


def test_adaptive_concurrency_controller_respects_bounds_and_reset():
    controller = AdaptiveConcurrencyController(
        initial=4,
        minimum=3,
        maximum=5,
        decrease_threshold=1,
        increase_threshold=1,
        decrease_factor=0.1,
        increase_step=10,
    )

    controller.report_failure()
    assert controller.get_concurrency() == 3
    assert controller.consecutive_successes == 0
    assert controller.consecutive_failures == 0

    controller.report_success()
    assert controller.get_concurrency() == 5
    assert controller.consecutive_failures == 0

    stats = controller.get_stats()
    assert stats["current_concurrency"] == 5
    assert stats["consecutive_successes"] == 0
    assert stats["consecutive_failures"] == 0
    assert stats["minimum"] == 3
    assert stats["maximum"] == 5

    controller.reset()
    assert controller.get_stats()["consecutive_successes"] == 0
    assert controller.get_stats()["consecutive_failures"] == 0
    assert controller.get_concurrency() == 5
