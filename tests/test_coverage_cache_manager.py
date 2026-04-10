"""
cache_manager.py 覆蓋率補測
目標：覆蓋 Go 委派路徑、_init_index 錯誤路徑、stats / cleanup 方法。
"""
import asyncio
import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.scrapers.cache_manager import CACHE_PAYLOAD_VERSION, CacheConfig, CacheEntry, CacheManager


# ---------- helper ----------

def _make_cache_manager(tmp_path, monkeypatch, **cfg_overrides) -> CacheManager:
    """建立不啟動背景執行緒的 CacheManager。"""
    monkeypatch.setattr(CacheManager, "_start_cleanup_task", lambda self: None)
    config = CacheConfig(cache_dir=str(tmp_path), **cfg_overrides)
    return CacheManager(config)


def _make_payload(value, compressed: bool = False) -> bytes:
    """產生符合 _get_go 期望格式的 payload：flag_byte + serialized_json。"""
    import gzip as _gzip

    raw = json.dumps({"version": CACHE_PAYLOAD_VERSION, "value": value}, ensure_ascii=False).encode("utf-8")
    if compressed:
        body = _gzip.compress(raw)
        return b"\x01" + body
    return b"\x00" + raw


# ============================================================
# _init_index 錯誤路徑
# ============================================================

def test_init_index_creates_when_missing(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    index = mgr._load_index()
    assert "entries" in index


def test_init_index_repairs_missing_entries_key(tmp_path, monkeypatch):
    monkeypatch.setattr(CacheManager, "_start_cleanup_task", lambda self: None)
    index_path = tmp_path / "cache_index.json"
    index_path.write_text('{"_metadata": {}}', encoding="utf-8")
    mgr = CacheManager(CacheConfig(cache_dir=str(tmp_path)))
    index = mgr._load_index()
    assert "entries" in index


def test_init_index_handles_corrupt_json(tmp_path, monkeypatch):
    monkeypatch.setattr(CacheManager, "_start_cleanup_task", lambda self: None)
    index_path = tmp_path / "cache_index.json"
    index_path.write_text("NOT VALID JSON {{{{", encoding="utf-8")
    mgr = CacheManager(CacheConfig(cache_dir=str(tmp_path)))
    assert mgr is not None


# ============================================================
# _serialize_value / _deserialize_value
# ============================================================

def test_serialize_deserialize_roundtrip(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_compression=False)
    data = {"key": "value", "num": 42}
    serialized, compressed = mgr._serialize_value(data)
    assert not compressed
    restored = mgr._deserialize_value(serialized, compressed)
    assert restored == data


def test_serialize_with_compression(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_compression=True)
    large_data = {"key": "x" * 2000}
    serialized, compressed = mgr._serialize_value(large_data)
    restored = mgr._deserialize_value(serialized, compressed)
    assert restored == large_data


def test_deserialize_invalid_version(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    bad_payload = json.dumps({"version": 999, "value": "data"}).encode("utf-8")
    assert mgr._deserialize_value(bad_payload, False) is None


def test_deserialize_invalid_bytes(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    assert mgr._deserialize_value(b"not json at all", False) is None


# ============================================================
# _is_expired
# ============================================================

def test_is_expired_true(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    assert mgr._is_expired(time.time() - 100, 10) is True


def test_is_expired_false(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    assert mgr._is_expired(time.time(), 3600) is False


# ============================================================
# _generate_cache_key / _get_file_path
# ============================================================

def test_generate_cache_key_stable(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    k1 = mgr._generate_cache_key("test-key")
    k2 = mgr._generate_cache_key("test-key")
    assert k1 == k2
    assert len(k1) == 64


def test_get_file_path_creates_dirs(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    path = mgr._get_file_path("abcdef1234567890" * 4)
    assert path.parent.exists()


# ============================================================
# set / get / delete (public API) - mocking module-level Go funcs
# ============================================================

def test_set_delegates_to_set_go(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    monkeypatch.setattr("src.scrapers.cache_manager._go_cache_set", lambda *a, **kw: True)
    assert mgr.set("test-key", {"data": 1}) is True


def test_set_returns_false_on_go_exception(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)

    def _raise(*a, **kw):
        raise RuntimeError("go error")

    monkeypatch.setattr("src.scrapers.cache_manager._go_cache_set", _raise)
    assert mgr.set("test-key", {"data": 1}) is False


def test_get_returns_none_on_not_found(tmp_path, monkeypatch):
    from src.services.go_cli import GoNotFoundError

    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_memory_cache=False)

    def _raise(*a, **kw):
        raise GoNotFoundError("not found")

    monkeypatch.setattr("src.scrapers.cache_manager._go_cache_get", _raise)
    assert mgr.get("missing-key") is None


def test_get_returns_none_on_go_error(tmp_path, monkeypatch):
    from src.services.go_cli import GoError

    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_memory_cache=False)

    def _raise(*a, **kw):
        raise GoError("go error")

    monkeypatch.setattr("src.scrapers.cache_manager._go_cache_get", _raise)
    assert mgr.get("broken-key") is None


def test_delete_returns_true(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    monkeypatch.setattr("src.scrapers.cache_manager._go_cache_delete", lambda *a, **kw: True)
    assert mgr.delete("test-key") is True


def test_delete_returns_false_on_exception(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)

    def _raise(*a, **kw):
        raise RuntimeError("fail")

    monkeypatch.setattr("src.scrapers.cache_manager._go_cache_delete", _raise)
    assert mgr.delete("test-key") is False


# ============================================================
# _set_go 細節
# ============================================================

def test_set_go_too_large_returns_false(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, max_file_size_mb=0)
    monkeypatch.setattr("src.scrapers.cache_manager._go_cache_set", lambda *a, **kw: True)
    assert mgr._set_go("key", {"data": "x" * 100}) is False


def test_set_go_go_returns_false_propagates(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    monkeypatch.setattr("src.scrapers.cache_manager._go_cache_set", lambda *a, **kw: False)
    assert mgr._set_go("key", {"data": 1}) is False


def test_set_go_increments_stats(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_memory_cache=True)
    monkeypatch.setattr("src.scrapers.cache_manager._go_cache_set", lambda *a, **kw: True)
    mgr._set_go("key", {"data": "hello"})
    assert mgr.stats["sets"] == 1


# ============================================================
# _get_go 細節
# ============================================================

def test_get_go_memory_cache_hit(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_memory_cache=True)
    cache_key = mgr._generate_cache_key("hit-key")
    entry = CacheEntry(
        key=cache_key,
        value={"cached": True},
        created_at=time.time(),
        ttl_seconds=3600,
        last_accessed=time.time(),
    )
    mgr.memory_cache[cache_key] = entry
    result = mgr._get_go("hit-key")
    assert result == {"cached": True}
    assert mgr.stats["memory_hits"] == 1


def test_get_go_memory_cache_expired_evicted(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_memory_cache=True)
    cache_key = mgr._generate_cache_key("expired-key")
    entry = CacheEntry(
        key=cache_key,
        value={"cached": True},
        created_at=time.time() - 200,
        ttl_seconds=1,
        last_accessed=time.time() - 200,
    )
    mgr.memory_cache[cache_key] = entry
    monkeypatch.setattr("src.scrapers.cache_manager._go_cache_get", lambda *a, **kw: None)
    result = mgr._get_go("expired-key")
    assert result is None
    assert cache_key not in mgr.memory_cache


def test_get_go_disk_hit(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_memory_cache=False)
    payload = _make_payload({"found": True}, compressed=False)
    monkeypatch.setattr("src.scrapers.cache_manager._go_cache_get", lambda *a, **kw: payload)
    result = mgr._get_go("disk-key")
    assert result == {"found": True}
    assert mgr.stats["disk_hits"] == 1


def test_get_go_miss(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_memory_cache=False)
    monkeypatch.setattr("src.scrapers.cache_manager._go_cache_get", lambda *a, **kw: None)
    assert mgr._get_go("no-such-key") is None
    assert mgr.stats["misses"] == 1


# ============================================================
# _delete_go 細節
# ============================================================

def test_delete_go_removes_memory_cache(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_memory_cache=True)
    cache_key = mgr._generate_cache_key("del-key")
    mgr.memory_cache[cache_key] = MagicMock()
    monkeypatch.setattr("src.scrapers.cache_manager._go_cache_delete", lambda *a, **kw: True)
    result = mgr._delete_go("del-key")
    assert result is True
    assert cache_key not in mgr.memory_cache
    assert mgr.stats["deletes"] == 1


# ============================================================
# _cleanup_memory_cache (LRU)
# ============================================================

def test_cleanup_memory_cache_lru_eviction(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, max_memory_entries=2)
    t_old = time.time() - 100
    for i in range(3):
        entry = CacheEntry(key=f"key-{i}", value=i, created_at=t_old + i,
                           ttl_seconds=3600, last_accessed=t_old + i)
        mgr.memory_cache[f"key-{i}"] = entry
    mgr._cleanup_memory_cache()
    assert len(mgr.memory_cache) == 2
    assert "key-0" not in mgr.memory_cache


def test_cleanup_memory_cache_no_action_within_limit(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, max_memory_entries=10)
    entry = CacheEntry(key="k", value=1, created_at=time.time(), ttl_seconds=3600, last_accessed=time.time())
    mgr.memory_cache["k"] = entry
    mgr._cleanup_memory_cache()
    assert len(mgr.memory_cache) == 1


# ============================================================
# _delete_cache_file / _remove_index_entry
# ============================================================

def test_delete_cache_file_missing_is_safe(tmp_path, monkeypatch):
    CacheManager._delete_cache_file(str(tmp_path / "nonexistent.cache"))


def test_delete_cache_file_none_is_safe(tmp_path, monkeypatch):
    CacheManager._delete_cache_file(None)


def test_delete_cache_file_existing(tmp_path, monkeypatch):
    f = tmp_path / "to_delete.cache"
    f.write_bytes(b"data")
    CacheManager._delete_cache_file(str(f))
    assert not f.exists()


def test_remove_index_entry_present(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    index = {"entries": {"key1": {}, "key2": {}}}
    assert mgr._remove_index_entry(index, "key1") is True
    assert "key1" not in index["entries"]


def test_remove_index_entry_missing(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    assert mgr._remove_index_entry({"entries": {}}, "missing") is False


# ============================================================
# _cleanup_expired_memory_entries
# ============================================================

def test_cleanup_expired_memory_entries_removes_expired(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_memory_cache=True)
    expired = CacheEntry(key="e", value=1, created_at=time.time() - 200, ttl_seconds=1, last_accessed=0.0)
    valid = CacheEntry(key="v", value=2, created_at=time.time(), ttl_seconds=3600, last_accessed=0.0)
    mgr.memory_cache["e"] = expired
    mgr.memory_cache["v"] = valid
    removed = mgr._cleanup_expired_memory_entries()
    assert "e" in removed
    assert "e" not in mgr.memory_cache
    assert "v" in mgr.memory_cache


def test_cleanup_expired_memory_entries_disabled(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_memory_cache=False)
    assert mgr._cleanup_expired_memory_entries() == []


# ============================================================
# clear_cache
# ============================================================

def test_clear_cache_clears_memory_and_disk_files(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_memory_cache=True, enable_disk_cache=True)
    cache_key = mgr._generate_cache_key("k")
    mgr.memory_cache[cache_key] = MagicMock()
    fake_cache = tmp_path / "ab" / "cd" / "fake.cache"
    fake_cache.parent.mkdir(parents=True)
    fake_cache.write_bytes(b"data")
    mgr.clear_cache()
    assert len(mgr.memory_cache) == 0
    assert not fake_cache.exists()


# ============================================================
# get_stats
# ============================================================

def test_get_stats_basic(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_disk_cache=False)
    stats = mgr.get_stats()
    assert "hit_rate" in stats
    assert "config" in stats


def test_get_stats_calculates_hit_rate(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_disk_cache=False)
    mgr.stats["memory_hits"] = 4
    mgr.stats["disk_hits"] = 0
    mgr.stats["misses"] = 1
    stats = mgr.get_stats()
    assert "80.0%" in stats["hit_rate"]


# ============================================================
# cleanup_expired / cleanup_by_size / get_cache_stats / clear_all / auto_cleanup
# 這些方法使用 local import，需要 patch src.services.go_cli.*
# ============================================================

def test_cleanup_expired_success(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    fake = {"deleted_count": 5, "freed_bytes": 1024, "remaining_count": 10}
    with patch("src.services.go_cli.cache_prune", return_value=fake):
        result = mgr.cleanup_expired(ttl_days=7)
    assert result["deleted_files"] == 5
    assert result["freed_bytes"] == 1024
    assert result["remaining_files"] == 10


def test_cleanup_expired_raises_on_none(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    with patch("src.services.go_cli.cache_prune", return_value=None):
        with pytest.raises(RuntimeError):
            mgr.cleanup_expired()


def test_cleanup_expired_raises_on_exception(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    with patch("src.services.go_cli.cache_prune", side_effect=RuntimeError("fail")):
        with pytest.raises(RuntimeError):
            mgr.cleanup_expired()


def test_cleanup_by_size_success(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    fake = {"deleted_count": 2, "freed_bytes": 512, "remaining_count": 8, "current_size_mb": 0.5}
    with patch("src.services.go_cli.cache_prune", return_value=fake):
        result = mgr.cleanup_by_size(max_size_mb=100)
    assert result["deleted_files"] == 2
    assert result["current_size_mb"] == 0.5


def test_cleanup_by_size_raises_on_none(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    with patch("src.services.go_cli.cache_prune", return_value=None):
        with pytest.raises(RuntimeError):
            mgr.cleanup_by_size()


def test_get_cache_stats_success(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    fake = {"total_files": 10, "total_size_mb": 1.0}
    with patch("src.services.go_cli.cache_get_stats", return_value=fake):
        result = mgr.get_cache_stats()
    assert result["total_files"] == 10
    assert "memory_cache_entries" in result


def test_get_cache_stats_raises_on_none(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    with patch("src.services.go_cli.cache_get_stats", return_value=None):
        with pytest.raises(RuntimeError):
            mgr.get_cache_stats()


def test_clear_all_requires_confirm(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    assert mgr.clear_all(confirm=False) is False


def test_clear_all_success(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch, enable_memory_cache=True)
    mgr.memory_cache["k"] = MagicMock()
    with patch("src.services.go_cli.cache_clear", return_value={"ok": True}):
        result = mgr.clear_all(confirm=True)
    assert result is True
    assert len(mgr.memory_cache) == 0


def test_clear_all_raises_on_none(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    with patch("src.services.go_cli.cache_clear", return_value=None):
        with pytest.raises(RuntimeError):
            mgr.clear_all(confirm=True)


def test_auto_cleanup_success(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    fake = {"deleted_count": 3, "freed_bytes": 768}
    with patch("src.services.go_cli.cache_prune", return_value=fake):
        result = mgr.auto_cleanup()
    assert result["total_deleted"] == 3


def test_auto_cleanup_raises_on_none(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    with patch("src.services.go_cli.cache_prune", return_value=None):
        with pytest.raises(RuntimeError):
            mgr.auto_cleanup()


# ============================================================
# 非同步介面
# ============================================================

def test_set_async_delegates(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    monkeypatch.setattr(mgr, "set", lambda key, value, ttl=None: True)
    result = asyncio.run(mgr.set_async("key", "value"))
    assert result is True


def test_get_async_delegates(tmp_path, monkeypatch):
    mgr = _make_cache_manager(tmp_path, monkeypatch)
    monkeypatch.setattr(mgr, "get", lambda key: {"cached": True})
    result = asyncio.run(mgr.get_async("key"))
    assert result == {"cached": True}
