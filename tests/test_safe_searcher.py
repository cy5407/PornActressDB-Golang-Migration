import json
import logging
import threading
import time
from pathlib import Path

import pytest

from src.services import safe_searcher as safe_searcher_module
from src.services.safe_searcher import CacheEntry, RequestConfig, SafeSearcher


def test_get_headers_without_rotation_returns_base_header(tmp_path):
    searcher = SafeSearcher(
        config=RequestConfig(enable_cache=False, rotate_headers=False),
        cache_file=str(tmp_path / "cache.json"),
    )

    headers = searcher.get_headers()

    assert headers is searcher.browser_headers[0]
    assert searcher.current_header_index == 0


def test_get_headers_rotates_and_randomizes_cache_control(tmp_path, monkeypatch):
    searcher = SafeSearcher(
        config=RequestConfig(enable_cache=False, rotate_headers=True),
        cache_file=str(tmp_path / "cache.json"),
    )
    monkeypatch.setattr(
        safe_searcher_module, "secure_choice", lambda _choices: "no-store"
    )

    first = searcher.get_headers()
    second = searcher.get_headers()

    assert first["Cache-Control"] == "no-store"
    assert second["Cache-Control"] == "no-store"
    assert first["User-Agent"] != second["User-Agent"]
    assert searcher.current_header_index == 2


def test_wait_for_next_request_uses_min_interval_when_range_collapses(
    tmp_path, monkeypatch
):
    searcher = SafeSearcher(
        config=RequestConfig(
            min_interval=1.0,
            max_interval=1.0,
            enable_cache=False,
            rotate_headers=False,
        ),
        cache_file=str(tmp_path / "cache.json"),
    )
    searcher.last_request_time = 10.0
    times = iter([10.25, 11.0])
    sleeps = []
    monkeypatch.setattr(safe_searcher_module.time, "time", lambda: next(times))
    monkeypatch.setattr(safe_searcher_module.time, "sleep", sleeps.append)

    searcher._wait_for_next_request()

    assert sleeps == [pytest.approx(0.75)]
    assert searcher.last_request_time == 11.0


def test_safe_request_injects_default_timeout_when_missing(tmp_path):
    searcher = SafeSearcher(
        config=RequestConfig(
            min_interval=0.0,
            max_interval=0.0,
            enable_cache=False,
            rotate_headers=False,
        ),
        cache_file=str(tmp_path / "cache.json"),
    )
    captured = {}

    def fake_request(url, *args, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return {"ok": True}

    result = searcher.safe_request(fake_request, "https://example.com")

    assert result == {"ok": True}
    assert captured["kwargs"]["timeout"] == 30


def test_safe_request_retries_and_rotates_headers(tmp_path, monkeypatch):
    searcher = SafeSearcher(
        config=RequestConfig(
            min_interval=0.0,
            max_interval=0.0,
            enable_cache=False,
            max_retries=1,
            rotate_headers=True,
        ),
        cache_file=str(tmp_path / "cache.json"),
    )
    monkeypatch.setattr(
        safe_searcher_module, "secure_choice", lambda _choices: "no-cache"
    )
    monkeypatch.setattr(safe_searcher_module.time, "sleep", lambda _seconds: None)
    user_agents = []

    def flaky_request(_url, *args, **kwargs):
        user_agents.append(kwargs["headers"]["User-Agent"])
        if len(user_agents) == 1:
            raise RuntimeError("temporary")
        return {"ok": True}

    result = searcher.safe_request(flaky_request, "https://example.com")

    assert result == {"ok": True}
    assert len(user_agents) == 2
    assert user_agents[0] != user_agents[1]


def test_safe_request_raises_last_exception_after_retries(tmp_path, monkeypatch):
    searcher = SafeSearcher(
        config=RequestConfig(
            min_interval=0.0,
            max_interval=0.0,
            enable_cache=False,
            max_retries=1,
            rotate_headers=False,
        ),
        cache_file=str(tmp_path / "cache.json"),
    )
    monkeypatch.setattr(safe_searcher_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="network down"):
        searcher.safe_request(
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("network down")
            ),
            "https://example.com",
        )


def test_safe_request_same_url_concurrent_calls_only_request_once(tmp_path):
    searcher = SafeSearcher(
        config=RequestConfig(
            min_interval=0.0,
            max_interval=0.0,
            enable_cache=True,
            rotate_headers=False,
        ),
        cache_file=str(tmp_path / "cache.json"),
    )
    call_count = 0
    call_lock = threading.Lock()
    results = []

    def fake_request(_url, *args, **kwargs):
        nonlocal call_count
        with call_lock:
            call_count += 1
        time.sleep(0.05)
        return {"value": "cached"}

    def worker():
        results.append(
            searcher.safe_request(fake_request, "https://example.com/resource")
        )

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert call_count == 1
    assert results == [{"value": "cached"}, {"value": "cached"}]


def test_load_cache_ignores_invalid_json(tmp_path):
    cache_file = tmp_path / "search_cache.json"
    cache_file.write_text("{broken", encoding="utf-8")

    searcher = SafeSearcher(cache_file=str(cache_file))

    assert searcher.cache == {}


def test_cache_validation_and_cleanup_respect_expiration(tmp_path, monkeypatch):
    searcher = SafeSearcher(
        config=RequestConfig(enable_cache=True, cache_duration=10),
        cache_file=str(tmp_path / "cache.json"),
    )
    monkeypatch.setattr(safe_searcher_module.time, "time", lambda: 100.0)
    fresh = CacheEntry(
        data={"value": "fresh"},
        timestamp=95.0,
        url="https://example.com/fresh",
        request_hash="fresh",
    )
    expired = CacheEntry(
        data={"value": "expired"},
        timestamp=80.0,
        url="https://example.com/expired",
        request_hash="expired",
    )
    searcher.cache = {"fresh": fresh, "expired": expired}

    searcher._cleanup_expired_cache()

    assert searcher._is_cache_valid(fresh) is True
    assert searcher._is_cache_valid(expired) is False
    assert list(searcher.cache) == ["fresh"]


def test_cache_validation_disabled(tmp_path):
    searcher = SafeSearcher(
        config=RequestConfig(enable_cache=False),
        cache_file=str(tmp_path / "cache.json"),
    )
    entry = CacheEntry(
        data={"value": "fresh"},
        timestamp=time.time(),
        url="https://example.com",
        request_hash="hash",
    )

    assert searcher._is_cache_valid(entry) is False
    assert searcher.get_from_cache("https://example.com") is None


def test_save_cache_keeps_previous_file_when_dump_fails(tmp_path, monkeypatch):
    cache_file = tmp_path / "search_cache.json"
    cache_file.write_text('{"stable": true}', encoding="utf-8")
    searcher = SafeSearcher(cache_file=str(cache_file))
    searcher.save_to_cache("https://example.com", {"value": "ok"})

    def fake_json_dump(data, file_obj, ensure_ascii=False, indent=2):
        file_obj.write('{"broken":')
        raise ValueError("boom")

    monkeypatch.setattr(safe_searcher_module, "json_dump", fake_json_dump)

    searcher._save_cache()

    assert cache_file.read_text(encoding="utf-8") == '{"stable": true}'


def test_save_cache_skips_unserializable_entries(tmp_path):
    cache_file = tmp_path / "search_cache.json"
    searcher = SafeSearcher(cache_file=str(cache_file))
    searcher.cache = {
        "good": CacheEntry(
            data={"ok": True},
            timestamp=1.0,
            url="https://example.com/good",
            request_hash="good",
        ),
        "bad": CacheEntry(
            data=object(),
            timestamp=1.0,
            url="https://example.com/bad",
            request_hash="bad",
        ),
    }

    searcher._save_cache()

    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert list(payload) == ["good"]


def test_save_to_cache_rejects_unserializable_data(tmp_path):
    searcher = SafeSearcher(cache_file=str(tmp_path / "cache.json"))

    searcher.save_to_cache("https://example.com", object())

    assert searcher.cache == {}


def test_contains_beautifulsoup_detects_nested_values():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup("<p>hello</p>", "html.parser")

    assert SafeSearcher._contains_beautifulsoup({"nested": [soup]}) is True
    assert SafeSearcher._contains_beautifulsoup({"nested": ["plain"]}) is False


def test_get_from_cache_logs_sanitized_url(tmp_path, caplog):
    searcher = SafeSearcher(
        config=RequestConfig(
            min_interval=0.0,
            max_interval=0.0,
            enable_cache=True,
            rotate_headers=False,
        ),
        cache_file=str(tmp_path / "cache.json"),
    )
    raw_url = "https://javdb.com/search?q=SSIS-123&f=all"
    searcher.save_to_cache(raw_url, {"value": "cached"})

    with caplog.at_level(logging.DEBUG):
        result = searcher.get_from_cache(raw_url)

    assert result == {"value": "cached"}
    assert raw_url not in caplog.text
    assert "search_url_hash=" in caplog.text
