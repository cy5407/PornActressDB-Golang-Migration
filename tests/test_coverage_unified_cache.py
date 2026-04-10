"""補測 UnifiedCacheManager 覆蓋率。"""
import pytest
from unittest.mock import MagicMock
from src.services.unified_cache import (
    CacheStats,
    UnifiedCacheManager,
    get_cache_manager,
    cleanup_all_caches,
)


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
    cache = MagicMock()
    cache.get.return_value = "hit"
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
    cache1 = MagicMock()
    cache1.get.return_value = None
    cache2 = MagicMock()
    cache2.get.return_value = "found"
    mgr.register_cache_source("c1", cache1)
    mgr.register_cache_source("c2", cache2)
    result = mgr.get("key1")
    assert result == "found"


def test_get_returns_none_when_all_miss():
    mgr = UnifiedCacheManager()
    cache = MagicMock()
    cache.get.return_value = None
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
    cache = MagicMock()
    mgr.register_cache_source("main", cache)
    mgr.set("key", "value", source="main", ttl_hours=2)
    cache.set.assert_called_once_with("key", "value", ttl_hours=2)


def test_set_specific_source_not_found():
    mgr = UnifiedCacheManager()
    # No sources registered, should not raise
    mgr.set("key", "value", source="nope")


def test_set_to_first_available_source():
    mgr = UnifiedCacheManager()
    cache = MagicMock()
    mgr.register_cache_source("main", cache)
    mgr.set("key", "value")
    assert cache.set.called


def test_set_uses_default_ttl_when_none():
    mgr = UnifiedCacheManager()
    cache = MagicMock()
    mgr.register_cache_source("main", cache)
    mgr.set("key", "value")
    # ttl_hours should be default_ttl_days * 24 = 168
    call_kwargs = cache.set.call_args[1]
    assert call_kwargs["ttl_hours"] == 7 * 24


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
    cache = MagicMock()
    mgr.register_cache_source("main", cache)
    mgr.delete("key", source="main")
    cache.delete.assert_called_once_with("key")


def test_delete_from_specific_source_not_found():
    mgr = UnifiedCacheManager()
    mgr.delete("key", source="nope")  # should not raise


def test_delete_from_all_sources():
    mgr = UnifiedCacheManager()
    c1 = MagicMock()
    c2 = MagicMock()
    mgr.register_cache_source("c1", c1)
    mgr.register_cache_source("c2", c2)
    mgr.delete("key")
    c1.delete.assert_called_once_with("key")
    c2.delete.assert_called_once_with("key")


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
    cache = MagicMock()
    cache.auto_cleanup.return_value = {"total_deleted": 5, "total_freed_mb": 1.5}
    mgr.register_cache_source("main", cache)
    result = mgr.cleanup_all(ttl_days=3, max_size_mb=100)
    assert result["total_deleted"] == 5
    assert result["total_freed_mb"] == 1.5


def test_cleanup_all_exception_is_captured():
    mgr = UnifiedCacheManager()
    cache = MagicMock()
    cache.auto_cleanup.side_effect = RuntimeError("oops")
    mgr.register_cache_source("bad", cache)
    result = mgr.cleanup_all()
    assert "error" in result["details"]["bad"]


# ──────────────────────────────
# _cleanup_single_source
# ──────────────────────────────


def test_cleanup_single_auto_cleanup():
    mgr = UnifiedCacheManager()
    cache = MagicMock()
    cache.auto_cleanup.return_value = {"total_deleted": 3, "total_freed_mb": 0.5}
    r = mgr._cleanup_single_source("name", cache, 7, 500)
    assert r["deleted"] == 3


def test_cleanup_single_clear_with_len():
    mgr = UnifiedCacheManager()
    cache = MagicMock(spec=["clear", "__len__"])
    cache.__len__ = MagicMock(return_value=10)
    r = mgr._cleanup_single_source("name", cache, 7, 500)
    assert r["deleted"] == 10
    cache.clear.assert_called_once()


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
    cache = MagicMock()
    mgr.register_cache_source("main", cache)
    mgr.clear_all(confirm=True)
    cache.clear_all.assert_called_once_with(confirm=True)


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
    cache = MagicMock()
    cache.clear_all.side_effect = RuntimeError("bad")
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
    cache = MagicMock()
    cache.get_stats.return_value = {
        "memory_cache_entries": 5,
        "index_entries": ["a", "b"],
        "total_size_mb": 1.2,
        "hit_rate": "80%",
    }
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
    cache = MagicMock()
    cache.get_stats.side_effect = RuntimeError("oops")
    mgr.register_cache_source("bad", cache)
    stats = mgr.get_stats()
    assert "error" in stats["sources"]["bad"]


def test_get_stats_index_entries_non_list():
    """index_entries 非 list 時，len() 拋出 TypeError，被 get_stats 捕獲後回傳 error。"""
    mgr = UnifiedCacheManager()
    cache = MagicMock()
    cache.get_stats.return_value = {
        "memory_cache_entries": 2,
        "index_entries": 5,  # not a list → len(5) raises TypeError
        "total_size_mb": 0.0,
        "hit_rate": "0%",
    }
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
    cache = MagicMock()
    cache.get_stats.side_effect = RuntimeError("crash")
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

    original_cleanup = UnifiedCacheManager.cleanup_all

    def fake_cleanup(self, ttl_days=None, max_size_mb=None):
        called_with["ttl"] = ttl_days
        called_with["size"] = max_size_mb
        return {}

    monkeypatch.setattr(UnifiedCacheManager, "cleanup_all", fake_cleanup)
    cleanup_all_caches(ttl_days=3, max_size_mb=100)
    assert called_with["ttl"] == 3
    assert called_with["size"] == 100

    uc._global_cache_manager = None
