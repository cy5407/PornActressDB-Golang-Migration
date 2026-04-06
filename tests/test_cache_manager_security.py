"""
測試 CacheManager 的安全磁碟快取行為
"""

import gzip
import json
import pickle
from pathlib import Path

from src.scrapers.cache_manager import CacheConfig, CacheManager


def test_disk_cache_uses_json_payload(tmp_path, monkeypatch):
    """磁碟快取應使用 JSON 載荷而非 pickle。"""
    manager = CacheManager(
        CacheConfig(
            cache_dir=str(tmp_path),
            enable_memory_cache=False,
            enable_compression=False,
        )
    )
    # 強制走 Python 路徑，確保測試 Python 安全實作而非 Go 儲存路徑
    monkeypatch.setattr(manager, "_GO_CACHE_AVAILABLE", False)

    value = {"name": "測試", "actresses": ["A", "B"], "count": 2}

    assert manager.set("video:test", value)

    cache_key = manager._generate_cache_key("video:test")
    cache_path = manager._get_file_path(cache_key)
    payload = json.loads(cache_path.read_text(encoding="utf-8"))

    assert payload["version"] == 1
    assert payload["value"] == value
    assert manager.get("video:test") == value


def test_legacy_pickle_cache_is_ignored_and_removed(tmp_path, monkeypatch):
    """舊版 pickle 快取檔應被忽略並刪除，避免反序列化不受信任資料。"""
    manager = CacheManager(
        CacheConfig(
            cache_dir=str(tmp_path),
            enable_memory_cache=False,
            enable_compression=False,
        )
    )
    # 強制走 Python 路徑，確保測試 Python 安全實作
    monkeypatch.setattr(manager, "_GO_CACHE_AVAILABLE", False)

    cache_key = manager._generate_cache_key("legacy:test")
    cache_path = manager._get_file_path(cache_key)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(pickle.dumps({"unsafe": True}))

    index_data = manager._load_index()
    index_data["entries"][cache_key] = {
        "file_path": str(cache_path),
        "created_at": 0,
        "ttl_seconds": 10**9,
        "last_accessed": 0,
        "access_count": 0,
        "compressed": False,
        "size_bytes": cache_path.stat().st_size,
    }
    manager._save_index(index_data)

    assert manager.get("legacy:test") is None
    assert not cache_path.exists()
    assert cache_key not in manager._load_index()["entries"]


def test_compressed_json_cache_roundtrip(tmp_path, monkeypatch):
    """壓縮後的 JSON 快取仍應可正確讀回。"""
    manager = CacheManager(
        CacheConfig(
            cache_dir=str(tmp_path),
            enable_memory_cache=False,
            enable_compression=True,
        )
    )
    # 強制走 Python 路徑，確保測試 Python 安全實作
    monkeypatch.setattr(manager, "_GO_CACHE_AVAILABLE", False)

    value = {"text": "x" * 5000}

    assert manager.set("compressed:test", value)

    cache_key = manager._generate_cache_key("compressed:test")
    cache_path = manager._get_file_path(cache_key)
    data = cache_path.read_bytes()
    decoded = gzip.decompress(data).decode("utf-8")
    payload = json.loads(decoded)

    assert payload["value"] == value
    assert manager.get("compressed:test") == value
