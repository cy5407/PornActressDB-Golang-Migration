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


def test_403_retry_wait_over_limit_should_give_up_without_long_sleep(tmp_path, monkeypatch):
    """403 等待超過上限時應直接放棄，不進入長時間等待"""
    searcher = SafeJAVDBSearcher(cache_dir=str(tmp_path))
    searcher.min_delay = 0.0
    searcher.max_delay = 0.0
    searcher.max_retry_wait_seconds = 60.0
    searcher.session = _DummySession(403)

    sleep_calls = []

    def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    uniform_values = iter([0.0, 180.0])  # base_delay=0, 403 wait=300

    def fake_uniform(_a, _b):
        return next(uniform_values)

    monkeypatch.setattr(searcher_module.time, "sleep", fake_sleep)
    monkeypatch.setattr(searcher_module.random, "uniform", fake_uniform)

    result = searcher.safe_request("https://javdb.com/search?q=TEST&f=all")

    assert result is None
    assert sleep_calls == [0.0]
