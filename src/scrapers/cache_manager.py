"""
智慧快取管理模組
提供高效的多層級快取機制
"""

import asyncio
import builtins
import contextlib
import gzip
import hashlib
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from src.services.go_cli import (
    GoError as _GoBridgeError,
    GoNotFoundError as _GoBridgeNotFoundError,
    cache_delete as _go_cache_delete,
    cache_get as _go_cache_get,
    cache_set as _go_cache_set,
)
from src.utils.json_utils import dump as json_dump
from src.utils.json_utils import load as json_load

logger = logging.getLogger(__name__)

CACHE_PAYLOAD_VERSION = 1


@dataclass
class CacheConfig:
    """快取配置類"""

    cache_dir: str = "cache"  # 快取目錄
    index_file: str = "cache_index.json"  # JSON索引檔案
    default_ttl_hours: int = 24  # 預設TTL(小時)
    max_memory_entries: int = 1000  # 記憶體快取最大條目數
    enable_compression: bool = True  # 啟用壓縮
    enable_memory_cache: bool = True  # 啟用記憶體快取
    enable_disk_cache: bool = True  # 啟用磁碟快取
    cleanup_interval_hours: int = 6  # 清理間隔(小時)
    max_file_size_mb: int = 10  # 單檔最大大小(MB)


@dataclass
class CacheEntry:
    """快取條目"""

    key: str
    value: Any
    created_at: float
    ttl_seconds: int
    access_count: int = 0
    last_accessed: float = 0.0
    compressed: bool = False
    size_bytes: int = 0


class CacheManager:
    """多層級智慧快取管理器"""

    def __init__(self, config: CacheConfig = None):
        self.config = config or CacheConfig()
        self.cache_dir = Path(self.config.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 記憶體快取
        self.memory_cache: dict[str, CacheEntry] = {}
        self.memory_lock = threading.RLock()

        # JSON 索引檔案
        self.index_path = self.cache_dir / self.config.index_file
        self.index_lock = threading.RLock()
        self._init_index()

        # 統計資訊
        self.stats = {
            "memory_hits": 0,
            "disk_hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "cleanups": 0,
            "total_size_mb": 0.0,
        }

        # 啟動背景清理任務
        self._start_cleanup_task()

        logger.info(f"💾 快取管理器已初始化 - 目錄: {self.cache_dir}")

    def _init_index(self):
        """初始化 JSON 索引檔案"""
        try:
            if not self.index_path.exists():
                # 建立空索引
                initial_index = {
                    "_metadata": {"version": "1.0", "created_at": time.time()},
                    "entries": {},
                }
                with open(self.index_path, "w", encoding="utf-8") as f:
                    json_dump(initial_index, f, indent=2, ensure_ascii=False)
                logger.debug("📊 快取索引檔案已建立")
            else:
                # 驗證現有索引
                with open(self.index_path, encoding="utf-8") as f:
                    index_data = json_load(f)
                    if "entries" not in index_data:
                        # 修復損壞的索引
                        index_data["entries"] = {}
                        with open(self.index_path, "w", encoding="utf-8") as f_write:
                            json_dump(index_data, f_write, indent=2, ensure_ascii=False)
                        logger.warning("📊 快取索引已修復")
                    else:
                        logger.debug("📊 快取索引已載入")

        except Exception as e:
            logger.error(f"初始化快取索引失敗: {e}")
            # 建立新索引
            try:
                initial_index = {
                    "_metadata": {"version": "1.0", "created_at": time.time()},
                    "entries": {},
                }
                with open(self.index_path, "w", encoding="utf-8") as f:
                    json_dump(initial_index, f, indent=2, ensure_ascii=False)
            except Exception as fallback_error:
                logger.error(f"建立備援索引失敗: {fallback_error}")

    def _load_index(self) -> dict:
        """載入 JSON 索引"""
        try:
            with self.index_lock, open(self.index_path, encoding="utf-8") as f:
                return json_load(f)
        except Exception as e:
            logger.error(f"載入索引失敗: {e}")
            return {
                "_metadata": {"version": "1.0", "created_at": time.time()},
                "entries": {},
            }

    def _save_index(self, index_data: dict) -> bool:
        """儲存 JSON 索引"""
        try:
            with self.index_lock, open(self.index_path, "w", encoding="utf-8") as f:
                json_dump(index_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"儲存索引失敗: {e}")
            return False

    def _generate_cache_key(self, key: str) -> str:
        """生成快取鍵值"""
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _get_file_path(self, cache_key: str) -> Path:
        """獲取快取檔案路徑"""
        # 使用兩層目錄結構避免單目錄檔案過多
        dir1 = cache_key[:2]
        dir2 = cache_key[2:4]
        cache_file_dir = self.cache_dir / dir1 / dir2
        cache_file_dir.mkdir(parents=True, exist_ok=True)
        return cache_file_dir / f"{cache_key}.cache"

    def _serialize_value(self, value: Any) -> tuple[bytes, bool]:
        """以 JSON 序列化值並選擇性壓縮。"""
        try:
            payload = {"version": CACHE_PAYLOAD_VERSION, "value": value}
            serialized = json.dumps(payload, ensure_ascii=False).encode("utf-8")

            # 決定是否壓縮
            should_compress = (
                self.config.enable_compression
                and len(serialized) > 1024  # 超過1KB才壓縮
            )

            if should_compress:
                compressed_data = gzip.compress(serialized)
                # 只有在壓縮有效果時才使用
                if len(compressed_data) < len(serialized) * 0.9:
                    return compressed_data, True

            return serialized, False

        except Exception as e:
            logger.error(f"序列化值失敗: {e}")
            return b"", False

    def _deserialize_value(self, data: bytes, compressed: bool) -> Any:
        """僅接受 JSON 格式的快取資料，避免反序列化不受信任位元組。"""
        try:
            if compressed:
                data = gzip.decompress(data)
            payload = json.loads(data.decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != CACHE_PAYLOAD_VERSION:
                raise ValueError("不支援的快取格式版本")
            return payload.get("value")
        except (UnicodeDecodeError, JSONDecodeError, ValueError) as e:
            logger.warning(f"⚠️ 偵測到無效或舊版快取資料，將忽略該條目: {e}")
            return None
        except Exception as e:
            logger.error(f"反序列化值失敗: {e}")
            return None

    def _is_expired(self, created_at: float, ttl_seconds: int) -> bool:
        """檢查是否過期"""
        return time.time() - created_at > ttl_seconds

    def set(self, key: str, value: Any, ttl_hours: int | None = None) -> bool:
        """設置快取值。Go 失敗時回傳 False。"""
        try:
            return self._set_go(key, value, ttl_hours)
        except Exception as e:
            logger.warning(f"⚠️ Go 快取寫入失敗: {e}")
            return False

    def get(self, key: str) -> Any | None:
        """獲取快取值。Go 失敗時回傳 None。"""
        try:
            return self._get_go(key)
        except _GoBridgeNotFoundError:
            return None
        except _GoBridgeError as e:
            logger.warning(f"⚠️ Go 快取讀取失敗: {e}")
            return None

    def delete(self, key: str) -> bool:
        """刪除快取條目。Go 失敗時回傳 False。"""
        try:
            return self._delete_go(key)
        except Exception as e:
            logger.warning(f"⚠️ Go 快取刪除失敗: {e}")
            return False

    # ------------------------------------------------------------------
    # Go 加速路徑
    # ------------------------------------------------------------------

    def _set_go(self, key: str, value: Any, ttl_hours: int | None = None) -> bool:
        """使用 Go CLI 寫入快取（含記憶體快取更新）。"""
        ttl_effective = ttl_hours or self.config.default_ttl_hours
        ttl_seconds = ttl_effective * 3600
        cache_key = self._generate_cache_key(key)
        current_time = time.time()

        serialized, compressed = self._serialize_value(value)
        if not serialized:
            return False

        # 第一位元組編碼壓縮旗標，以便讀回時還原
        flag = b'\x01' if compressed else b'\x00'
        payload = flag + serialized

        max_size_bytes = self.config.max_file_size_mb * 1024 * 1024
        if len(payload) > max_size_bytes:
            logger.warning(f"快取值過大 ({len(payload) / 1024 / 1024:.1f}MB)，跳過快取")
            return False

        ok = _go_cache_set(key, payload, ttl_effective, cache_dir=str(self.cache_dir))
        if not ok:
            return False

        if self.config.enable_memory_cache:
            entry = CacheEntry(
                key=cache_key,
                value=value,
                created_at=current_time,
                ttl_seconds=ttl_seconds,
                last_accessed=current_time,
                compressed=compressed,
                size_bytes=len(serialized),
            )
            with self.memory_lock:
                self.memory_cache[cache_key] = entry
                self._cleanup_memory_cache()

        self.stats["sets"] += 1
        logger.debug(f"💾 Go 快取已寫入: {key} ({len(serialized)} bytes)")
        return True

    def _get_go(self, key: str) -> Any | None:
        """從 Go CLI 讀取快取（優先查記憶體，再查 Go 磁碟）。"""
        cache_key = self._generate_cache_key(key)
        current_time = time.time()

        # 先查記憶體快取
        if self.config.enable_memory_cache:
            with self.memory_lock:
                if cache_key in self.memory_cache:
                    entry = self.memory_cache[cache_key]
                    if not self._is_expired(entry.created_at, entry.ttl_seconds):
                        entry.access_count += 1
                        entry.last_accessed = current_time
                        self.stats["memory_hits"] += 1
                        logger.debug(f"📋 記憶體快取命中: {key}")
                        return entry.value
                    else:
                        del self.memory_cache[cache_key]

        # 查 Go 磁碟快取
        payload = _go_cache_get(key, cache_dir=str(self.cache_dir))
        if payload is None or len(payload) < 1:
            self.stats["misses"] += 1
            logger.debug(f"❌ Go 快取未命中: {key}")
            return None

        compressed = payload[0] == 1
        value = self._deserialize_value(payload[1:], compressed)
        if value is None:
            self.stats["misses"] += 1
            return None

        if self.config.enable_memory_cache:
            entry = CacheEntry(
                key=cache_key,
                value=value,
                created_at=current_time,
                ttl_seconds=self.config.default_ttl_hours * 3600,
                access_count=1,
                last_accessed=current_time,
                compressed=compressed,
                size_bytes=len(payload) - 1,
            )
            with self.memory_lock:
                self.memory_cache[cache_key] = entry

        self.stats["disk_hits"] += 1
        logger.debug(f"🚀 Go 快取命中: {key}")
        return value

    def _delete_go(self, key: str) -> bool:
        """使用 Go CLI 刪除快取（同時清除記憶體快取）。"""
        cache_key = self._generate_cache_key(key)

        if self.config.enable_memory_cache:
            with self.memory_lock:
                self.memory_cache.pop(cache_key, None)

        ok = _go_cache_delete(key, cache_dir=str(self.cache_dir))
        if ok:
            self.stats["deletes"] += 1
            logger.debug(f"🗑️ Go 快取已刪除: {key}")
        return ok

    def _delete_cache_entry(self, cache_key: str, file_path: str):
        """刪除快取條目（檔案和索引）"""
        try:
            # 刪除檔案
            file_path_obj = Path(file_path)
            if file_path_obj.exists():
                file_path_obj.unlink()

            # 從 JSON 索引移除
            index_data = self._load_index()
            if cache_key in index_data.get("entries", {}):
                del index_data["entries"][cache_key]
                self._save_index(index_data)

        except Exception as e:
            logger.error(f"刪除快取條目失敗: {e}")

    def _cleanup_memory_cache(self):
        """清理記憶體快取（LRU策略）"""
        if len(self.memory_cache) <= self.config.max_memory_entries:
            return

        # 按最後訪問時間排序，移除最舊的條目
        sorted_entries = sorted(
            self.memory_cache.items(), key=lambda x: x[1].last_accessed
        )

        # 移除超出限制的條目
        remove_count = len(self.memory_cache) - self.config.max_memory_entries
        for i in range(remove_count):
            cache_key, _ = sorted_entries[i]
            del self.memory_cache[cache_key]

        logger.debug(f"🧹 記憶體快取清理: 移除 {remove_count} 個條目")

    def _cleanup_expired_cache(self):
        """清理過期快取"""
        try:
            time.time()

            # 清理記憶體快取
            if self.config.enable_memory_cache:
                with self.memory_lock:
                    expired_keys = [
                        key
                        for key, entry in self.memory_cache.items()
                        if self._is_expired(entry.created_at, entry.ttl_seconds)
                    ]

                    for key in expired_keys:
                        del self.memory_cache[key]

                    if expired_keys:
                        logger.info(
                            f"🧹 記憶體快取清理: {len(expired_keys)} 個過期條目"
                        )

            # 清理磁碟快取
            if self.config.enable_disk_cache:
                index_data = self._load_index()
                expired_entries = []

                # 查找過期條目
                for cache_key, entry_data in list(
                    index_data.get("entries", {}).items()
                ):
                    created_at = entry_data.get("created_at", 0)
                    ttl_seconds = entry_data.get("ttl_seconds", 0)

                    if self._is_expired(created_at, ttl_seconds):
                        expired_entries.append((cache_key, entry_data.get("file_path")))

                # 刪除過期條目
                for cache_key, file_path in expired_entries:
                    self._delete_cache_entry(cache_key, file_path)

                if expired_entries:
                    logger.info(f"🧹 磁碟快取清理: {len(expired_entries)} 個過期條目")

            self.stats["cleanups"] += 1

        except Exception as e:
            logger.error(f"清理過期快取失敗: {e}")

    def _start_cleanup_task(self):
        """啟動背景清理任務"""

        def cleanup_worker():
            while True:
                try:
                    time.sleep(self.config.cleanup_interval_hours * 3600)
                    self._cleanup_expired_cache()
                except Exception as e:
                    logger.error(f"背景清理任務失敗: {e}")

        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        logger.info(
            f"🧹 背景清理任務已啟動 (間隔: {self.config.cleanup_interval_hours}小時)"
        )

    def clear_cache(self):
        """清空所有快取"""
        try:
            # 清空記憶體快取
            if self.config.enable_memory_cache:
                with self.memory_lock:
                    self.memory_cache.clear()

            # 清空磁碟快取
            if self.config.enable_disk_cache:
                # 刪除所有快取檔案
                for cache_file in self.cache_dir.rglob("*.cache"):
                    with contextlib.suppress(builtins.BaseException):
                        cache_file.unlink()

                # 清空 JSON 索引
                index_data = {
                    "_metadata": {"version": "1.0", "created_at": time.time()},
                    "entries": {},
                }
                self._save_index(index_data)

            logger.info("🧹 已清空所有快取")

        except Exception as e:
            logger.error(f"清空快取失敗: {e}")

    def get_stats(self) -> dict[str, Any]:
        """獲取快取統計資訊"""
        try:
            # 計算總大小
            total_size_bytes = 0
            if self.config.enable_disk_cache:
                index_data = self._load_index()
                for entry_data in index_data.get("entries", {}).values():
                    total_size_bytes += entry_data.get("size_bytes", 0)

            # 記憶體快取大小
            memory_size_bytes = sum(
                entry.size_bytes for entry in self.memory_cache.values()
            )

            total_requests = (
                self.stats["memory_hits"]
                + self.stats["disk_hits"]
                + self.stats["misses"]
            )
            hit_rate = (
                (self.stats["memory_hits"] + self.stats["disk_hits"])
                / total_requests
                * 100
                if total_requests > 0
                else 0
            )

            return {
                **self.stats,
                "total_size_mb": total_size_bytes / (1024 * 1024),
                "memory_cache_entries": len(self.memory_cache),
                "memory_cache_size_mb": memory_size_bytes / (1024 * 1024),
                "hit_rate": f"{hit_rate:.1f}%",
                "memory_hit_rate": f"{(self.stats['memory_hits'] / total_requests * 100):.1f}%"
                if total_requests > 0
                else "0%",
                "disk_hit_rate": f"{(self.stats['disk_hits'] / total_requests * 100):.1f}%"
                if total_requests > 0
                else "0%",
                "config": asdict(self.config),
            }

        except Exception as e:
            logger.error(f"獲取快取統計失敗: {e}")
            return self.stats

    # ============================================================
    # 快取過期清理功能（新增）
    # ============================================================

    def cleanup_expired(
        self, ttl_days: int = 7, min_keep_entries: int = 100
    ) -> dict[str, int]:
        """
        清理過期的快取檔案

        Args:
            ttl_days: 快取保留天數
            min_keep_entries: 清理時保留的最小檔案數（避免全部清空）

        Returns:
            {
                'deleted_files': 刪除的檔案數,
                'freed_bytes': 釋放的空間（位元組）,
                'remaining_files': 剩餘檔案數
            }
        """
        try:
            from src.services.go_cli import cache_prune
            go_result = cache_prune(
                cache_dir=str(self.cache_dir),
                ttl_days=ttl_days,
                max_size_mb=9999,
                min_keep=min_keep_entries,
            )
            if go_result:
                logger.info(f"🧹 Go 快取清理完成: {go_result}")
                return {
                    "deleted_files": go_result.get("deleted_count", 0),
                    "freed_bytes": int(go_result.get("freed_bytes", 0)),
                    "remaining_files": go_result.get("remaining_count", 0),
                }
            raise RuntimeError("Go cache_prune 回傳空結果")
        except Exception as e:
            logger.warning(f"⚠️ Go 快取清理失敗: {e}")
            raise RuntimeError(f"Go CLI 不可用，無法清理過期快取 (cleanup_expired): {e}") from e

    def cleanup_by_size(
        self, max_size_mb: int = 500, min_keep_entries: int = 100
    ) -> dict[str, int]:
        """
        根據大小限制清理快取（LRU 策略：刪除最久未存取的）

        Args:
            max_size_mb: 最大快取大小 MB
            min_keep_entries: 清理時保留的最小檔案數

        Returns:
            清理結果統計
        """
        try:
            from src.services.go_cli import cache_prune
            go_result = cache_prune(
                cache_dir=str(self.cache_dir),
                ttl_days=9999,
                max_size_mb=max_size_mb,
                min_keep=min_keep_entries,
            )
            if go_result:
                logger.info(f"🧹 Go 大小清理完成: {go_result}")
                return {
                    "deleted_files": go_result.get("deleted_count", 0),
                    "freed_bytes": int(go_result.get("freed_bytes", 0)),
                    "remaining_files": go_result.get("remaining_count", 0),
                    "current_size_mb": go_result.get("current_size_mb", 0.0),
                }
            raise RuntimeError("Go cache_prune 回傳空結果")
        except Exception as e:
            logger.warning(f"⚠️ Go 大小清理失敗: {e}")
            raise RuntimeError(f"Go CLI 不可用，無法根據大小清理快取 (cleanup_by_size): {e}") from e

    def get_cache_stats(self) -> dict[str, Any]:
        """
        取得快取統計資訊

        Returns:
            {
                'total_files': 總檔案數,
                'total_size_mb': 總大小 MB,
                'oldest_entry': 最舊的快取時間,
                'newest_entry': 最新的快取時間,
                'index_entries': 索引中的條目數,
                'memory_cache_entries': 記憶體快取條目數,
                'average_access_count': 平均存取次數
            }
        """
        try:
            from src.services.go_cli import cache_get_stats
            go_result = cache_get_stats(cache_dir=str(self.cache_dir))
            if go_result:
                go_result["memory_cache_entries"] = len(self.memory_cache)
                return go_result
            raise RuntimeError("Go cache_get_stats 回傳空結果")
        except Exception as e:
            logger.warning(f"⚠️ Go 快取統計失敗: {e}")
            raise RuntimeError(f"Go CLI 不可用，無法取得快取統計 (get_cache_stats): {e}") from e

    def clear_all(self, confirm: bool = False) -> bool:
        """
        清除所有快取（需要確認）

        Args:
            confirm: 必須為 True 才會執行

        Returns:
            是否成功
        """
        if not confirm:
            logger.warning("清除所有快取需要 confirm=True 參數")
            return False

        try:
            from src.services.go_cli import cache_clear
            result = cache_clear(cache_dir=str(self.cache_dir), dry_run=False)
            if result:
                with self.memory_lock:
                    self.memory_cache.clear()
                logger.info("🗑️ 已清除所有快取（Go）")
                return True
            raise RuntimeError("Go cache_clear 回傳空結果")
        except Exception as e:
            logger.warning(f"⚠️ Go 清空快取失敗: {e}")
            raise RuntimeError(f"Go CLI 不可用，無法清除所有快取 (clear_all): {e}") from e

    def auto_cleanup(
        self, ttl_days: int = 7, max_size_mb: int = 500, min_keep_entries: int = 100
    ) -> dict[str, Any]:
        """
        自動清理快取（結合過期清理和大小清理）

        Args:
            ttl_days: 快取保留天數
            max_size_mb: 最大快取大小 MB
            min_keep_entries: 保留的最小檔案數

        Returns:
            清理結果統計
        """
        try:
            from src.services.go_cli import cache_prune
            go_result = cache_prune(
                cache_dir=str(self.cache_dir),
                ttl_days=ttl_days,
                max_size_mb=max_size_mb,
                min_keep=min_keep_entries,
            )
            if go_result:
                result = {
                    "expired_cleanup": go_result,
                    "size_cleanup": {},
                    "total_deleted": go_result.get("deleted_count", 0),
                    "total_freed_mb": go_result.get("freed_bytes", 0) / (1024 * 1024),
                }
                if result["total_deleted"] > 0:
                    logger.info(
                        f"🧹 Go 自動清理完成: 共刪除 {result['total_deleted']} 個檔案，"
                        f"釋放 {result['total_freed_mb']:.2f} MB"
                    )
                return result
            raise RuntimeError("Go cache_prune 回傳空結果")
        except Exception as e:
            logger.warning(f"⚠️ Go 自動清理失敗: {e}")
            raise RuntimeError(f"Go CLI 不可用，無法執行自動清理 (auto_cleanup): {e}") from e

    # ============================================================
    # 非同步介面
    # ============================================================

    async def set_async(
        self, key: str, value: Any, ttl_hours: int | None = None
    ) -> bool:
        """非同步設置快取值"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.set, key, value, ttl_hours)

    async def get_async(self, key: str) -> Any | None:
        """非同步獲取快取值"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get, key)

async def delete_async(self, key: str) -> bool:
        """非同步刪除快取值"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.delete, key)


_global_cache_manager: CacheManager | None = None
_global_cache_lock = threading.RLock()


def get_global_cache_manager() -> CacheManager:
    """取得共用快取管理器，避免重複建立背景清理執行緒。"""
    global _global_cache_manager
    with _global_cache_lock:
        if _global_cache_manager is None:
            _global_cache_manager = CacheManager()
        return _global_cache_manager
