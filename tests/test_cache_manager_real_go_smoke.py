import src.scrapers.cache_manager as cache_manager_module
from src.scrapers.cache_manager import CacheConfig, CacheManager
from src.services import go_cli


def _manager(tmp_path, monkeypatch, **overrides):
    monkeypatch.setattr(CacheManager, "_start_cleanup_task", lambda self: None)
    cfg = CacheConfig(cache_dir=str(tmp_path), **overrides)
    return CacheManager(cfg)


def test_cache_manager_public_api_uses_real_go_cli(tmp_path, monkeypatch):
    mgr = _manager(tmp_path, monkeypatch, enable_memory_cache=False)
    cache_manager_module._go_cache_set = go_cli.cache_set
    cache_manager_module._go_cache_get = go_cli.cache_get
    cache_manager_module._go_cache_delete = go_cli.cache_delete

    assert mgr.set("smoke-key", {"message": "真實快取"}, ttl_hours=1) is True
    assert mgr.get("smoke-key") == {"message": "真實快取"}
    assert mgr.delete("smoke-key") is True
    assert mgr.get("smoke-key") is None


def test_cache_manager_get_stats_tracks_real_go_cache_entries(tmp_path, monkeypatch):
    mgr = _manager(tmp_path, monkeypatch, enable_memory_cache=False)
    cache_manager_module._go_cache_set = go_cli.cache_set
    cache_manager_module._go_cache_get = go_cli.cache_get
    cache_manager_module._go_cache_delete = go_cli.cache_delete

    assert mgr.set("stats-key", [1, 2, 3], ttl_hours=1) is True
    stats = mgr.get_stats()

    assert isinstance(stats, dict)
    assert stats["config"]["cache_dir"] == str(tmp_path)
    assert stats["sets"] >= 1
    assert stats["total_size_mb"] >= 0
