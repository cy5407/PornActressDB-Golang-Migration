"""
測試 SafeJAVDBSearcher 的重試等待上限行為
"""

import logging
import threading
from unittest.mock import MagicMock

import httpx
import pytest

from src.services import safe_javdb_searcher as searcher_module
from src.services.safe_javdb_searcher import SafeJAVDBSearcher


class _DummySession:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def get(self, url: str):
        request = httpx.Request("GET", url)
        return httpx.Response(self.status_code, request=request)


class _SequencedDummySession:
    def __init__(self, status_codes: list[int]):
        self._status_codes = list(status_codes)

    def get(self, url: str):
        request = httpx.Request("GET", url)
        status_code = self._status_codes.pop(0)
        return httpx.Response(status_code, request=request)


class _ClosableSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_403_retry_wait_over_limit_should_give_up_without_long_sleep(tmp_path, monkeypatch):
    """403 等待超過上限時應直接放棄，不進入長時間等待。"""
    searcher = SafeJAVDBSearcher(cache_dir=str(tmp_path), warmup_enabled=False)
    searcher.min_delay = 0.0
    searcher.max_delay = 0.0
    searcher.max_retry_wait_seconds = 29.0
    searcher.session = _DummySession(403)
    monkeypatch.setattr(searcher, "create_session", lambda: None)

    sleep_calls = []

    def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    monkeypatch.setattr(searcher_module.time, "sleep", fake_sleep)
    random_values = iter([0.0, 0.0])  # base_delay=0, 403 wait=30
    monkeypatch.setattr(
        searcher_module, "_random_delay", lambda _a, _b: next(random_values)
    )

    result = searcher.safe_request("https://javdb.com/search?q=TEST&f=all")

    assert result is None
    assert sleep_calls == [0.0]


def test_403_retry_can_reenter_without_deadlock(tmp_path, monkeypatch):
    """403 重試時應可重入 safe_request，第二次成功返回 response。"""
    searcher = SafeJAVDBSearcher(cache_dir=str(tmp_path), warmup_enabled=False)
    searcher.min_delay = 0.0
    searcher.max_delay = 0.0
    searcher.max_retry_wait_seconds = 999.0
    searcher.session = _SequencedDummySession([403, 200])
    monkeypatch.setattr(searcher, "create_session", lambda: None)

    sleep_calls = []

    def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    monkeypatch.setattr(searcher_module.time, "sleep", fake_sleep)
    random_values = iter([0.0, 0.0, 0.0])  # base_delay, 403 wait, retry base_delay
    monkeypatch.setattr(
        searcher_module, "_random_delay", lambda _a, _b: next(random_values)
    )

    response = searcher.safe_request("https://javdb.com/search?q=TEST&f=all")

    assert response is not None
    assert response.status_code == 200
    assert searcher.request_count == 2
    assert searcher.consecutive_errors == 0
    assert sleep_calls == [0.0, 30.0, 2.0]


def test_429_warning_does_not_include_consecutive_error_count(
    tmp_path, monkeypatch, caplog
):
    """429 warning 與 error log 不應包含連續錯誤計數。"""
    searcher = SafeJAVDBSearcher(cache_dir=str(tmp_path), warmup_enabled=False)
    searcher.min_delay = 0.0
    searcher.max_delay = 0.0
    searcher.max_retry_wait_seconds = 999.0
    searcher.session = _DummySession(429)

    monkeypatch.setattr(searcher_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(searcher_module, "_random_delay", lambda _a, _b: 0.0)

    with caplog.at_level(logging.WARNING):
        result = searcher.safe_request("https://javdb.com/search?q=TEST&f=all")

    warning_messages = [
        record.message for record in caplog.records if record.levelno == logging.WARNING
    ]
    error_messages = [
        record.message for record in caplog.records if record.levelno == logging.ERROR
    ]

    assert result is None
    assert any("收到 429" in message for message in warning_messages)
    assert all(
        "連續錯誤" not in message
        for message in warning_messages
        if "收到 429" in message
    )
    assert any("429 重試次數過多" in message for message in error_messages)
    assert all("連續錯誤" not in message for message in error_messages)
    assert searcher.consecutive_errors == 4


def test_safe_request_daily_limit_returns_none_without_http_request(
    tmp_path, monkeypatch
):
    """達每日上限時 safe_request 應直接回傳 None，不送出 HTTP request。"""
    searcher = SafeJAVDBSearcher(cache_dir=str(tmp_path), warmup_enabled=False)
    searcher.stats["today_count"] = searcher.daily_limit
    searcher.session = MagicMock()

    monkeypatch.setattr(searcher_module.time, "sleep", MagicMock())

    result = searcher.safe_request("https://javdb.com/search?q=TEST&f=all")

    assert result is None
    searcher.session.get.assert_not_called()
    searcher_module.time.sleep.assert_not_called()


def test_create_session_closes_previous_client(tmp_path):
    """重建 session 前應先關閉舊 client，避免長時間累積未關閉連線。"""
    searcher = SafeJAVDBSearcher(cache_dir=str(tmp_path), warmup_enabled=False)
    previous_session = _ClosableSession()
    searcher.session = previous_session

    searcher.create_session()

    assert previous_session.closed is True


def test_consecutive_errors_trigger_cooldown_and_reset(tmp_path, monkeypatch):
    """連續錯誤達閾值時應冷卻、重建 session 並重置計數。"""
    searcher = SafeJAVDBSearcher(cache_dir=str(tmp_path), warmup_enabled=False)
    searcher.min_delay = 0.0
    searcher.max_delay = 0.0
    searcher.consecutive_errors = 5
    searcher.session = _DummySession(200)

    sleep_calls = []
    create_session_calls = []

    def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    monkeypatch.setattr(searcher_module.time, "sleep", fake_sleep)
    monkeypatch.setattr(searcher_module, "_random_delay", lambda _a, _b: 0.0)
    monkeypatch.setattr(
        searcher, "create_session", lambda: create_session_calls.append("called")
    )

    response = searcher.safe_request("https://javdb.com/search?q=TEST&f=all")

    assert response is not None
    assert response.status_code == 200
    assert create_session_calls == ["called"]
    assert searcher.consecutive_errors == 0
    assert sleep_calls == [300, 0.0]


def test_safe_request_does_not_hold_lock_during_cooldown_sleep(tmp_path, monkeypatch):
    """冷卻等待期間不應長時間持有 lock，避免其他搜尋整串卡住。"""
    searcher = SafeJAVDBSearcher(cache_dir=str(tmp_path), warmup_enabled=False)
    searcher.min_delay = 0.0
    searcher.max_delay = 0.0
    searcher.consecutive_errors = 5
    searcher.session = _DummySession(200)

    cooldown_started = threading.Event()
    release_cooldown = threading.Event()

    def fake_sleep(seconds: float):
        if seconds == 300:
            cooldown_started.set()
            release_cooldown.wait(timeout=1)

    monkeypatch.setattr(searcher_module.time, "sleep", fake_sleep)
    monkeypatch.setattr(searcher_module, "_random_delay", lambda _a, _b: 0.0)
    monkeypatch.setattr(searcher, "create_session", lambda: None)

    worker = threading.Thread(
        target=lambda: searcher.safe_request("https://javdb.com/search?q=TEST&f=all")
    )
    worker.start()

    assert cooldown_started.wait(timeout=1), "safe_request 應進入 cooldown 分支"
    acquired = searcher._lock.acquire(timeout=0.05)
    if acquired:
        searcher._lock.release()

    release_cooldown.set()
    worker.join(timeout=1)

    assert acquired is True


# ──────────────────────────────────────────────────────────────────────────────
# 測試：搜尋結果番號不匹配時不應 fallback 使用第一筆
# ──────────────────────────────────────────────────────────────────────────────

def _make_search_html_with_mismatched_code(video_code: str) -> str:
    """產生一個搜尋結果頁面，其中只有與 video_code 不符的影片連結"""
    return f"""
    <html><body>
    <div class="item">
      <a href="/v/AWTB005">
        <div class="video-title">AWTB-005 淫語中出しソープ Best Collection 5</div>
      </a>
    </div>
    </body></html>
    """


def _make_detail_html_with_wrong_code(wrong_code: str) -> str:
    """產生一個詳情頁面，標題含有錯誤番號"""
    return f"""
    <html><body>
    <h2 class="title">{wrong_code} 淫語中出しソープ</h2>
    <div class="panel-block">
      <strong>演員:</strong>
      <a href="/actors/1" class="value">田中花子 <strong class="symbol female">♀</strong></a>
    </div>
    </body></html>
    """


def test_search_javdb_no_fallback_on_mismatch(tmp_path, monkeypatch):
    """搜尋結果無精確匹配番號時，應回傳 None，不得 fallback 使用第一筆結果。"""
    searcher = SafeJAVDBSearcher(cache_dir=str(tmp_path), warmup_enabled=False)
    searcher.min_delay = 0.0
    searcher.max_delay = 0.0

    call_count = [0]

    def fake_safe_request(url: str):
        call_count[0] += 1
        request = httpx.Request("GET", url)
        if "/search" in url:
            html = _make_search_html_with_mismatched_code("WTB-045")
        else:
            html = _make_detail_html_with_wrong_code("AWTB-005")
        return httpx.Response(200, text=html, request=request)

    monkeypatch.setattr(searcher, "safe_request", fake_safe_request)

    result = searcher.search_javdb("WTB-045")

    # 不應找到任何結果（不得 fallback）
    assert result is None
    # 只應發出一次搜尋請求，不應發出詳情頁請求
    assert call_count[0] == 1, f"不應存取詳情頁，但執行了 {call_count[0]} 次請求"


def test_search_javdb_detail_page_code_mismatch_returns_none(tmp_path, monkeypatch):
    """就算詳情頁被訪問，若頁面番號與搜尋目標不符，應回傳 None。"""
    searcher = SafeJAVDBSearcher(cache_dir=str(tmp_path), warmup_enabled=False)
    searcher.min_delay = 0.0
    searcher.max_delay = 0.0

    # 直接測試 _parse_detail_page 的二次驗證
    wrong_html = _make_detail_html_with_wrong_code("AWTB-005")
    request = httpx.Request("GET", "https://javdb.com/v/AWTB005")
    fake_response = httpx.Response(200, text=wrong_html, request=request)

    result = searcher._parse_detail_page(fake_response, "WTB-045", "https://javdb.com/v/AWTB005")

    assert result is None, "詳情頁番號不符時應回傳 None"
