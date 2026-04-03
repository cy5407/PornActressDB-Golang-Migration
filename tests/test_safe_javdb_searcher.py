"""
測試 SafeJAVDBSearcher 的重試等待上限行為
"""

import httpx

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


def _build_searcher(tmp_path, monkeypatch):
    monkeypatch.setattr(SafeJAVDBSearcher, "_warmup", lambda self: None)
    return SafeJAVDBSearcher(cache_dir=str(tmp_path))


def test_403_retry_wait_over_limit_should_give_up_without_long_sleep(tmp_path, monkeypatch):
    """403 等待超過上限時應直接放棄，不進入長時間等待"""
    searcher = _build_searcher(tmp_path, monkeypatch)
    searcher.min_delay = 0.0
    searcher.max_delay = 0.0
    searcher.max_retry_wait_seconds = 60.0
    searcher.session = _DummySession(403)

    sleep_calls = []

    def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    monkeypatch.setattr(searcher_module.time, "sleep", fake_sleep)
    random_values = iter([0.0, 180.0])  # base_delay=0, 403 wait=300
    monkeypatch.setattr(
        searcher_module, "_random_delay", lambda _a, _b: next(random_values)
    )

    result = searcher.safe_request("https://javdb.com/search?q=TEST&f=all")

    assert result is None
    assert sleep_calls == [0.0]


def test_403_retry_can_reenter_without_deadlock(tmp_path, monkeypatch):
    """403 重試時應可重入 safe_request，第二次成功返回 response。"""
    searcher = SafeJAVDBSearcher(cache_dir=str(tmp_path))
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
    assert searcher.consecutive_errors == 0
    assert searcher.request_count == 2
    assert sleep_calls == [0.0, 30.0, 2.0]


def test_create_session_closes_previous_client(tmp_path, monkeypatch):
    """重建 session 前應先關閉舊 client，避免長時間累積未關閉連線。"""
    searcher = _build_searcher(tmp_path, monkeypatch)
    previous_session = _ClosableSession()
    searcher.session = previous_session

    searcher.create_session()

    assert previous_session.closed is True


def test_get_stats_includes_session_state(tmp_path, monkeypatch):
    """統計資訊應包含 session 類型與連續錯誤次數。"""
    searcher = _build_searcher(tmp_path, monkeypatch)
    searcher.consecutive_errors = 3
    searcher._session_type = "httpx"

    stats = searcher.get_stats()

    assert stats["consecutive_errors"] == 3
    assert stats["session_type"] == "httpx"
