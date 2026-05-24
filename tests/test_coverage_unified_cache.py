"""補測 UnifiedCacheManager 覆蓋率。"""
import pytest

from src.services.unified_cache import (
    CacheStats,
    UnifiedCacheManager,
    cleanup_all_caches,
    get_cache_manager,
)


class FakeCacheSource:
    def __init__(
        self,
        initial=None,
        *,
        auto_cleanup_result=None,
        stats_result=None,
        raise_on=None,
    ):
        self.store = dict(initial or {})
        self.auto_cleanup_result = auto_cleanup_result
        self.stats_result = stats_result
        self.raise_on = set(raise_on or [])
        self.last_set = None
        self.last_delete = None
        self.clear_all_called = False
        self.clear_cache_called = False
        self.clear_called = False
        self.cleanup_calls = []

    def get(self, key):
        if "get" in self.raise_on:
            raise RuntimeError("get fail")
        return self.store.get(key)

    def set(self, key, value, ttl_hours=None):
        if "set" in self.raise_on:
            raise RuntimeError("set fail")
        self.last_set = {"key": key, "value": value, "ttl_hours": ttl_hours}
        self.store[key] = value

    def delete(self, key):
        if "delete" in self.raise_on:
            raise RuntimeError("delete fail")
        self.last_delete = key
        self.store.pop(key, None)

    def auto_cleanup(self, ttl_days=None, max_size_mb=None, min_keep_entries=None):
        if "auto_cleanup" in self.raise_on:
            raise RuntimeError("cleanup fail")
        self.cleanup_calls.append(
            {
                "ttl_days": ttl_days,
                "max_size_mb": max_size_mb,
                "min_keep_entries": min_keep_entries,
            }
        )
        return self.auto_cleanup_result or {"total_deleted": 0, "total_freed_mb": 0.0}

    def clear_all(self, confirm=False):
        if "clear_all" in self.raise_on:
            raise RuntimeError("clear all fail")
        self.clear_all_called = confirm
        self.store.clear()

    def clear_cache(self):
        if "clear_cache" in self.raise_on:
            raise RuntimeError("clear cache fail")
        self.clear_cache_called = True
        self.store.clear()

    def clear(self):
        if "clear" in self.raise_on:
            raise RuntimeError("clear fail")
        self.clear_called = True
        self.store.clear()

    def get_stats(self):
        if "get_stats" in self.raise_on:
            raise RuntimeError("stats fail")
        if self.stats_result is not None:
            return self.stats_result
        return {
            "memory_cache_entries": len(self.store),
            "index_entries": [],
            "total_size_mb": 0.0,
            "hit_rate": "0%",
        }

    def __len__(self):
        return len(self.store)


# ──────────────────────────────
# CacheStats dataclass
# ──────────────────────────────


def test_cache_stats_defaults():
    s = CacheStats()
    assert s.total_entries == 0
    assert s.total_size_mb == 0.0
    assert s.hit_rate == 0.0


# ──────────────────────────────
# __init__
# ──────────────────────────────


def test_init_no_config():
    mgr = UnifiedCacheManager()
    assert mgr.default_ttl_days == 7
    assert mgr.max_cache_size_mb == 500


def test_init_with_config():
    class FakeConfig:
        def getint(self, section, key, fallback=None):
            if key == "ttl_days":
                return 14
            if key == "max_size_mb":
                return 200
            return fallback

    mgr = UnifiedCacheManager(config=FakeConfig())
    assert mgr.default_ttl_days == 14
    assert mgr.max_cache_size_mb == 200


def test_init_config_exception_uses_defaults():
    class BadConfig:
        def getint(self, section, key, fallback=None):
            raise ValueError("bad config")

    mgr = UnifiedCacheManager(config=BadConfig())
    assert mgr.default_ttl_days == 7


# ──────────────────────────────
# register / unregister
# ──────────────────────────────


def test_register_and_unregister():
    mgr = UnifiedCacheManager()
    cache = {}
    mgr.register_cache_source("test", cache)
    assert "test" in mgr._cache_sources
    mgr.unregister_cache_source("test")
    assert "test" not in mgr._cache_sources


def test_unregister_nonexistent_is_noop():
    mgr = UnifiedCacheManager()
    mgr.unregister_cache_source("nope")  # should not raise


# ──────────────────────────────
# get
# ──────────────────────────────


def test_get_from_specific_source():
    mgr = UnifiedCacheManager()
    cache = FakeCacheSource({"key1": "hit"})
    mgr.register_cache_source("main", cache)
    result = mgr.get("key1", source="main")
    assert result == "hit"


def test_get_from_specific_source_not_found():
    mgr = UnifiedCacheManager()
    result = mgr.get("key1", source="nonexistent")
    assert result is None


def test_get_from_specific_source_no_get_method():
    mgr = UnifiedCacheManager()
    mgr.register_cache_source("main", object())
    result = mgr.get("key1", source="main")
    assert result is None


def test_get_searches_all_sources():
    mgr = UnifiedCacheManager()
    cache1 = FakeCacheSource()
    cache2 = FakeCacheSource({"key1": "found"})
    mgr.register_cache_source("c1", cache1)
    mgr.register_cache_source("c2", cache2)
    result = mgr.get("key1")
    assert result == "found"


def test_get_returns_none_when_all_miss():
    mgr = UnifiedCacheManager()
    cache = FakeCacheSource()
    mgr.register_cache_source("main", cache)
    result = mgr.get("missing")
    assert result is None


def test_get_skips_sources_without_get():
    mgr = UnifiedCacheManager()
    mgr.register_cache_source("noget", object())
    # Should return None, not raise
    assert mgr.get("key") is None


# ──────────────────────────────
# set
# ──────────────────────────────


def test_set_to_specific_source():
    mgr = UnifiedCacheManager()
    cache = FakeCacheSource()
    mgr.register_cache_source("main", cache)
    mgr.set("key", "value", source="main", ttl_hours=2)
    assert cache.last_set == {"key": "key", "value": "value", "ttl_hours": 2}


def test_set_specific_source_not_found():
    mgr = UnifiedCacheManager()
    # No sources registered, should not raise
    mgr.set("key", "value", source="nope")


def test_set_to_first_available_source():
    mgr = UnifiedCacheManager()
    cache = FakeCacheSource()
    mgr.register_cache_source("main", cache)
    mgr.set("key", "value")
    assert cache.store["key"] == "value"


def test_set_uses_default_ttl_when_none():
    mgr = UnifiedCacheManager()
    cache = FakeCacheSource()
    mgr.register_cache_source("main", cache)
    mgr.set("key", "value")
    assert cache.last_set["ttl_hours"] == 7 * 24


def test_set_skips_no_set_method():
    mgr = UnifiedCacheManager()
    mgr.register_cache_source("noset", object())
    # Should not raise
    mgr.set("key", "value")


# ──────────────────────────────
# delete
# ──────────────────────────────


def test_delete_from_specific_source():
    mgr = UnifiedCacheManager()
    cache = FakeCacheSource({"key": "value"})
    mgr.register_cache_source("main", cache)
    mgr.delete("key", source="main")
    assert cache.last_delete == "key"
    assert "key" not in cache.store


def test_delete_from_specific_source_not_found():
    mgr = UnifiedCacheManager()
    mgr.delete("key", source="nope")  # should not raise


def test_delete_from_all_sources():
    mgr = UnifiedCacheManager()
    c1 = FakeCacheSource({"key": "value1"})
    c2 = FakeCacheSource({"key": "value2"})
    mgr.register_cache_source("c1", c1)
    mgr.register_cache_source("c2", c2)
    mgr.delete("key")
    assert c1.last_delete == "key"
    assert c2.last_delete == "key"


def test_delete_skips_no_delete_method():
    mgr = UnifiedCacheManager()
    mgr.register_cache_source("nodlt", object())
    mgr.delete("key")  # should not raise


# ──────────────────────────────
# cleanup_all
# ──────────────────────────────


def test_cleanup_all_no_sources():
    mgr = UnifiedCacheManager()
    result = mgr.cleanup_all()
    assert result["sources_cleaned"] == 0
    assert result["total_deleted"] == 0


def test_cleanup_all_with_auto_cleanup():
    mgr = UnifiedCacheManager()
    cache = FakeCacheSource(auto_cleanup_result={"total_deleted": 5, "total_freed_mb": 1.5})
    mgr.register_cache_source("main", cache)
    result = mgr.cleanup_all(ttl_days=3, max_size_mb=100)
    assert result["total_deleted"] == 5
    assert result["total_freed_mb"] == 1.5
    assert cache.cleanup_calls[-1] == {
        "ttl_days": 3,
        "max_size_mb": 100,
        "min_keep_entries": mgr.min_keep_entries,
    }


def test_cleanup_all_exception_is_captured():
    mgr = UnifiedCacheManager()
    cache = FakeCacheSource(raise_on={"auto_cleanup"})
    mgr.register_cache_source("bad", cache)
    result = mgr.cleanup_all()
    assert "error" in result["details"]["bad"]


# ──────────────────────────────
# _cleanup_single_source
# ──────────────────────────────


def test_cleanup_single_auto_cleanup():
    mgr = UnifiedCacheManager()
    cache = FakeCacheSource(auto_cleanup_result={"total_deleted": 3, "total_freed_mb": 0.5})
    r = mgr._cleanup_single_source("name", cache, 7, 500)
    assert r["deleted"] == 3
    assert cache.cleanup_calls[-1]["ttl_days"] == 7


def test_cleanup_single_clear_with_len():
    mgr = UnifiedCacheManager()
    class ClearableLenCache:
        def __init__(self):
            self.store = {"a": 1, "b": 2, "c": 3}
            self.clear_called = False

        def __len__(self):
            return len(self.store)

        def clear(self):
            self.clear_called = True
            self.store.clear()

    cache = ClearableLenCache()
    r = mgr._cleanup_single_source("name", cache, 7, 500)
    assert r["deleted"] == 3
    assert cache.clear_called is True


def test_cleanup_single_clear_no_len():
    mgr = UnifiedCacheManager()

    class OnlyClear:
        def clear(self):
            pass

    r = mgr._cleanup_single_source("name", OnlyClear(), 7, 500)
    assert r["deleted"] == 0


def test_cleanup_single_dict():
    mgr = UnifiedCacheManager()
    d = {"a": 1, "b": 2}
    r = mgr._cleanup_single_source("name", d, 7, 500)
    assert r["deleted"] == 2
    assert d == {}


def test_cleanup_single_no_method():
    mgr = UnifiedCacheManager()
    r = mgr._cleanup_single_source("name", object(), 7, 500)
    assert r["deleted"] == 0


# ──────────────────────────────
# clear_all
# ──────────────────────────────


def test_clear_all_requires_confirm():
    mgr = UnifiedCacheManager()
    assert mgr.clear_all(confirm=False) is False


def test_clear_all_calls_clear_all_on_cache():
    mgr = UnifiedCacheManager()
    cache = FakeCacheSource({"a": 1})
    mgr.register_cache_source("main", cache)
    mgr.clear_all(confirm=True)
    assert cache.clear_all_called is True


def test_clear_all_falls_back_to_clear_cache():
    mgr = UnifiedCacheManager()

    class HasClearCache:
        def clear_cache(self):
            self.cleared = True

    c = HasClearCache()
    mgr.register_cache_source("main", c)
    mgr.clear_all(confirm=True)
    assert c.cleared is True


def test_clear_all_falls_back_to_clear():
    mgr = UnifiedCacheManager()
    d = {"a": 1}
    mgr.register_cache_source("dict", d)
    mgr.clear_all(confirm=True)
    assert d == {}


def test_clear_all_exception_is_swallowed():
    mgr = UnifiedCacheManager()
    cache = FakeCacheSource({"a": 1}, raise_on={"clear_all"})
    mgr.register_cache_source("bad", cache)
    # Should not raise
    assert mgr.clear_all(confirm=True) is True


# ──────────────────────────────
# get_stats
# ──────────────────────────────


def test_get_stats_no_sources():
    mgr = UnifiedCacheManager()
    stats = mgr.get_stats()
    assert stats["total_sources"] == 0
    assert stats["summary"]["total_entries"] == 0


def test_get_stats_with_cache_manager_source():
    mgr = UnifiedCacheManager()
    cache = FakeCacheSource(
        stats_result={
            "memory_cache_entries": 5,
            "index_entries": ["a", "b"],
            "total_size_mb": 1.2,
            "hit_rate": "80%",
        }
    )
    mgr.register_cache_source("main", cache)
    stats = mgr.get_stats()
    assert stats["sources"]["main"]["memory_entries"] == 5
    assert stats["sources"]["main"]["disk_entries"] == 2


def test_get_stats_with_dict_source():
    mgr = UnifiedCacheManager()
    mgr.register_cache_source("dict", {"k1": 1, "k2": 2})
    stats = mgr.get_stats()
    assert stats["sources"]["dict"]["entries"] == 2


def test_get_stats_with_len_source():
    mgr = UnifiedCacheManager()

    class HasLen:
        def __len__(self):
            return 7

    mgr.register_cache_source("lenobj", HasLen())
    stats = mgr.get_stats()
    assert stats["sources"]["lenobj"]["entries"] == 7


def test_get_stats_source_exception():
    mgr = UnifiedCacheManager()
    cache = FakeCacheSource(raise_on={"get_stats"})
    mgr.register_cache_source("bad", cache)
    stats = mgr.get_stats()
    assert "error" in stats["sources"]["bad"]


def test_get_stats_index_entries_non_list():
    """index_entries 非 list 時，len() 拋出 TypeError，被 get_stats 捕獲後回傳 error。"""
    mgr = UnifiedCacheManager()
    cache = FakeCacheSource(
        stats_result={
            "memory_cache_entries": 2,
            "index_entries": 5,  # not a list → len(5) raises TypeError
            "total_size_mb": 0.0,
            "hit_rate": "0%",
        }
    )
    mgr.register_cache_source("main", cache)
    stats = mgr.get_stats()
    # TypeError is caught, so source shows error dict
    assert "error" in stats["sources"]["main"]


# ──────────────────────────────
# print_stats
# ──────────────────────────────


def test_print_stats_runs_without_error(capsys):
    mgr = UnifiedCacheManager()
    mgr.register_cache_source("dict", {"a": 1})
    mgr.print_stats()
    captured = capsys.readouterr()
    assert "快取統計報告" in captured.out


def test_print_stats_shows_error_source(capsys):
    mgr = UnifiedCacheManager()
    cache = FakeCacheSource(raise_on={"get_stats"})
    mgr.register_cache_source("bad", cache)
    mgr.print_stats()
    captured = capsys.readouterr()
    assert "錯誤" in captured.out


# ──────────────────────────────
# get_cache_manager (singleton)
# ──────────────────────────────


def test_get_cache_manager_returns_singleton():
    import src.services.unified_cache as uc
    # Reset singleton
    uc._global_cache_manager = None

    m1 = get_cache_manager()
    m2 = get_cache_manager()
    assert m1 is m2

    # Cleanup
    uc._global_cache_manager = None


def test_get_cache_manager_with_config():
    import src.services.unified_cache as uc
    uc._global_cache_manager = None

    class FakeConfig:
        def getint(self, s, k, fallback=None):
            return 14 if k == "ttl_days" else fallback

    m = get_cache_manager(config=FakeConfig())
    assert m.default_ttl_days == 14

    uc._global_cache_manager = None


# ──────────────────────────────
# cleanup_all_caches
# ──────────────────────────────


def test_cleanup_all_caches_delegates(monkeypatch):
    import src.services.unified_cache as uc
    uc._global_cache_manager = None
    called_with = {}


    def fake_cleanup(self, ttl_days=None, max_size_mb=None):
        called_with["ttl"] = ttl_days
        called_with["size"] = max_size_mb
        return {}

    monkeypatch.setattr(UnifiedCacheManager, "cleanup_all", fake_cleanup)
    cleanup_all_caches(ttl_days=3, max_size_mb=100)
    assert called_with["ttl"] == 3
    assert called_with["size"] == 100

    uc._global_cache_manager = None
