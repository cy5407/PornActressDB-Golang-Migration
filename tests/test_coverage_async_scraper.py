"""
補測 AsyncWebScraper / BatchWebScraper 的純邏輯部分。
測試目標：驗證真實行為（重試決策、UA 輪替、統計計算），不跑真實網路。
"""
import asyncio
import time
import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
from src.scrapers.async_scraper import (
    AsyncWebScraper,
    BatchWebScraper,
    ScrapingConfig,
    ScrapingResult,
)


# ──────────────────────────────
# Dataclass 預設值
# ──────────────────────────────


def test_scraping_config_defaults():
    cfg = ScrapingConfig()
    assert cfg.max_concurrent == 3
    assert cfg.max_retries == 3
    assert cfg.enable_cache is True
    assert cfg.user_agent_rotation is True


def test_scraping_result_defaults():
    r = ScrapingResult(url="http://example.com", success=True)
    assert r.from_cache is False
    assert r.error is None
    assert r.response_time == 0.0


# ──────────────────────────────
# _should_retry_result() - 重試決策
# 這是最關鍵的邏輯：錯誤的重試判斷會浪費請求或漏掉重試
# ──────────────────────────────


def _result(status_code=None, error=None) -> ScrapingResult:
    return ScrapingResult(
        url="http://test.com",
        success=False,
        status_code=status_code,
        error=error,
    )


@pytest.fixture
def scraper():
    fake_rate_limiter = SimpleNamespace(get_stats=lambda: {})
    fake_cache_manager = SimpleNamespace(get_stats=lambda: {})
    with patch("src.scrapers.async_scraper.get_global_rate_limiter", return_value=fake_rate_limiter), \
         patch("src.scrapers.async_scraper.get_global_cache_manager", return_value=fake_cache_manager):
        return AsyncWebScraper()


def test_should_retry_when_no_status_code(scraper):
    """status_code=None 表示網路層錯誤，應重試。"""
    assert scraper._should_retry_result(_result(status_code=None)) is True


def test_should_retry_on_408(scraper):
    """408 Request Timeout → 應重試。"""
    assert scraper._should_retry_result(_result(status_code=408)) is True


def test_should_retry_on_429(scraper):
    """429 Too Many Requests → 應重試。"""
    assert scraper._should_retry_result(_result(status_code=429)) is True


def test_should_not_retry_on_404(scraper):
    """404 Not Found → 不應重試（永久失敗）。"""
    assert scraper._should_retry_result(_result(status_code=404)) is False


def test_should_not_retry_on_403(scraper):
    """403 Forbidden → 不應重試（存取被拒）。"""
    assert scraper._should_retry_result(_result(status_code=403)) is False


def test_should_not_retry_on_400(scraper):
    assert scraper._should_retry_result(_result(status_code=400)) is False


def test_should_retry_on_500(scraper):
    """500 Server Error → 應重試（服務器暫時問題）。"""
    assert scraper._should_retry_result(_result(status_code=500)) is True


def test_should_retry_on_503(scraper):
    """503 Service Unavailable → 應重試。"""
    assert scraper._should_retry_result(_result(status_code=503)) is True


def test_should_not_retry_on_301(scraper):
    """301 Redirect → 不是 4xx，應重試（非錯誤）。
    但 301 只會出現在 response.status >= 400 的分支之前，
    此函式只在 success=False 的情況下被呼叫，所以 301 理論上不會到這裡。
    測試確認邏輯本身對非 4xx 回傳 True。
    """
    assert scraper._should_retry_result(_result(status_code=301)) is True


# ──────────────────────────────
# _get_headers() - User-Agent 輪替
# ──────────────────────────────


def test_get_headers_rotates_user_agent(scraper):
    """每次呼叫應輪替 UA，避免被偵測為 bot。"""
    ua_set = set()
    for _ in range(len(scraper.user_agents) + 1):
        headers = scraper._get_headers()
        ua_set.add(headers["User-Agent"])
    # 至少用過 2 個不同的 UA
    assert len(ua_set) > 1


def test_get_headers_index_wraps_around(scraper):
    """UA index 超出清單長度時應回到 0。"""
    scraper.current_ua_index = len(scraper.user_agents) - 1
    scraper._get_headers()  # 使用最後一個，index 會 wrap 到 0
    # 下一次應使用 index=0 的 UA
    headers = scraper._get_headers()
    assert headers["User-Agent"] == scraper.user_agents[0]


def test_get_headers_no_rotation_uses_first(scraper):
    """user_agent_rotation=False 應固定使用第一個 UA。"""
    scraper.config.user_agent_rotation = False
    ua1 = scraper._get_headers()["User-Agent"]
    ua2 = scraper._get_headers()["User-Agent"]
    assert ua1 == ua2 == scraper.user_agents[0]


def test_get_headers_has_required_fields(scraper):
    headers = scraper._get_headers()
    for key in ("Accept", "Accept-Language", "User-Agent", "DNT"):
        assert key in headers


# ──────────────────────────────
# _update_stats()
# ──────────────────────────────


def test_update_stats_success(scraper):
    scraper._update_stats("example.com", True, 0.5)
    assert scraper.stats["total_requests"] == 1
    assert scraper.stats["successful_requests"] == 1
    assert scraper.stats["failed_requests"] == 0
    assert scraper.stats["total_response_time"] == 0.5
    assert scraper.stats["requests_by_domain"]["example.com"]["total"] == 1
    assert scraper.stats["requests_by_domain"]["example.com"]["success"] == 1


def test_update_stats_failure(scraper):
    scraper._update_stats("example.com", False, 1.0)
    assert scraper.stats["failed_requests"] == 1
    assert scraper.stats["requests_by_domain"]["example.com"]["success"] == 0


def test_update_stats_encoding(scraper):
    scraper._update_stats("example.com", True, 0.1, encoding="utf-8")
    assert scraper.stats["encoding_stats"]["utf-8"] == 1


def test_update_stats_encoding_accumulates(scraper):
    scraper._update_stats("a.com", True, 0.1, encoding="utf-8")
    scraper._update_stats("b.com", True, 0.1, encoding="utf-8")
    assert scraper.stats["encoding_stats"]["utf-8"] == 2


def test_update_stats_domain_accumulates(scraper):
    scraper._update_stats("a.com", True, 0.1)
    scraper._update_stats("a.com", False, 0.2)
    assert scraper.stats["requests_by_domain"]["a.com"]["total"] == 2
    assert scraper.stats["requests_by_domain"]["a.com"]["success"] == 1


# ──────────────────────────────
# get_stats() - 邊界條件
# ──────────────────────────────


def test_get_stats_no_requests(scraper):
    """0 請求時不應有 ZeroDivisionError。"""
    stats = scraper.get_stats()
    assert "0" in stats["success_rate"]
    assert "0" in stats["average_response_time"]
    assert "0" in stats["cache_hit_rate"]


def test_get_stats_calculates_correctly(scraper):
    scraper._update_stats("a.com", True, 0.4)
    scraper._update_stats("a.com", True, 0.6)
    scraper._update_stats("a.com", False, 1.0)
    stats = scraper.get_stats()
    assert stats["success_rate"] == "66.7%"
    assert stats["average_response_time"] == "0.67s"


# ──────────────────────────────
# reset_stats()
# ──────────────────────────────


def test_reset_stats_clears_all(scraper):
    scraper._update_stats("a.com", True, 1.0, encoding="utf-8")
    scraper.stats["cache_hits"] = 3
    scraper.reset_stats()
    assert scraper.stats["total_requests"] == 0
    assert scraper.stats["successful_requests"] == 0
    assert scraper.stats["failed_requests"] == 0
    assert scraper.stats["cache_hits"] == 0
    assert scraper.stats["total_response_time"] == 0.0
    assert scraper.stats["requests_by_domain"] == {}
    assert scraper.stats["encoding_stats"] == {}


# ──────────────────────────────
# scrape_multiple() - 空列表
# ──────────────────────────────


def test_scrape_multiple_empty_urls(scraper):
    result = asyncio.run(scraper.scrape_multiple([]))
    assert result == []


# ──────────────────────────────
# BatchWebScraper
# ──────────────────────────────


@pytest.fixture
def batch_scraper():
    fake_rate_limiter = SimpleNamespace(get_stats=lambda: {})
    fake_cache_manager = SimpleNamespace(get_stats=lambda: {})
    with patch("src.scrapers.async_scraper.get_global_rate_limiter", return_value=fake_rate_limiter), \
         patch("src.scrapers.async_scraper.get_global_cache_manager", return_value=fake_cache_manager):
        return BatchWebScraper(batch_size=3)


class FakeBatchWorker:
    def __init__(self, results_by_url):
        self.results_by_url = results_by_url
        self.calls = []

    def scrape_multiple_sync(self, urls, progress_callback=None):
        self.calls.append(list(urls))
        results = []
        for url in urls:
            result = self.results_by_url[url]
            results.append(result)
            if progress_callback:
                status = "✅ 成功" if result.success else f"❌ 失敗: {result.error}"
                progress_callback(f"{url}: {status}")
        return results


def test_batch_scraper_empty_urls(batch_scraper):
    result = batch_scraper.scrape_in_batches([])
    assert result == []


def test_batch_scraper_calls_progress_callback(batch_scraper):
    """progress_callback 應被呼叫於每批開始。"""
    called = []

    def on_progress(msg):
        called.append(msg)

    batch_scraper.scraper = FakeBatchWorker(
        {
            "http://a.com": ScrapingResult(url="http://a.com", success=True),
        }
    )

    with patch("time.sleep"):  # 跳過批次間 sleep
        batch_scraper.scrape_in_batches(["http://a.com"], progress_callback=on_progress)

    assert any("處理批次 1/1" in msg for msg in called)
    assert any("http://a.com: ✅ 成功" in msg for msg in called)


def test_batch_scraper_no_inter_batch_pause_for_single_batch(batch_scraper):
    """只有一批時不應呼叫 time.sleep。"""
    batch_scraper.scraper = FakeBatchWorker(
        {
            "http://a.com": ScrapingResult(url="http://a.com", success=True),
        }
    )

    with patch("time.sleep") as mock_sleep:
        batch_scraper.scrape_in_batches(["http://a.com"])

    mock_sleep.assert_not_called()


def test_batch_scraper_pauses_between_batches(batch_scraper):
    """多批時應呼叫 time.sleep 進行批次間暫停。"""
    batch_scraper.scraper = FakeBatchWorker(
        {
            "http://a.com": ScrapingResult(url="http://a.com", success=True),
            "http://b.com": ScrapingResult(url="http://b.com", success=True),
            "http://c.com": ScrapingResult(url="http://c.com", success=True),
            "http://d.com": ScrapingResult(url="http://d.com", success=True),
        }
    )

    urls = ["http://a.com", "http://b.com", "http://c.com", "http://d.com"]  # 4 urls, batch_size=3 → 2 batches

    with patch("time.sleep") as mock_sleep:
        batch_scraper.scrape_in_batches(urls)

    mock_sleep.assert_called_once_with(2.0)
    assert batch_scraper.scraper.calls == [
        ["http://a.com", "http://b.com", "http://c.com"],
        ["http://d.com"],
    ]


def test_batch_scraper_collects_all_results(batch_scraper):
    """所有批次的結果應被合併回傳。"""
    batch_scraper.scraper = FakeBatchWorker(
        {
            "http://a.com": ScrapingResult(url="http://a.com", success=True),
            "http://b.com": ScrapingResult(url="http://b.com", success=True),
            "http://c.com": ScrapingResult(url="http://c.com", success=True),
            "http://d.com": ScrapingResult(
                url="http://d.com", success=False, error="timeout"
            ),
        }
    )

    urls = ["http://a.com", "http://b.com", "http://c.com", "http://d.com"]

    with patch("time.sleep"):
        results = batch_scraper.scrape_in_batches(urls)

    assert len(results) == 4
    assert sum(1 for r in results if r.success) == 3
    assert [r.url for r in results] == urls


# ──────────────────────────────
# clear_cache（line 398-399）
# ──────────────────────────────


def test_clear_cache_delegates_to_cache_manager(scraper):
    """clear_cache 應呼叫 cache_manager.clear_cache()（lines 398-399）"""
    scraper.cache_manager = SimpleNamespace(clear_cache=MagicMock(), get_stats=lambda: {})
    scraper.clear_cache()
    scraper.cache_manager.clear_cache.assert_called_once()


# ──────────────────────────────
# _make_request（lines 129-133, 172-211）
# ──────────────────────────────

def _make_mock_session(status=200, content=b"<html>test</html>", raise_on_get=None):
    """建立模擬 aiohttp.ClientSession"""
    response = MagicMock()
    response.status = status
    response.read = AsyncMock(return_value=content)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    if raise_on_get:
        session.get = MagicMock(side_effect=raise_on_get)
    else:
        session.get = MagicMock(return_value=response)
    return session


def _run_async(coro):
    """在測試中同步執行非同步協程"""
    return asyncio.run(coro)


def _make_scraper():
    """建立無網路的 AsyncWebScraper"""
    fake_rate_limiter = SimpleNamespace(
        wait_if_needed_async=AsyncMock(), get_stats=lambda: {}
    )
    fake_cache_manager = SimpleNamespace(
        get_async=AsyncMock(return_value=None),
        set_async=AsyncMock(),
        clear_cache=MagicMock(),
        get_stats=lambda: {},
    )
    with patch("src.scrapers.async_scraper.get_global_rate_limiter", return_value=fake_rate_limiter), \
         patch("src.scrapers.async_scraper.get_global_cache_manager", return_value=fake_cache_manager):
        s = AsyncWebScraper()
    s.rate_limiter = fake_rate_limiter
    s.cache_manager = fake_cache_manager
    return s


def test_make_request_returns_cache_hit():
    """快取命中時應直接回傳快取資料（lines 129-133）"""
    s = _make_scraper()
    s.cache_manager.get_async = AsyncMock(return_value="cached_html")
    session = MagicMock()
    result = _run_async(s._make_request(session, "http://example.com/page"))
    assert result.success is True
    assert result.from_cache is True
    assert result.data == "cached_html"
    assert s.stats["cache_hits"] == 1


def test_make_request_http_400_returns_failure():
    """HTTP 4xx 應回傳 success=False（lines 160-169）"""
    s = _make_scraper()
    session = _make_mock_session(status=404)
    result = _run_async(s._make_request(session, "http://example.com/notfound"))
    assert result.success is False
    assert result.status_code == 404


def test_make_request_success_200():
    """HTTP 200 應回傳 success=True，並設定快取（lines 186-193）"""
    s = _make_scraper()
    session = _make_mock_session(status=200, content=b"<html>ok</html>")
    result = _run_async(s._make_request(session, "http://example.com/ok"))
    assert result.success is True
    assert result.status_code == 200
    assert s.cache_manager.set_async.called


def test_make_request_timeout_error():
    """TimeoutError 應回傳 success=False（lines 195-199）"""
    s = _make_scraper()
    session = _make_mock_session(raise_on_get=TimeoutError("timed out"))
    result = _run_async(s._make_request(session, "http://example.com/slow"))
    assert result.success is False
    assert "超時" in result.error


def test_make_request_client_error():
    """aiohttp.ClientError 應回傳 success=False（lines 201-205）"""
    s = _make_scraper()
    session = _make_mock_session(raise_on_get=aiohttp.ClientError("conn refused"))
    result = _run_async(s._make_request(session, "http://example.com/bad"))
    assert result.success is False
    assert "客戶端錯誤" in result.error


def test_make_request_unknown_exception():
    """未知例外應回傳 success=False（lines 207-211）"""
    s = _make_scraper()
    session = _make_mock_session(raise_on_get=RuntimeError("unexpected"))
    result = _run_async(s._make_request(session, "http://example.com/crash"))
    assert result.success is False
    assert "未知錯誤" in result.error


# ──────────────────────────────
# _make_request_with_retry（lines 224, 232-245）
# ──────────────────────────────


def test_make_request_with_retry_success_first_attempt():
    """第一次就成功時不應重試（line 224）"""
    s = _make_scraper()
    success_result = ScrapingResult(url="http://a.com", success=True, data="ok")
    s._make_request = AsyncMock(return_value=success_result)
    session = MagicMock()
    result = _run_async(s._make_request_with_retry(session, "http://a.com"))
    assert result.success is True
    assert s._make_request.call_count == 1


def test_make_request_with_retry_retries_on_failure():
    """可重試的失敗應觸發重試（lines 232-237）"""
    s = _make_scraper()
    fail_result = ScrapingResult(url="http://a.com", success=False, status_code=500)
    success_result = ScrapingResult(url="http://a.com", success=True, data="ok")
    s._make_request = AsyncMock(side_effect=[fail_result, success_result])
    session = MagicMock()
    with patch("asyncio.sleep", new=AsyncMock()):
        result = _run_async(s._make_request_with_retry(session, "http://a.com"))
    assert result.success is True
    assert s._make_request.call_count == 2


def test_make_request_with_retry_no_retry_on_404():
    """404 不應重試，立即回傳（line 229）"""
    s = _make_scraper()
    fail_result = ScrapingResult(url="http://a.com", success=False, status_code=404)
    s._make_request = AsyncMock(return_value=fail_result)
    session = MagicMock()
    result = _run_async(s._make_request_with_retry(session, "http://a.com"))
    assert result.success is False
    assert s._make_request.call_count == 1


def test_make_request_with_retry_all_fail():
    """所有重試都失敗時應回傳最後一個結果（lines 244-247）"""
    s = _make_scraper()
    s.config.max_retries = 2
    fail_result = ScrapingResult(url="http://a.com", success=False, status_code=503)
    s._make_request = AsyncMock(return_value=fail_result)
    session = MagicMock()
    with patch("asyncio.sleep", new=AsyncMock()):
        result = _run_async(s._make_request_with_retry(session, "http://a.com"))
    assert result.success is False
    assert s._make_request.call_count == 3  # initial + 2 retries


def test_make_request_with_retry_exception_in_attempt():
    """重試過程中例外應被捕獲並繼續（lines 239-242）"""
    s = _make_scraper()
    s.config.max_retries = 1
    s._make_request = AsyncMock(side_effect=RuntimeError("boom"))
    session = MagicMock()
    with patch("asyncio.sleep", new=AsyncMock()):
        result = _run_async(s._make_request_with_retry(session, "http://a.com"))
    assert result.success is False


# ──────────────────────────────
# scrape_multiple（lines 267-308）
# ──────────────────────────────


def test_scrape_multiple_with_exception_result():
    """asyncio.gather 回傳 Exception 時應包裝成失敗 ScrapingResult（lines 297-301）"""
    s = _make_scraper()

    async def mock_scrape(*args, **kwargs):
        raise RuntimeError("gather exception")

    mock_connector = MagicMock()
    mock_connector.__aenter__ = AsyncMock(return_value=mock_connector)
    mock_connector.__aexit__ = AsyncMock(return_value=False)
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch.object(s, "_make_request_with_retry", side_effect=mock_scrape):
        with patch("aiohttp.TCPConnector", return_value=mock_connector):
            with patch("aiohttp.ClientSession", return_value=mock_session):
                results = _run_async(s.scrape_multiple(["http://a.com"]))
    assert len(results) == 1
    assert results[0].success is False


def test_scrape_multiple_with_progress_callback():
    """progress_callback 應被呼叫（lines 277-279）"""
    s = _make_scraper()
    messages = []
    ok_result = ScrapingResult(url="http://a.com", success=True, data="ok")

    async def mock_retry(session, url):
        return ok_result

    mock_connector = MagicMock()
    mock_connector.__aenter__ = AsyncMock(return_value=mock_connector)
    mock_connector.__aexit__ = AsyncMock(return_value=False)
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    with patch.object(s, "_make_request_with_retry", side_effect=mock_retry):
        with patch("aiohttp.TCPConnector", return_value=mock_connector):
            with patch("aiohttp.ClientSession", return_value=mock_session):
                results = _run_async(
                    s.scrape_multiple(["http://a.com"], progress_callback=messages.append)
                )
    assert len(results) == 1
    assert results[0].success is True
    assert len(messages) == 1


# ──────────────────────────────
# scrape_multiple_sync（lines 314-340）
# ──────────────────────────────


def test_scrape_multiple_sync_no_loop(scraper):
    """沒有執行中的事件循環時應用 loop.run_until_complete（lines 334-337）"""
    ok_result = [ScrapingResult(url="http://a.com", success=True)]
    with patch.object(scraper, "scrape_multiple", new=AsyncMock(return_value=ok_result)):
        loop = asyncio.new_event_loop()
        with patch("asyncio.get_event_loop", return_value=loop):
            results = scraper.scrape_multiple_sync(["http://a.com"])
        loop.close()
    assert results[0].success is True


def test_scrape_multiple_sync_runtime_error_fallback(scraper):
    """RuntimeError 時應 fallback 到 asyncio.run（lines 338-340）"""
    ok_result = [ScrapingResult(url="http://a.com", success=True)]
    with patch.object(scraper, "scrape_multiple", new=AsyncMock(return_value=ok_result)):
        with patch("asyncio.get_event_loop", side_effect=RuntimeError("no loop")):
            with patch("asyncio.run", return_value=ok_result) as mock_run:
                results = scraper.scrape_multiple_sync(["http://a.com"])
    assert mock_run.called


def test_scrape_multiple_sync_loop_is_running(scraper):
    """事件循環已在執行時應透過 ThreadPoolExecutor 執行（lines 319-333）"""
    ok_result = [ScrapingResult(url="http://a.com", success=True)]

    # 建立一個假的 loop 回報 is_running() = True
    mock_loop = MagicMock()
    mock_loop.is_running.return_value = True

    with patch.object(scraper, "scrape_multiple", new=AsyncMock(return_value=ok_result)):
        with patch("asyncio.get_event_loop", return_value=mock_loop):
            # ThreadPoolExecutor 的 future.result() 直接回傳 ok_result
            import concurrent.futures
            mock_future = MagicMock()
            mock_future.result.return_value = ok_result
            mock_executor = MagicMock()
            mock_executor.__enter__ = MagicMock(return_value=mock_executor)
            mock_executor.__exit__ = MagicMock(return_value=False)
            mock_executor.submit.return_value = mock_future
            with patch("concurrent.futures.ThreadPoolExecutor", return_value=mock_executor):
                results = scraper.scrape_multiple_sync(["http://a.com"])
    assert results == ok_result
