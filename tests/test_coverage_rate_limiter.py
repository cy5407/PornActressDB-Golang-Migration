"""
補測 rate_limiter.py 的純邏輯部分。
測試重點：
1. _secure_uniform 邊界條件
2. DomainLimiter：記錄、統計、Retry-After、自適應延遲
3. RateLimiter：URL 提取、域名配置、統計匯總
4. 裝飾器：rate_limited / async_rate_limited
"""
import asyncio
import threading
import time

import pytest

from src.scrapers.rate_limiter import (
    DomainConfig,
    DomainLimiter,
    RateLimiter,
    RequestRecord,
    _secure_uniform,
    async_rate_limited,
    get_global_rate_limiter,
    rate_limited,
)

# ──────────────────────────────
# _secure_uniform
# ──────────────────────────────


def test_secure_uniform_returns_min_when_max_le_min():
    assert _secure_uniform(3.0, 3.0) == 3.0


def test_secure_uniform_returns_min_when_max_lt_min():
    assert _secure_uniform(5.0, 2.0) == 5.0


def test_secure_uniform_within_range():
    for _ in range(50):
        v = _secure_uniform(1.0, 2.0)
        assert 1.0 <= v <= 2.0


def test_secure_uniform_distribution_non_constant():
    """產生的值應有足夠的分散性，不應全部相同。"""
    values = {_secure_uniform(0.0, 1.0) for _ in range(10)}
    assert len(values) > 1


# ──────────────────────────────
# DomainConfig 預設值
# ──────────────────────────────


def test_domain_config_defaults():
    cfg = DomainConfig()
    assert cfg.requests_per_minute == 15
    assert cfg.min_interval == 1.0
    assert cfg.adaptive_delay is True
    assert cfg.respect_retry_after is True


# ──────────────────────────────
# DomainLimiter.record_request 與 get_stats
# ──────────────────────────────


@pytest.fixture
def limiter():
    return DomainLimiter("test.com", DomainConfig())


def test_record_request_success_increments_stats(limiter):
    limiter.record_request(success=True, response_time=0.5)
    stats = limiter.get_stats()
    assert stats["total_requests"] == 1
    assert stats["successful_requests"] == 1
    assert stats["failed_requests"] == 0


def test_record_request_failure_increments_stats(limiter):
    limiter.record_request(success=False, response_time=1.0)
    stats = limiter.get_stats()
    assert stats["total_requests"] == 1
    assert stats["failed_requests"] == 1
    assert stats["consecutive_failures"] == 1


def test_record_request_success_resets_consecutive_failures(limiter):
    limiter.record_request(success=False, response_time=1.0)
    limiter.record_request(success=False, response_time=1.0)
    limiter.record_request(success=True, response_time=0.3)
    assert limiter.consecutive_failures == 0


def test_record_request_adds_to_minute_and_hour_queues(limiter):
    limiter.record_request(success=True, response_time=0.1)
    limiter.record_request(success=True, response_time=0.2)
    assert len(limiter.minute_requests) == 2
    assert len(limiter.hour_requests) == 2


def test_record_request_respects_retry_after(limiter):
    """retry_after 應設定 retry_after_until 未來時間。"""
    limiter.record_request(success=False, response_time=0.1, retry_after=60)
    assert limiter.retry_after_until > time.time()


def test_record_request_no_retry_after_when_not_respected(limiter):
    limiter.config.respect_retry_after = False
    limiter.record_request(success=False, response_time=0.1, retry_after=60)
    assert limiter.retry_after_until == 0.0


def test_get_stats_success_rate(limiter):
    limiter.record_request(success=True, response_time=0.1)
    limiter.record_request(success=False, response_time=0.1)
    stats = limiter.get_stats()
    assert stats["success_rate"] == "50.0%"


def test_get_stats_no_requests(limiter):
    stats = limiter.get_stats()
    assert stats["success_rate"] == "0.0%"
    assert stats["average_response_time"] == "0.00s"


def test_get_stats_retry_after_active(limiter):
    limiter.record_request(success=False, response_time=0.1, retry_after=120)
    stats = limiter.get_stats()
    assert stats["is_retry_after_active"] is True
    assert stats["retry_after_remaining"] > 0


def test_get_stats_retry_after_inactive(limiter):
    stats = limiter.get_stats()
    assert stats["is_retry_after_active"] is False
    assert stats["retry_after_remaining"] == 0


# ──────────────────────────────
# DomainLimiter.consecutive_failures 退避邏輯
# ──────────────────────────────


def test_consecutive_failures_triggers_backoff(limiter):
    """連續 3 次失敗後，current_delay 應增加。"""
    original_delay = limiter.current_delay
    for _ in range(3):
        limiter.record_request(success=False, response_time=0.1)
    assert limiter.current_delay > original_delay


# ──────────────────────────────
# DomainLimiter._cleanup_old_records
# ──────────────────────────────


def test_cleanup_old_minute_records(limiter):
    old_time = time.time() - 120  # 2分鐘前
    limiter.minute_requests.append(old_time)
    limiter.hour_requests.append(old_time)
    limiter._cleanup_old_records(time.time())
    assert len(limiter.minute_requests) == 0


def test_cleanup_trims_request_history(limiter):
    """超過 1000 條記錄時應截斷。"""
    for _ in range(1100):
        limiter.request_history.append(
            RequestRecord(timestamp=time.time(), success=True, response_time=0.1)
        )
    limiter._cleanup_old_records(time.time())
    assert len(limiter.request_history) <= 1000


# ──────────────────────────────
# DomainLimiter._calculate_adaptive_delay
# ──────────────────────────────


def test_adaptive_delay_no_history_returns_current(limiter):
    """不足 5 條記錄時應返回 current_delay。"""
    delay = limiter._calculate_adaptive_delay()
    assert delay == pytest.approx(limiter.current_delay, rel=0.3)


def test_adaptive_delay_high_failure_rate_increases_delay(limiter):
    """高失敗率（>30%）應增加 current_delay。"""
    # 填入 10 條 70% 失敗的記錄
    for i in range(10):
        limiter.request_history.append(
            RequestRecord(
                timestamp=time.time(),
                success=(i < 3),  # 3 成功 7 失敗 = 70% 失敗率
                response_time=0.1,
            )
        )
    original = limiter.current_delay
    limiter._calculate_adaptive_delay()
    assert limiter.current_delay > original


def test_adaptive_delay_disabled_returns_current(limiter):
    limiter.config.adaptive_delay = False
    for _ in range(10):
        limiter.request_history.append(
            RequestRecord(timestamp=time.time(), success=False, response_time=5.0)
        )
    expected = limiter.current_delay
    result = limiter._calculate_adaptive_delay()
    assert result == expected


# ──────────────────────────────
# DomainLimiter.can_make_request - Retry-After 封鎖
# ──────────────────────────────


def test_can_make_request_blocked_by_retry_after(limiter):
    """若 retry_after_until 在未來，應回傳 False。"""
    limiter.retry_after_until = time.time() + 100
    can_request, wait_time = limiter.can_make_request()
    assert can_request is False
    assert wait_time > 0


def test_can_make_request_minute_limit(limiter):
    """超過每分鐘限制應回傳 False。"""
    limiter.config.requests_per_minute = 3
    current_time = time.time()
    for _ in range(3):
        limiter.minute_requests.append(current_time)
    can_request, wait_time = limiter.can_make_request()
    assert can_request is False
    assert wait_time >= 0


def test_can_make_request_hour_limit(limiter):
    """超過每小時限制應回傳 False。"""
    limiter.config.requests_per_hour = 2
    current_time = time.time()
    for _ in range(2):
        limiter.hour_requests.append(current_time)
    can_request, wait_time = limiter.can_make_request()
    assert can_request is False


def test_can_make_request_ok_when_first_request(limiter):
    """第一次請求且沒有封鎖條件，應回傳 True。"""
    limiter.last_request_time = 0.0  # 很久以前
    can_request, wait_time = limiter.can_make_request()
    assert can_request is True
    assert wait_time == 0.0


# ──────────────────────────────
# RateLimiter 整體功能
# ──────────────────────────────


@pytest.fixture
def rate_limiter():
    return RateLimiter()


def test_extract_domain(rate_limiter):
    assert rate_limiter._extract_domain("https://javdb.com/search") == "javdb.com"
    assert rate_limiter._extract_domain("http://av-wiki.net/page") == "av-wiki.net"


def test_extract_domain_invalid_url(rate_limiter):
    """無效 URL 應回傳 'unknown'。"""
    result = rate_limiter._extract_domain("not_a_url")
    assert isinstance(result, str)


def test_get_domain_limiter_creates_on_first_access(rate_limiter):
    limiter = rate_limiter._get_domain_limiter("new-domain.com")
    assert limiter.domain == "new-domain.com"


def test_get_domain_limiter_returns_same_instance(rate_limiter):
    l1 = rate_limiter._get_domain_limiter("same.com")
    l2 = rate_limiter._get_domain_limiter("same.com")
    assert l1 is l2


def test_known_domains_use_custom_config(rate_limiter):
    """av-wiki.net 和 javdb.com 應使用預設的特殊配置。"""
    limiter_avwiki = rate_limiter._get_domain_limiter("av-wiki.net")
    limiter_javdb = rate_limiter._get_domain_limiter("javdb.com")
    assert limiter_avwiki.config.min_interval == 2.0
    assert limiter_javdb.config.min_interval == 1.0


def test_unknown_domain_uses_default_config(rate_limiter):
    limiter = rate_limiter._get_domain_limiter("random.net")
    assert limiter.config.requests_per_minute == 15


def test_record_request_delegates_to_domain_limiter(rate_limiter):
    rate_limiter.record_request("https://test.com/page", True, 0.5)
    limiter = rate_limiter._get_domain_limiter("test.com")
    assert limiter.stats["total_requests"] == 1


def test_add_domain_config(rate_limiter):
    new_cfg = DomainConfig(min_interval=10.0)
    rate_limiter.add_domain_config("custom.com", new_cfg)
    limiter = rate_limiter._get_domain_limiter("custom.com")
    assert limiter.config.min_interval == 10.0


def test_add_domain_config_updates_existing_limiter(rate_limiter):
    """若限流器已存在，add_domain_config 應即時更新其 config。"""
    rate_limiter._get_domain_limiter("exist.com")  # 先建立
    new_cfg = DomainConfig(min_interval=99.0)
    rate_limiter.add_domain_config("exist.com", new_cfg)
    assert rate_limiter.domain_limiters["exist.com"].config.min_interval == 99.0


def test_get_domain_stats_returns_none_for_unknown(rate_limiter):
    assert rate_limiter.get_domain_stats("never.com") is None


def test_get_domain_stats_returns_stats_for_known(rate_limiter):
    rate_limiter.record_request("https://known.com/x", True, 0.1)
    stats = rate_limiter.get_domain_stats("known.com")
    assert stats is not None
    assert stats["total_requests"] == 1


def test_reset_domain_removes_limiter(rate_limiter):
    rate_limiter._get_domain_limiter("cleanup.com")
    rate_limiter.reset_domain("cleanup.com")
    assert "cleanup.com" not in rate_limiter.domain_limiters


def test_reset_domain_nonexistent_no_error(rate_limiter):
    rate_limiter.reset_domain("ghost.com")  # 不應拋出


def test_reset_all_clears_all_limiters(rate_limiter):
    rate_limiter._get_domain_limiter("a.com")
    rate_limiter._get_domain_limiter("b.com")
    rate_limiter.reset_all()
    assert len(rate_limiter.domain_limiters) == 0


def test_get_stats_aggregates(rate_limiter):
    rate_limiter.record_request("https://a.com/1", True, 0.1)
    rate_limiter.record_request("https://b.com/1", False, 0.2)
    stats = rate_limiter.get_stats()
    assert stats["total_stats"]["total_requests"] == 2
    assert stats["total_stats"]["successful_requests"] == 1
    assert "a.com" in stats["active_domains"]
    assert "b.com" in stats["active_domains"]


def test_get_stats_success_rate_zero_when_no_requests(rate_limiter):
    stats = rate_limiter.get_stats()
    assert stats["total_stats"]["success_rate"] == "0.0%"


# ──────────────────────────────
# wait_if_needed（跳過實際等待）
# ──────────────────────────────


def test_wait_if_needed_no_wait_when_can_request(rate_limiter, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    rate_limiter._get_domain_limiter("no-wait.com").last_request_time = 0
    wait = rate_limiter.wait_if_needed("https://no-wait.com/x")
    assert wait == 0.0


def test_wait_if_needed_sleeps_when_blocked(rate_limiter, monkeypatch):
    slept = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))
    # 強制 can_make_request 回傳需等待
    limiter = rate_limiter._get_domain_limiter("blocked.com")
    limiter.retry_after_until = time.time() + 5.0
    rate_limiter.wait_if_needed("https://blocked.com/x")
    assert len(slept) == 1
    assert slept[0] > 0


# ──────────────────────────────
# wait_if_needed_async
# ──────────────────────────────


def test_wait_if_needed_async_returns_zero_when_ok(rate_limiter, monkeypatch):
    async def run():
        monkeypatch.setattr(asyncio, "sleep", lambda s: asyncio.coroutine(lambda: None)())
        rate_limiter._get_domain_limiter("async-ok.com").last_request_time = 0
        return await rate_limiter.wait_if_needed_async("https://async-ok.com/x")

    result = asyncio.run(run())
    assert result == 0.0


# ──────────────────────────────
# get_global_rate_limiter 單例
# ──────────────────────────────


def test_get_global_rate_limiter_is_singleton():
    l1 = get_global_rate_limiter()
    l2 = get_global_rate_limiter()
    assert l1 is l2


# ──────────────────────────────
# rate_limited 裝飾器
# ──────────────────────────────


def test_rate_limited_decorator_calls_function(monkeypatch):
    monkeypatch.setattr(
        "src.scrapers.rate_limiter.get_global_rate_limiter",
        lambda: type("MockRL", (), {"wait_if_needed": lambda self, u: 0.0})(),
    )

    @rate_limited()
    def my_func(url):
        return f"ok:{url}"

    assert my_func(url="http://test.com") == "ok:http://test.com"


def test_rate_limited_decorator_no_url_still_calls(monkeypatch):
    monkeypatch.setattr(
        "src.scrapers.rate_limiter.get_global_rate_limiter",
        lambda: type("MockRL", (), {"wait_if_needed": lambda self, u: 0.0})(),
    )

    @rate_limited()
    def my_func(x, y):
        return x + y

    assert my_func(1, 2) == 3


# ──────────────────────────────
# async_rate_limited 裝飾器
# ──────────────────────────────


def test_async_rate_limited_decorator(monkeypatch):
    async def fake_wait(url):
        return 0.0

    mock_rl = type(
        "MockRL",
        (),
        {"wait_if_needed_async": lambda self, u: fake_wait(u)},
    )()
    monkeypatch.setattr(
        "src.scrapers.rate_limiter.get_global_rate_limiter",
        lambda: mock_rl,
    )

    @async_rate_limited()
    async def my_async_func(url):
        return f"done:{url}"

    result = asyncio.run(my_async_func(url="http://x.com"))
    assert result == "done:http://x.com"


# ──────────────────────────────
# 執行緒安全：並發記錄
# ──────────────────────────────


def test_domain_limiter_thread_safe_record(limiter):
    """多執行緒同時呼叫 record_request 不應崩潰或資料競態。"""
    errors = []

    def worker():
        try:
            for _ in range(50):
                limiter.record_request(success=True, response_time=0.01)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert limiter.stats["total_requests"] == 250


def test_rate_limiter_thread_safe_get_domain(rate_limiter):
    """並發呼叫 _get_domain_limiter 應回傳同一個 instance。"""
    results = []
    lock = threading.Lock()

    def worker():
        limiter = rate_limiter._get_domain_limiter("concurrent.com")
        with lock:
            results.append(limiter)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(r is results[0] for r in results)
