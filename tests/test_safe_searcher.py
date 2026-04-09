import threading
import time
from pathlib import Path

import logging

from src.services import safe_searcher as safe_searcher_module
from src.services.safe_searcher import RequestConfig, SafeSearcher


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
