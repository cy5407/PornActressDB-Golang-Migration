"""
統一快取管理模組

整合專案中所有快取機制：
1. CacheManager (磁碟 + 記憶體多層快取)
2. WebSearcher.search_cache (記憶體快取)
3. SafeJAVDBSearcher.cache (JSON 檔案快取)

提供統一的介面和 TTL 管理
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """快取統計資料"""

    total_entries: int = 0
    total_size_mb: float = 0.0
    memory_entries: int = 0
    disk_entries: int = 0
    hit_rate: float = 0.0
    oldest_entry_age_days: float = 0.0


class UnifiedCacheManager:
    """
    統一快取管理器

    整合多個快取來源，提供統一的介面和管理功能
    """

    def __init__(self, config=None):
        """
        初始化統一快取管理器

        Args:
            config: 可選的配置管理器實例
        """
        self._cache_sources: dict[str, Any] = {}
        self._config = config

        # 預設 TTL 設定（天）
        self.default_ttl_days = 7
        self.max_cache_size_mb = 500
        self.min_keep_entries = 100

        # 從配置載入設定
        if config:
            try:
                self.default_ttl_days = config.getint("cache", "ttl_days", fallback=7)
                self.max_cache_size_mb = config.getint(
                    "cache", "max_size_mb", fallback=500
                )
            except Exception:
                pass

        logger.info(
            f"🔗 統一快取管理器已初始化 (TTL: {self.default_ttl_days} 天, 大小限制: {self.max_cache_size_mb} MB)"
        )

    def register_cache_source(self, name: str, cache_instance: Any):
        """
        註冊快取來源

        Args:
            name: 快取來源名稱
            cache_instance: 快取實例（需提供 get/set/clear 方法）
        """
        self._cache_sources[name] = cache_instance
        logger.debug(f"📦 已註冊快取來源: {name}")

    def unregister_cache_source(self, name: str):
        """取消註冊快取來源"""
        if name in self._cache_sources:
            del self._cache_sources[name]
            logger.debug(f"📤 已移除快取來源: {name}")

    # ========================================
    # 統一快取操作
    # ========================================

    def get(self, key: str, source: str = None) -> Any | None:
        """
        從快取取得值

        Args:
            key: 快取鍵
            source: 指定快取來源（None 表示搜尋所有）

        Returns:
            快取值或 None
        """
        if source:
            # 從指定來源取得
            cache = self._cache_sources.get(source)
            if cache and hasattr(cache, "get"):
                return cache.get(key)
            return None

        # 搜尋所有來源
        for name, cache in self._cache_sources.items():
            if hasattr(cache, "get"):
                value = cache.get(key)
                if value is not None:
                    logger.debug(f"📋 快取命中 ({name}): {key[:50]}...")
                    return value

        return None

    def set(self, key: str, value: Any, source: str = None, ttl_hours: int = None):
        """
        設定快取值

        Args:
            key: 快取鍵
            value: 快取值
            source: 指定快取來源（None 表示使用預設）
            ttl_hours: TTL 小時數
        """
        ttl = ttl_hours or (self.default_ttl_days * 24)

        if source:
            cache = self._cache_sources.get(source)
            if cache and hasattr(cache, "set"):
                cache.set(key, value, ttl_hours=ttl)
                return

        # 使用第一個可用的快取來源
        for _name, cache in self._cache_sources.items():
            if hasattr(cache, "set"):
                cache.set(key, value, ttl_hours=ttl)
                return

    def delete(self, key: str, source: str = None):
        """刪除快取項目"""
        if source:
            cache = self._cache_sources.get(source)
            if cache and hasattr(cache, "delete"):
                cache.delete(key)
                return

        # 從所有來源刪除
        for cache in self._cache_sources.values():
            if hasattr(cache, "delete"):
                cache.delete(key)

    # ========================================
    # 統一清理操作
    # ========================================

    def cleanup_all(
        self, ttl_days: int = None, max_size_mb: int = None
    ) -> dict[str, Any]:
        """
        清理所有快取來源

        Args:
            ttl_days: 過期天數（None 使用預設值）
            max_size_mb: 大小限制 MB（None 使用預設值）

        Returns:
            清理結果統計
        """
        ttl = ttl_days or self.default_ttl_days
        max_size = max_size_mb or self.max_cache_size_mb

        results = {
            "sources_cleaned": 0,
            "total_deleted": 0,
            "total_freed_mb": 0.0,
            "details": {},
        }

        for name, cache in self._cache_sources.items():
            try:
                source_result = self._cleanup_single_source(name, cache, ttl, max_size)
                results["details"][name] = source_result
                results["total_deleted"] += source_result.get("deleted", 0)
                results["total_freed_mb"] += source_result.get("freed_mb", 0.0)
                results["sources_cleaned"] += 1
            except Exception as e:
                logger.error(f"❌ 清理快取來源 {name} 失敗: {e}")
                results["details"][name] = {"error": str(e)}

        if results["total_deleted"] > 0:
            logger.info(
                f"🧹 快取清理完成: 共刪除 {results['total_deleted']} 項，釋放 {results['total_freed_mb']:.2f} MB"
            )

        return results

    def _cleanup_single_source(
        self, name: str, cache: Any, ttl_days: int, max_size_mb: int
    ) -> dict[str, Any]:
        """清理單一快取來源"""
        result = {"deleted": 0, "freed_mb": 0.0}

        # CacheManager 有 auto_cleanup 方法
        if hasattr(cache, "auto_cleanup"):
            cleanup_result = cache.auto_cleanup(
                ttl_days=ttl_days,
                max_size_mb=max_size_mb,
                min_keep_entries=self.min_keep_entries,
            )
            result["deleted"] = cleanup_result.get("total_deleted", 0)
            result["freed_mb"] = cleanup_result.get("total_freed_mb", 0.0)

        # 簡單快取只有 clear 方法
        elif hasattr(cache, "clear"):
            if hasattr(cache, "__len__"):
                result["deleted"] = len(cache)
            cache.clear()

        # dict 類型快取
        elif isinstance(cache, dict):
            result["deleted"] = len(cache)
            cache.clear()

        return result

    def clear_all(self, confirm: bool = False) -> bool:
        """
        清除所有快取

        Args:
            confirm: 必須為 True 才會執行

        Returns:
            是否成功
        """
        if not confirm:
            logger.warning("⚠️ 清除所有快取需要 confirm=True 參數")
            return False

        for name, cache in self._cache_sources.items():
            try:
                if hasattr(cache, "clear_all"):
                    cache.clear_all(confirm=True)
                elif hasattr(cache, "clear_cache"):
                    cache.clear_cache()
                elif hasattr(cache, "clear") or isinstance(cache, dict):
                    cache.clear()
                logger.info(f"🗑️ 已清除快取: {name}")
            except Exception as e:
                logger.error(f"❌ 清除快取 {name} 失敗: {e}")

        return True

    # ========================================
    # 統計和監控
    # ========================================

    def get_stats(self) -> dict[str, Any]:
        """
        取得所有快取統計

        Returns:
            統計資訊字典
        """
        stats = {
            "total_sources": len(self._cache_sources),
            "sources": {},
            "summary": CacheStats(),
        }

        total_entries = 0
        total_size_mb = 0.0

        for name, cache in self._cache_sources.items():
            try:
                source_stats = self._get_source_stats(cache)
                stats["sources"][name] = source_stats
                total_entries += source_stats.get("entries", 0)
                total_size_mb += source_stats.get("size_mb", 0.0)
            except Exception as e:
                stats["sources"][name] = {"error": str(e)}

        stats["summary"] = {
            "total_entries": total_entries,
            "total_size_mb": total_size_mb,
            "memory_entries": sum(
                s.get("memory_entries", 0)
                for s in stats["sources"].values()
                if isinstance(s, dict)
            ),
            "disk_entries": sum(
                s.get("disk_entries", 0)
                for s in stats["sources"].values()
                if isinstance(s, dict)
            ),
        }

        return stats

    def _get_source_stats(self, cache: Any) -> dict[str, Any]:
        """取得單一來源統計"""
        # CacheManager
        if hasattr(cache, "get_stats"):
            full_stats = cache.get_stats()
            return {
                "entries": full_stats.get("memory_cache_entries", 0)
                + len(full_stats.get("index_entries", [])),
                "size_mb": full_stats.get("total_size_mb", 0.0),
                "memory_entries": full_stats.get("memory_cache_entries", 0),
                "disk_entries": len(full_stats.get("index_entries", []))
                if isinstance(full_stats.get("index_entries"), list)
                else 0,
                "hit_rate": full_stats.get("hit_rate", "0%"),
            }

        # dict 類型
        if isinstance(cache, dict):
            return {
                "entries": len(cache),
                "size_mb": 0.0,
                "memory_entries": len(cache),
                "disk_entries": 0,
            }

        # 有 __len__ 方法的物件
        if hasattr(cache, "__len__"):
            return {"entries": len(cache), "size_mb": 0.0}

        return {"entries": 0, "size_mb": 0.0}

    def print_stats(self):
        """印出格式化的統計資訊"""
        stats = self.get_stats()

        print("\n" + "=" * 60)
        print("📊 快取統計報告")
        print("=" * 60)

        print(f"\n📦 註冊的快取來源: {stats['total_sources']}")

        for name, source_stats in stats["sources"].items():
            print(f"\n  【{name}】")
            if "error" in source_stats:
                print(f"    ❌ 錯誤: {source_stats['error']}")
            else:
                print(f"    條目數: {source_stats.get('entries', 0)}")
                print(f"    大小: {source_stats.get('size_mb', 0):.2f} MB")
                if "hit_rate" in source_stats:
                    print(f"    命中率: {source_stats['hit_rate']}")

        print("\n📈 總計:")
        print(f"    總條目數: {stats['summary']['total_entries']}")
        print(f"    總大小: {stats['summary']['total_size_mb']:.2f} MB")
        print("=" * 60 + "\n")


# ========================================
# 全域快取管理器實例
# ========================================

_global_cache_manager: UnifiedCacheManager | None = None


def get_cache_manager(config=None) -> UnifiedCacheManager:
    """
    取得全域快取管理器實例（單例模式）

    Args:
        config: 可選的配置管理器

    Returns:
        UnifiedCacheManager 實例
    """
    global _global_cache_manager

    if _global_cache_manager is None:
        _global_cache_manager = UnifiedCacheManager(config)

    return _global_cache_manager


def cleanup_all_caches(ttl_days: int = 7, max_size_mb: int = 500) -> dict[str, Any]:
    """
    清理所有已註冊的快取

    便捷函式，可從任何地方呼叫

    Args:
        ttl_days: 過期天數
        max_size_mb: 大小限制 MB

    Returns:
        清理結果統計
    """
    manager = get_cache_manager()
    return manager.cleanup_all(ttl_days=ttl_days, max_size_mb=max_size_mb)
