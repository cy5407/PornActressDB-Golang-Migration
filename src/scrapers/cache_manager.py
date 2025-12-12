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
import pickle
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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
                    json.dump(initial_index, f, indent=2, ensure_ascii=False)
                logger.debug("📊 快取索引檔案已建立")
            else:
                # 驗證現有索引
                with open(self.index_path, encoding="utf-8") as f:
                    index_data = json.load(f)
                    if "entries" not in index_data:
                        # 修復損壞的索引
                        index_data["entries"] = {}
                        with open(self.index_path, "w", encoding="utf-8") as f_write:
                            json.dump(index_data, f_write, indent=2, ensure_ascii=False)
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
                    json.dump(initial_index, f, indent=2, ensure_ascii=False)
            except Exception as fallback_error:
                logger.error(f"建立備援索引失敗: {fallback_error}")

    def _load_index(self) -> dict:
        """載入 JSON 索引"""
        try:
            with self.index_lock, open(self.index_path, encoding="utf-8") as f:
                return json.load(f)
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
                json.dump(index_data, f, indent=2, ensure_ascii=False)
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
        """序列化值並選擇性壓縮"""
        try:
            # 序列化
            serialized = pickle.dumps(value)

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
        """反序列化值"""
        try:
            if compressed:
                data = gzip.decompress(data)
            return pickle.loads(data)
        except Exception as e:
            logger.error(f"反序列化值失敗: {e}")
            return None

    def _is_expired(self, created_at: float, ttl_seconds: int) -> bool:
        """檢查是否過期"""
        return time.time() - created_at > ttl_seconds

    def set(self, key: str, value: Any, ttl_hours: int | None = None) -> bool:
        """設置快取值"""
        ttl_seconds = (ttl_hours or self.config.default_ttl_hours) * 3600
        cache_key = self._generate_cache_key(key)
        current_time = time.time()

        try:
            # 序列化和壓縮
            serialized_data, compressed = self._serialize_value(value)
            size_bytes = len(serialized_data)

            # 檢查檔案大小限制
            max_size_bytes = self.config.max_file_size_mb * 1024 * 1024
            if size_bytes > max_size_bytes:
                logger.warning(
                    f"快取值過大 ({size_bytes / 1024 / 1024:.1f}MB)，跳過快取"
                )
                return False

            # 建立快取條目
            entry = CacheEntry(
                key=cache_key,
                value=value,
                created_at=current_time,
                ttl_seconds=ttl_seconds,
                last_accessed=current_time,
                compressed=compressed,
                size_bytes=size_bytes,
            )

            # 設置記憶體快取
            if self.config.enable_memory_cache:
                with self.memory_lock:
                    self.memory_cache[cache_key] = entry
                    self._cleanup_memory_cache()

            # 設置磁碟快取
            if self.config.enable_disk_cache:
                file_path = self._get_file_path(cache_key)

                # 寫入檔案
                with open(file_path, "wb") as f:
                    f.write(serialized_data)

                # 更新 JSON 索引
                index_data = self._load_index()
                index_data["entries"][cache_key] = {
                    "file_path": str(file_path),
                    "created_at": current_time,
                    "ttl_seconds": ttl_seconds,
                    "last_accessed": current_time,
                    "access_count": 0,
                    "compressed": compressed,
                    "size_bytes": size_bytes,
                }
                self._save_index(index_data)

            self.stats["sets"] += 1
            logger.debug(f"💾 已快取: {key} ({size_bytes} bytes)")
            return True

        except Exception as e:
            logger.error(f"設置快取失敗: {e}")
            return False

    def get(self, key: str) -> Any | None:
        """獲取快取值"""
        cache_key = self._generate_cache_key(key)
        current_time = time.time()

        # 嘗試記憶體快取
        if self.config.enable_memory_cache:
            with self.memory_lock:
                if cache_key in self.memory_cache:
                    entry = self.memory_cache[cache_key]

                    # 檢查是否過期
                    if not self._is_expired(entry.created_at, entry.ttl_seconds):
                        entry.access_count += 1
                        entry.last_accessed = current_time
                        self.stats["memory_hits"] += 1
                        logger.debug(f"📋 記憶體快取命中: {key}")
                        return entry.value
                    else:
                        # 過期，從記憶體移除
                        del self.memory_cache[cache_key]

        # 嘗試磁碟快取
        if self.config.enable_disk_cache:
            try:
                index_data = self._load_index()
                entry_data = index_data.get("entries", {}).get(cache_key)

                if entry_data:
                    file_path = entry_data["file_path"]
                    created_at = entry_data["created_at"]
                    ttl_seconds = entry_data["ttl_seconds"]
                    compressed = entry_data["compressed"]
                    access_count = entry_data.get("access_count", 0)

                    # 檢查是否過期
                    if not self._is_expired(created_at, ttl_seconds):
                        file_path_obj = Path(file_path)

                        if file_path_obj.exists():
                            # 讀取檔案
                            with open(file_path_obj, "rb") as f:
                                data = f.read()

                            # 反序列化
                            value = self._deserialize_value(data, compressed)

                            if value is not None:
                                # 更新訪問統計
                                entry_data["access_count"] = access_count + 1
                                entry_data["last_accessed"] = current_time
                                index_data["entries"][cache_key] = entry_data
                                self._save_index(index_data)

                                # 載入到記憶體快取
                                if self.config.enable_memory_cache:
                                    with self.memory_lock:
                                        entry = CacheEntry(
                                            key=cache_key,
                                            value=value,
                                            created_at=created_at,
                                            ttl_seconds=ttl_seconds,
                                            access_count=access_count + 1,
                                            last_accessed=current_time,
                                            compressed=compressed,
                                            size_bytes=len(data),
                                        )
                                        self.memory_cache[cache_key] = entry

                                self.stats["disk_hits"] += 1
                                logger.debug(f"💿 磁碟快取命中: {key}")
                                return value
                    else:
                        # 過期，清理
                        self._delete_cache_entry(cache_key, file_path)

            except Exception as e:
                logger.error(f"讀取磁碟快取失敗: {e}")

        self.stats["misses"] += 1
        logger.debug(f"❌ 快取未命中: {key}")
        return None

    def delete(self, key: str) -> bool:
        """刪除快取條目"""
        cache_key = self._generate_cache_key(key)

        try:
            # 從記憶體移除
            if self.config.enable_memory_cache:
                with self.memory_lock:
                    self.memory_cache.pop(cache_key, None)

            # 從磁碟移除
            if self.config.enable_disk_cache:
                index_data = self._load_index()
                entry_data = index_data.get("entries", {}).get(cache_key)

                if entry_data:
                    file_path = entry_data["file_path"]
                    self._delete_cache_entry(cache_key, file_path)

            self.stats["deletes"] += 1
            logger.debug(f"🗑️ 已刪除快取: {key}")
            return True

        except Exception as e:
            logger.error(f"刪除快取失敗: {e}")
            return False

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
        result = {"deleted_files": 0, "freed_bytes": 0, "remaining_files": 0}

        try:
            ttl_seconds = ttl_days * 24 * 3600
            current_time = time.time()

            # 載入索引
            index_data = self._load_index()
            entries = index_data.get("entries", {})

            # 檢查是否需要保留最小條目數
            if len(entries) <= min_keep_entries:
                result["remaining_files"] = len(entries)
                logger.info(
                    f"🧹 快取條目數 ({len(entries)}) 小於最小保留數 ({min_keep_entries})，跳過清理"
                )
                return result

            # 收集過期條目
            expired_entries = []
            for cache_key, entry_data in entries.items():
                created_at = entry_data.get("created_at", 0)
                if current_time - created_at > ttl_seconds:
                    expired_entries.append((cache_key, entry_data))

            # 確保不會刪除太多，保留最小條目數
            max_deletable = len(entries) - min_keep_entries
            if len(expired_entries) > max_deletable:
                # 按建立時間排序，刪除最舊的
                expired_entries.sort(key=lambda x: x[1].get("created_at", 0))
                expired_entries = expired_entries[:max_deletable]

            # 執行刪除
            for cache_key, entry_data in expired_entries:
                file_path = entry_data.get("file_path")
                size_bytes = entry_data.get("size_bytes", 0)

                try:
                    # 刪除檔案
                    if file_path:
                        file_path_obj = Path(file_path)
                        if file_path_obj.exists():
                            file_path_obj.unlink()

                    # 從索引移除
                    if cache_key in entries:
                        del entries[cache_key]

                    result["deleted_files"] += 1
                    result["freed_bytes"] += size_bytes

                except Exception as e:
                    logger.warning(f"刪除快取條目 {cache_key} 失敗: {e}")

            # 儲存更新後的索引
            self._save_index(index_data)

            result["remaining_files"] = len(entries)

            if result["deleted_files"] > 0:
                freed_mb = result["freed_bytes"] / (1024 * 1024)
                logger.info(
                    f"🧹 快取清理完成: 刪除 {result['deleted_files']} 個過期檔案，釋放 {freed_mb:.2f} MB"
                )

        except Exception as e:
            logger.error(f"清理過期快取失敗: {e}")

        return result

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
        result = {
            "deleted_files": 0,
            "freed_bytes": 0,
            "remaining_files": 0,
            "current_size_mb": 0.0,
        }

        try:
            max_size_bytes = max_size_mb * 1024 * 1024

            # 載入索引
            index_data = self._load_index()
            entries = index_data.get("entries", {})

            # 計算當前總大小
            total_size = sum(e.get("size_bytes", 0) for e in entries.values())
            result["current_size_mb"] = total_size / (1024 * 1024)

            # 檢查是否需要清理
            if total_size <= max_size_bytes:
                result["remaining_files"] = len(entries)
                logger.info(
                    f"🧹 當前快取大小 ({result['current_size_mb']:.2f} MB) 未超過限制 ({max_size_mb} MB)，跳過清理"
                )
                return result

            # 需要釋放的空間
            bytes_to_free = total_size - max_size_bytes

            # 按最後存取時間排序（LRU）
            sorted_entries = sorted(
                entries.items(),
                key=lambda x: x[1].get("last_accessed", x[1].get("created_at", 0)),
            )

            # 計算可刪除的最大數量
            max_deletable = len(entries) - min_keep_entries

            # 刪除直到釋放足夠空間
            freed_bytes = 0
            deleted_count = 0

            for cache_key, entry_data in sorted_entries:
                if freed_bytes >= bytes_to_free or deleted_count >= max_deletable:
                    break

                file_path = entry_data.get("file_path")
                size_bytes = entry_data.get("size_bytes", 0)

                try:
                    # 刪除檔案
                    if file_path:
                        file_path_obj = Path(file_path)
                        if file_path_obj.exists():
                            file_path_obj.unlink()

                    # 從索引移除
                    if cache_key in entries:
                        del entries[cache_key]

                    freed_bytes += size_bytes
                    deleted_count += 1

                except Exception as e:
                    logger.warning(f"刪除快取條目 {cache_key} 失敗: {e}")

            # 儲存更新後的索引
            self._save_index(index_data)

            result["deleted_files"] = deleted_count
            result["freed_bytes"] = freed_bytes
            result["remaining_files"] = len(entries)
            result["current_size_mb"] = (total_size - freed_bytes) / (1024 * 1024)

            if deleted_count > 0:
                freed_mb = freed_bytes / (1024 * 1024)
                logger.info(
                    f"🧹 大小清理完成: 刪除 {deleted_count} 個檔案，釋放 {freed_mb:.2f} MB"
                )

        except Exception as e:
            logger.error(f"根據大小清理快取失敗: {e}")

        return result

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
            index_data = self._load_index()
            entries = index_data.get("entries", {})

            if not entries:
                return {
                    "total_files": 0,
                    "total_size_mb": 0.0,
                    "oldest_entry": None,
                    "newest_entry": None,
                    "index_entries": 0,
                    "memory_cache_entries": len(self.memory_cache),
                    "average_access_count": 0.0,
                }

            # 計算統計
            total_size = sum(e.get("size_bytes", 0) for e in entries.values())
            created_times = [e.get("created_at", 0) for e in entries.values()]
            access_counts = [e.get("access_count", 0) for e in entries.values()]

            oldest_time = min(created_times) if created_times else None
            newest_time = max(created_times) if created_times else None
            avg_access = sum(access_counts) / len(access_counts) if access_counts else 0

            return {
                "total_files": len(entries),
                "total_size_mb": total_size / (1024 * 1024),
                "oldest_entry": datetime.fromtimestamp(oldest_time).isoformat()
                if oldest_time
                else None,
                "newest_entry": datetime.fromtimestamp(newest_time).isoformat()
                if newest_time
                else None,
                "index_entries": len(entries),
                "memory_cache_entries": len(self.memory_cache),
                "average_access_count": avg_access,
            }

        except Exception as e:
            logger.error(f"獲取快取統計失敗: {e}")
            return {
                "total_files": 0,
                "total_size_mb": 0.0,
                "oldest_entry": None,
                "newest_entry": None,
                "index_entries": 0,
                "memory_cache_entries": 0,
                "average_access_count": 0.0,
                "error": str(e),
            }

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
            # 使用現有的 clear_cache 方法
            self.clear_cache()
            logger.info("🗑️ 已清除所有快取（含確認）")
            return True
        except Exception as e:
            logger.error(f"清除所有快取失敗: {e}")
            return False

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
        result = {
            "expired_cleanup": {},
            "size_cleanup": {},
            "total_deleted": 0,
            "total_freed_mb": 0.0,
        }

        try:
            # 先清理過期
            expired_result = self.cleanup_expired(ttl_days, min_keep_entries)
            result["expired_cleanup"] = expired_result

            # 再檢查大小
            size_result = self.cleanup_by_size(max_size_mb, min_keep_entries)
            result["size_cleanup"] = size_result

            # 總計
            result["total_deleted"] = expired_result.get(
                "deleted_files", 0
            ) + size_result.get("deleted_files", 0)
            result["total_freed_mb"] = (
                expired_result.get("freed_bytes", 0) + size_result.get("freed_bytes", 0)
            ) / (1024 * 1024)

            if result["total_deleted"] > 0:
                logger.info(
                    f"🧹 自動清理完成: 共刪除 {result['total_deleted']} 個檔案，釋放 {result['total_freed_mb']:.2f} MB"
                )

        except Exception as e:
            logger.error(f"自動清理失敗: {e}")
            result["error"] = str(e)

        return result

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
