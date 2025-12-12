"""
統一爬蟲管理器
整合所有資料源的統一介面
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .base_scraper import HealthCheckConfig, RetryConfig
from .cache_manager import CacheConfig, CacheManager
from .encoding_utils import install_encoding_warning_filter
from .rate_limiter import DomainConfig, RateLimiter
from .sources import AVWikiScraper, ChibaFScraper, JAVDBScraper

logger = logging.getLogger(__name__)

# 安裝編碼警告過濾器
install_encoding_warning_filter()


class DataSource(Enum):
    """資料源枚舉"""

    JAVDB = "javdb"
    AVWIKI = "avwiki"
    CHIBAF = "chibaf"


@dataclass
class UnifiedScraperConfig:
    """統一爬蟲配置"""

    # 資料源優先級
    source_priority: list[DataSource] = None

    # 併發設定
    max_concurrent_sources: int = 2
    source_timeout: float = 30.0

    # 重試設定
    retry_config: RetryConfig = None

    # 快取設定
    cache_config: CacheConfig = None

    # 健康檢查設定
    health_config: HealthCheckConfig = None

    # 結果合併設定
    merge_results: bool = True
    require_consensus: bool = False  # 是否需要多個源的共識
    min_consensus_sources: int = 2

    def __post_init__(self):
        if self.source_priority is None:
            self.source_priority = [
                DataSource.JAVDB,
                DataSource.AVWIKI,
                DataSource.CHIBAF,
            ]

        if self.retry_config is None:
            self.retry_config = RetryConfig()

        if self.cache_config is None:
            self.cache_config = CacheConfig()

        if self.health_config is None:
            self.health_config = HealthCheckConfig()


class UnifiedWebScraper:
    """統一網路爬蟲管理器"""

    def __init__(self, config: UnifiedScraperConfig = None):
        self.config = config or UnifiedScraperConfig()

        # 初始化快取和限流器
        self.cache_manager = CacheManager(self.config.cache_config)
        self.rate_limiter = RateLimiter()

        # 配置各域名的限流規則
        self._configure_domain_limits()

        # 初始化各資料源爬蟲
        self.scrapers = {
            DataSource.JAVDB: JAVDBScraper(
                cache_manager=self.cache_manager, rate_limiter=self.rate_limiter
            ),
            DataSource.AVWIKI: AVWikiScraper(
                cache_manager=self.cache_manager, rate_limiter=self.rate_limiter
            ),
            DataSource.CHIBAF: ChibaFScraper(
                cache_manager=self.cache_manager, rate_limiter=self.rate_limiter
            ),
        }

        # 統計資訊
        self.stats = {
            "total_searches": 0,
            "successful_searches": 0,
            "failed_searches": 0,
            "source_usage": dict.fromkeys(DataSource, 0),
            "source_success_rate": dict.fromkeys(DataSource, 0.0),
            "cache_hits": 0,
            "merged_results": 0,
        }

        logger.info("🚀 統一爬蟲管理器已初始化")

    def _configure_domain_limits(self):
        """配置各域名的限流規則"""
        domain_configs = {
            "javdb.com": DomainConfig(
                requests_per_minute=20,
                requests_per_hour=800,
                burst_limit=5,
                min_interval=1.0,
                max_interval=3.0,
            ),
            "av-wiki.net": DomainConfig(
                requests_per_minute=10,
                requests_per_hour=300,
                burst_limit=3,
                min_interval=2.0,
                max_interval=5.0,
            ),
            "chiba-f.net": DomainConfig(
                requests_per_minute=15,
                requests_per_hour=500,
                burst_limit=4,
                min_interval=1.5,
                max_interval=4.0,
            ),
        }

        for domain, config in domain_configs.items():
            self.rate_limiter.add_domain_config(domain, config)

    async def search_video_info(
        self, video_code: str, sources: list[DataSource] = None
    ) -> dict[str, Any]:
        """
        從多個資料源搜尋影片資訊

        Args:
            video_code: 影片番號
            sources: 指定使用的資料源列表，None表示使用所有配置的源

        Returns:
            合併後的影片資訊
        """
        self.stats["total_searches"] += 1

        if sources is None:
            sources = self.config.source_priority

        # 檢查快取
        cache_key = f"video:{video_code}"
        cached_result = await self.cache_manager.get_async(cache_key)
        if cached_result:
            self.stats["cache_hits"] += 1
            logger.info(f"📋 從快取獲取影片資訊: {video_code}")
            return cached_result

        # 並行搜尋
        logger.info(
            f"🔍 開始搜尋影片 {video_code}，使用資料源: {[s.value for s in sources]}"
        )

        results = await self._search_from_multiple_sources(
            video_code, sources, "search_video"
        )

        # 合併結果
        merged_result = self._merge_video_results(results, video_code)

        # 儲存到快取
        if merged_result.get("actresses"):
            await self.cache_manager.set_async(cache_key, merged_result, ttl_hours=24)

        # 更新統計
        if merged_result.get("actresses"):
            self.stats["successful_searches"] += 1
        else:
            self.stats["failed_searches"] += 1

        logger.info(f"✅ 影片搜尋完成: {video_code}")
        return merged_result

    async def get_actress_info(
        self, actress_name: str, sources: list[DataSource] = None
    ) -> dict[str, Any]:
        """
        從多個資料源獲取女優資訊

        Args:
            actress_name: 女優名稱
            sources: 指定使用的資料源列表

        Returns:
            合併後的女優資訊
        """
        if sources is None:
            sources = self.config.source_priority

        # 檢查快取
        cache_key = f"actress:{actress_name}"
        cached_result = await self.cache_manager.get_async(cache_key)
        if cached_result:
            self.stats["cache_hits"] += 1
            logger.info(f"📋 從快取獲取女優資訊: {actress_name}")
            return cached_result

        logger.info(
            f"👤 開始搜尋女優 {actress_name}，使用資料源: {[s.value for s in sources]}"
        )

        results = await self._search_from_multiple_sources(
            actress_name, sources, "get_actress_info"
        )

        # 合併結果
        merged_result = self._merge_actress_results(results, actress_name)

        # 儲存到快取
        if merged_result.get("total_works", 0) > 0:
            await self.cache_manager.set_async(cache_key, merged_result, ttl_hours=12)

        logger.info(f"✅ 女優搜尋完成: {actress_name}")
        return merged_result

    async def _search_from_multiple_sources(
        self, query: str, sources: list[DataSource], method_name: str
    ) -> dict[DataSource, Any]:
        """從多個資料源併發搜尋"""

        # 限制併發數
        semaphore = asyncio.Semaphore(self.config.max_concurrent_sources)

        async def search_single_source(source: DataSource) -> tuple:
            async with semaphore:
                try:
                    scraper = self.scrapers[source]
                    method = getattr(scraper, method_name)

                    # 設置超時
                    result = await asyncio.wait_for(
                        method(query), timeout=self.config.source_timeout
                    )

                    self.stats["source_usage"][source] += 1
                    logger.debug(f"✅ {source.value} 搜尋成功: {query}")
                    return source, result

                except TimeoutError:
                    logger.warning(f"⏰ {source.value} 搜尋超時: {query}")
                    return source, None
                except Exception as e:
                    logger.error(f"❌ {source.value} 搜尋失敗: {query} - {e}")
                    return source, None

        # 併發執行所有搜尋
        tasks = [search_single_source(source) for source in sources]
        completed_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 整理結果
        results = {}
        for item in completed_results:
            if isinstance(item, tuple):
                source, result = item
                if result is not None:
                    results[source] = result

        return results

    def _merge_video_results(
        self, results: dict[DataSource, Any], video_code: str
    ) -> dict[str, Any]:
        """合併影片搜尋結果"""
        if not results:
            return {
                "video_code": video_code,
                "actresses": [],
                "source": "none",
                "message": "所有資料源都未找到結果",
            }

        # 如果只有一個結果，直接返回
        if len(results) == 1:
            source, result = next(iter(results.items()))
            result["primary_source"] = source.value
            return result

        # 合併多個結果
        merged = {
            "video_code": video_code,
            "actresses": [],
            "studio": None,
            "studio_code": None,
            "title": None,
            "release_date": None,
            "duration": None,
            "director": None,
            "series": None,
            "rating": None,
            "categories": [],
            "sources_used": list(results.keys()),
            "source_count": len(results),
        }

        # 收集所有女優名稱
        all_actresses = set()
        actress_votes = {}

        for source, result in results.items():
            actresses = result.get("actresses", [])
            for actress in actresses:
                all_actresses.add(actress)
                actress_votes[actress] = actress_votes.get(actress, 0) + 1

        # 如果需要共識，只保留多個源都確認的女優
        if (
            self.config.require_consensus
            and len(results) >= self.config.min_consensus_sources
        ):
            min_votes = self.config.min_consensus_sources
            merged["actresses"] = [
                actress
                for actress, votes in actress_votes.items()
                if votes >= min_votes
            ]
            merged["consensus_required"] = True
        else:
            merged["actresses"] = list(all_actresses)
            merged["consensus_required"] = False

        # 合併其他資訊（優先級順序）
        for source in self.config.source_priority:
            if source in results:
                result = results[source]

                # 使用第一個可用的值
                for field in [
                    "studio",
                    "studio_code",
                    "title",
                    "release_date",
                    "duration",
                    "director",
                    "series",
                    "rating",
                ]:
                    if not merged[field] and result.get(field):
                        merged[field] = result[field]
                        merged[f"{field}_source"] = source.value

                # 合併類別
                categories = result.get("categories", [])
                for category in categories:
                    if category not in merged["categories"]:
                        merged["categories"].append(category)

        # 設置主要資料源
        merged["primary_source"] = self.config.source_priority[0].value

        if self.config.merge_results:
            self.stats["merged_results"] += 1

        return merged

    def _merge_actress_results(
        self, results: dict[DataSource, Any], actress_name: str
    ) -> dict[str, Any]:
        """合併女優資訊結果"""
        if not results:
            return {
                "actress_name": actress_name,
                "total_works": 0,
                "works": [],
                "studio_distribution": {},
                "sources_used": [],
            }

        # 合併所有作品
        all_works = []
        studio_count = {}

        for source, result in results.items():
            works = result.get("works", [])
            all_works.extend(works)

            # 合併片商統計
            source_studios = result.get("studio_distribution", {})
            for studio, count in source_studios.items():
                studio_count[studio] = studio_count.get(studio, 0) + count

        # 去重作品（基於標題）
        unique_works = []
        seen_titles = set()

        for work in all_works:
            title = work.get("title", "")
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_works.append(work)

        return {
            "actress_name": actress_name,
            "total_works": len(unique_works),
            "works": unique_works,
            "studio_distribution": studio_count,
            "sources_used": [source.value for source in results],
            "source_count": len(results),
        }

    async def batch_search_videos(
        self,
        video_codes: list[str],
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """批次搜尋多個影片"""

        if not video_codes:
            return {}

        logger.info(f"📦 開始批次搜尋 {len(video_codes)} 個影片")

        # 分批處理以控制併發
        batch_size = 10
        all_results = {}

        for i in range(0, len(video_codes), batch_size):
            batch_codes = video_codes[i : i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(video_codes) + batch_size - 1) // batch_size

            if progress_callback:
                progress_callback(
                    f"處理批次 {batch_num}/{total_batches} ({len(batch_codes)} 個影片)..."
                )

            logger.info(f"📦 處理批次 {batch_num}/{total_batches}")

            # 並行處理當前批次
            tasks = [self.search_video_info(code) for code in batch_codes]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # 整理批次結果
            for j, result in enumerate(batch_results):
                code = batch_codes[j]
                if isinstance(result, Exception):
                    logger.error(f"❌ 搜尋 {code} 失敗: {result}")
                    all_results[code] = {
                        "video_code": code,
                        "actresses": [],
                        "error": str(result),
                    }
                else:
                    all_results[code] = result

                if progress_callback:
                    status = (
                        "✅ 成功" if not isinstance(result, Exception) else "❌ 失敗"
                    )
                    progress_callback(f"{code}: {status}")

            # 批次間暫停
            if i + batch_size < len(video_codes):
                await asyncio.sleep(1.0)

        successful = sum(1 for r in all_results.values() if r.get("actresses"))
        logger.info(f"🎉 批次搜尋完成: {successful}/{len(video_codes)} 成功")

        return all_results

    def get_comprehensive_stats(self) -> dict[str, Any]:
        """獲取綜合統計資訊"""
        # 計算各源成功率
        for source in DataSource:
            usage = self.stats["source_usage"][source]
            if usage > 0:
                # 從各爬蟲獲取成功率統計
                scraper_stats = self.scrapers[source].get_comprehensive_stats()
                scraper_success = scraper_stats.get("scraper_stats", {}).get(
                    "successful_requests", 0
                )
                scraper_total = scraper_stats.get("scraper_stats", {}).get(
                    "total_requests", 1
                )
                self.stats["source_success_rate"][source] = (
                    (scraper_success / scraper_total * 100) if scraper_total > 0 else 0
                )

        return {
            "unified_scraper_stats": self.stats,
            "cache_stats": self.cache_manager.get_stats(),
            "rate_limiter_stats": self.rate_limiter.get_stats(),
            "individual_scrapers": {
                source.value: scraper.get_comprehensive_stats()
                for source, scraper in self.scrapers.items()
            },
        }

    def clear_all_caches(self):
        """清空所有快取"""
        self.cache_manager.clear_cache()
        for scraper in self.scrapers.values():
            scraper.clear_cache()
        logger.info("🧹 已清空所有爬蟲快取")

    async def health_check(self) -> dict[str, Any]:
        """執行健康檢查"""
        health_results = {}

        for source, scraper in self.scrapers.items():
            try:
                # 嘗試搜尋一個常見番號進行健康檢查
                test_result = await asyncio.wait_for(
                    scraper.search_video("test-001"), timeout=10.0
                )
                health_results[source.value] = {
                    "status": "healthy",
                    "response_time": "< 10s",
                }
            except Exception as e:
                health_results[source.value] = {"status": "unhealthy", "error": str(e)}

        return {
            "timestamp": asyncio.get_event_loop().time(),
            "sources": health_results,
            "overall_health": all(
                result["status"] == "healthy" for result in health_results.values()
            ),
        }
