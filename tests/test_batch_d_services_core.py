import asyncio
import copy
import configparser
import threading
import time
from pathlib import Path
from types import SimpleNamespace
import sys
from typing import Any

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.models.config import ConfigManager
from src.scrapers.base_scraper import ErrorType, RetryConfig, RetryManager
from src.scrapers.cache_manager import CacheConfig, CacheManager
from src.services.web_searcher import WebSearcher


def test_config_manager_validate_config_resets_invalid_values(tmp_path):
    config_file = tmp_path / "config.ini"
    parser = configparser.ConfigParser()
    parser["search"] = {
        "batch_size": "0",
        "thread_count": "999",
        "batch_delay": "bad-value",
        "request_timeout": "20",
        "avwiki_max_concurrent": "15",
    }
    parser["cache"] = {"ttl_days": "0", "max_size_mb": "99999"}
    with config_file.open("w", encoding="utf-8") as file_obj:
        parser.write(file_obj)

    manager = ConfigManager(str(config_file))

    assert manager.getint("search", "batch_size") == 10
    assert manager.getint("search", "thread_count") == 5
    assert manager.getfloat("search", "batch_delay") == 2.0
    assert manager.getint("cache", "ttl_days") == 7
    assert manager.getint("cache", "max_size_mb") == 500


def test_retry_manager_retry_sync_tracks_retry_reason_and_success():
    retry_manager = RetryManager(RetryConfig(max_retries=2, jitter=False))
    attempts = {"count": 0}

    def flaky_operation():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("temporary failure")
        return "ok"

    result = retry_manager.retry_sync(flaky_operation)

    assert result == "ok"
    assert retry_manager.stats["total_attempts"] == 2
    assert retry_manager.stats["successful_retries"] == 1
    assert retry_manager.stats["retry_reasons"][ErrorType.UNKNOWN_ERROR] == 1


def test_retry_manager_retry_sync_does_not_depend_on_asyncio_run(monkeypatch):
    retry_manager = RetryManager(RetryConfig(max_retries=1, jitter=False))
    attempts = {"count": 0}

    def fail_then_succeed():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary failure")
        return "ok"

    monkeypatch.setattr(asyncio, "run", lambda _coroutine: (_ for _ in ()).throw(AssertionError("retry_sync 不應呼叫 asyncio.run")))

    assert retry_manager.retry_sync(fail_then_succeed) == "ok"
    assert attempts["count"] == 2


def test_retry_manager_retry_async_stops_after_non_retryable_error():
    retry_manager = RetryManager(RetryConfig(max_retries=3, jitter=False))
    attempts = {"count": 0}

    async def fail_once():
        attempts["count"] += 1
        raise Exception("no retry needed")

    retry_manager.should_retry = lambda error, attempt: False

    with pytest.raises(Exception, match="no retry needed"):
        asyncio.run(retry_manager.retry_async(fail_once))

    assert attempts["count"] == 1
    assert retry_manager.stats["failed_retries"] == 1


def test_cleanup_expired_cache_removes_index_entry_without_file_path(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(CacheManager, "_start_cleanup_task", lambda self: None)
    cache_manager = CacheManager(
        CacheConfig(
            cache_dir=str(tmp_path),
            enable_memory_cache=False,
            enable_disk_cache=True,
        )
    )
    expired_entry = {
        "created_at": time.time() - 10,
        "ttl_seconds": 1,
    }
    cache_manager._save_index(
        {
            "_metadata": {"version": "1.0", "created_at": time.time()},
            "entries": {"expired-without-file": expired_entry},
        }
    )

    cache_manager._cleanup_expired_cache()

    assert "expired-without-file" not in cache_manager._load_index()["entries"]


def test_cleanup_expired_cache_continues_after_single_entry_delete_failure(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(CacheManager, "_start_cleanup_task", lambda self: None)
    cache_manager = CacheManager(
        CacheConfig(
            cache_dir=str(tmp_path),
            enable_memory_cache=False,
            enable_disk_cache=True,
        )
    )
    index_data = {
        "_metadata": {"version": "1.0", "created_at": time.time()},
        "entries": {
            "bad": {
                "created_at": time.time() - 10,
                "ttl_seconds": 1,
                "file_path": "bad.cache",
            },
            "good": {
                "created_at": time.time() - 10,
                "ttl_seconds": 1,
                "file_path": "good.cache",
            },
        },
    }
    saved_index: dict[str, Any] = {}

    monkeypatch.setattr(cache_manager, "_load_index", lambda: copy.deepcopy(index_data))

    def fake_delete(file_path: str | None) -> None:
        if file_path == "bad.cache":
            raise OSError("boom")

    monkeypatch.setattr(cache_manager, "_delete_cache_file", fake_delete)
    monkeypatch.setattr(
        cache_manager,
        "_save_index",
        lambda data: saved_index.update(copy.deepcopy(data)) or True,
    )

    cache_manager._cleanup_expired_cache()

    assert "bad" in saved_index["entries"]
    assert "good" not in saved_index["entries"]


def test_web_searcher_search_info_returns_search_error_without_caching():
    searcher = object.__new__(WebSearcher)
    searcher.search_cache = {}
    searcher._build_code_candidates = lambda code: [code, "ABC-001"]
    searcher._search_av_wiki = lambda candidate, stop_event: None
    searcher.javdb_searcher = SimpleNamespace(
        search_javdb=lambda candidate: {
            "source": "JAVDB (安全增強版)",
            "actresses": [],
            "studio": "Mock Studio",
            "studio_code": "MOCK",
            "release_date": "2024-01-01",
            "title": "Mock Title",
            "duration": "120",
            "director": "Mock Director",
            "series": "Mock Series",
            "rating": "4.5",
            "categories": ["分類一", "分類二"],
            "search_status": "search_error",
            "search_error_reason": "暫時異常",
            "search_url": "https://example.com/search",
        }
        if candidate == "ABC-001"
        else None
    )
    searcher.studio_identifier = SimpleNamespace(
        normalize_studio_name=lambda studio_name, _code: f"正規化:{studio_name}"
    )

    result = searcher.search_info("ABC-0001", threading.Event())

    assert result["source"] == "JAVDB (安全增強版)"
    assert result["studio"] == "正規化:Mock Studio"
    assert result["search_status"] == "search_error"
    assert result["search_alias_used"] is True
    assert "ABC-0001" not in searcher.search_cache

