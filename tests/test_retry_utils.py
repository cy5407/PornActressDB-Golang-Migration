"""
retry_utils 行為測試

目標：驗證重試/退避與自適應併發控制的外部行為與不變性，
不是只為了踩 coverage 分支。
"""

from src.utils.retry_utils import AdaptiveConcurrencyController, ExponentialBackoff


def test_exponential_backoff_grows_monotonically_without_jitter_and_reset():
    backoff = ExponentialBackoff(
        base_delay=0.5,
        max_delay=10.0,
        multiplier=2.0,
        jitter=False,
    )

    delays = [backoff.next_delay() for _ in range(4)]

    assert delays == [0.5, 1.0, 2.0, 4.0]
    assert backoff.current_attempt() == 4

    backoff.reset()

    assert backoff.current_attempt() == 0
    assert backoff.next_delay() == 0.5


def test_exponential_backoff_never_exceeds_max_delay():
    backoff = ExponentialBackoff(
        base_delay=3.0,
        max_delay=5.0,
        multiplier=3.0,
        jitter=False,
    )

    delays = [backoff.next_delay() for _ in range(5)]

    assert delays[0] == 3.0
    assert delays[1:] == [5.0, 5.0, 5.0, 5.0]
    assert all(delay <= 5.0 for delay in delays)


def test_exponential_backoff_with_jitter_stays_within_expected_band():
    backoff = ExponentialBackoff(
        base_delay=10.0,
        max_delay=10.0,
        multiplier=2.0,
        jitter=True,
    )

    delay = backoff.next_delay()

    assert 8.0 <= delay <= 12.0


def test_adaptive_concurrency_controller_reduces_after_failures_and_recovers_after_successes():
    controller = AdaptiveConcurrencyController(
        initial=12,
        minimum=3,
        maximum=20,
        decrease_threshold=2,
        increase_threshold=3,
        decrease_factor=0.5,
        increase_step=4,
    )

    controller.report_failure()
    assert controller.get_concurrency() == 12

    controller.report_failure()
    assert controller.get_concurrency() == 6

    controller.report_success()
    controller.report_success()
    assert controller.get_concurrency() == 6

    controller.report_success()
    assert controller.get_concurrency() == 10


def test_adaptive_concurrency_controller_respects_minimum_and_maximum_bounds():
    controller = AdaptiveConcurrencyController(
        initial=5,
        minimum=4,
        maximum=6,
        decrease_threshold=1,
        increase_threshold=1,
        decrease_factor=0.1,
        increase_step=10,
    )

    controller.report_failure()
    assert controller.get_concurrency() == 4

    controller.report_failure()
    assert controller.get_concurrency() == 4

    controller.report_success()
    assert controller.get_concurrency() == 6

    controller.report_success()
    assert controller.get_concurrency() == 6


def test_adaptive_concurrency_stats_reflect_current_state():
    controller = AdaptiveConcurrencyController(
        initial=8,
        minimum=2,
        maximum=16,
        decrease_threshold=3,
        increase_threshold=2,
        decrease_factor=0.5,
        increase_step=2,
    )

    controller.report_success()
    stats_after_one_success = controller.get_stats()
    assert stats_after_one_success["current_concurrency"] == 8
    assert stats_after_one_success["consecutive_successes"] == 1
    assert stats_after_one_success["consecutive_failures"] == 0

    controller.report_success()
    stats_after_scale_up = controller.get_stats()
    assert stats_after_scale_up["current_concurrency"] == 10
    assert stats_after_scale_up["consecutive_successes"] == 0
    assert stats_after_scale_up["minimum"] == 2
    assert stats_after_scale_up["maximum"] == 16

    controller.report_failure()
    controller.reset()
    stats_after_reset = controller.get_stats()
    assert stats_after_reset["current_concurrency"] == 10
    assert stats_after_reset["consecutive_successes"] == 0
    assert stats_after_reset["consecutive_failures"] == 0
