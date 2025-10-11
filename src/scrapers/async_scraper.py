# -*- coding: utf-8 -*-
"""
非同步網路爬蟲模組
提供高效的併發網路爬蟲功能
"""

import asyncio
import aiohttp
import logging
import time
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass
from pathlib import Path
import json
import threading
from urllib.parse import urljoin, urlparse

from .encoding_utils import EncodingDetector, install_encoding_warning_filter
from .rate_limiter import RateLimiter
from .cache_manager import CacheManager

logger = logging.getLogger(__name__)

# 安裝編碼警告過濾器
install_encoding_warning_filter()


@dataclass
class ScrapingConfig:
    """爬蟲配置類"""
    max_concurrent: int = 3               # 最大併發連線數
    request_timeout: int = 30             # 請求超時時間(秒)
    connect_timeout: int = 10             # 連線超時時間(秒)
    total_timeout: int = 60               # 總超時時間(秒)
    max_retries: int = 3                  # 最大重試次數
    backoff_factor: float = 2.0           # 指數退避因子
    enable_cache: bool = True             # 啟用快取
    cache_duration_hours: int = 24        # 快取持續時間(小時)
    user_agent_rotation: bool = True      # 啟用 User-Agent 輪替
    respect_robots_txt: bool = True       # 遵守 robots.txt
    max_redirects: int = 5                # 最大重定向次數


@dataclass
class ScrapingResult:
    """爬蟲結果類"""
    url: str
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    status_code: Optional[int] = None
    response_time: float = 0.0
    encoding: Optional[str] = None
    from_cache: bool = False


class AsyncWebScraper:
    """非同步網路爬蟲類"""
    
    def __init__(self, config: ScrapingConfig = None, cache_manager: CacheManager = None):
        self.config = config or ScrapingConfig()
        self.encoding_detector = EncodingDetector()
        
        # 初始化限流器和快取管理器
        self.rate_limiter = RateLimiter()
        self.cache_manager = cache_manager or CacheManager()
        
        # 統計資訊
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'cache_hits': 0,
            'total_response_time': 0.0,
            'requests_by_domain': {},
            'encoding_stats': {}
        }
        
        # User-Agent 池
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36'
        ]
        self.current_ua_index = 0
        
        logger.info(f"🚀 AsyncWebScraper 已初始化 - 最大併發: {self.config.max_concurrent}")
    
    def _get_headers(self) -> Dict[str, str]:
        """獲取請求標頭"""
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8,ja;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
        }
        
        # 輪替 User-Agent
        if self.config.user_agent_rotation:
            headers['User-Agent'] = self.user_agents[self.current_ua_index]
            self.current_ua_index = (self.current_ua_index + 1) % len(self.user_agents)
        else:
            headers['User-Agent'] = self.user_agents[0]
            
        return headers
    
    async def _make_request(self, session: aiohttp.ClientSession, url: str) -> ScrapingResult:
        """執行單個請求"""
        start_time = time.time()
        domain = urlparse(url).netloc
        
        try:
            # 檢查快取
            if self.config.enable_cache:
                cached_result = await self.cache_manager.get_async(url)
                if cached_result:
                    self.stats['cache_hits'] += 1
                    logger.debug(f"📋 從快取獲取: {url}")
                    return ScrapingResult(
                        url=url,
                        success=True,
                        data=cached_result,
                        from_cache=True,
                        response_time=time.time() - start_time
                    )
            
            # 應用頻率限制
            await self.rate_limiter.wait_if_needed_async(domain)
            
            # 發送請求
            timeout = aiohttp.ClientTimeout(
                total=self.config.total_timeout,
                connect=self.config.connect_timeout,
                sock_read=self.config.request_timeout
            )
            
            async with session.get(
                url, 
                headers=self._get_headers(),
                timeout=timeout,
                max_redirects=self.config.max_redirects
            ) as response:
                
                # 讀取響應內容
                content_bytes = await response.read()
                
                # 自動編碼檢測
                decoded_content, encoding = self.encoding_detector.detect_and_decode(content_bytes)
                
                # 更新統計
                response_time = time.time() - start_time
                self._update_stats(domain, True, response_time, encoding)
                
                # 儲存到快取
                if self.config.enable_cache and response.status == 200:
                    await self.cache_manager.set_async(url, decoded_content)
                
                return ScrapingResult(
                    url=url,
                    success=True,
                    data=decoded_content,
                    status_code=response.status,
                    response_time=response_time,
                    encoding=encoding
                )
                
        except asyncio.TimeoutError:
            error_msg = f"請求超時: {url}"
            logger.warning(f"⏰ {error_msg}")
            self._update_stats(domain, False, time.time() - start_time)
            return ScrapingResult(url=url, success=False, error=error_msg)
            
        except aiohttp.ClientError as e:
            error_msg = f"客戶端錯誤: {e}"
            logger.warning(f"🌐 {error_msg} - {url}")
            self._update_stats(domain, False, time.time() - start_time)
            return ScrapingResult(url=url, success=False, error=error_msg)
            
        except Exception as e:
            error_msg = f"未知錯誤: {e}"
            logger.error(f"❌ {error_msg} - {url}")
            self._update_stats(domain, False, time.time() - start_time)
            return ScrapingResult(url=url, success=False, error=error_msg)
    
    async def _make_request_with_retry(self, session: aiohttp.ClientSession, url: str) -> ScrapingResult:
        """帶重試機制的請求"""
        last_result = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                result = await self._make_request(session, url)
                
                if result.success:
                    return result
                    
                last_result = result
                
                # 如果不是最後一次嘗試，則等待後重試
                if attempt < self.config.max_retries:
                    wait_time = self.config.backoff_factor ** attempt
                    logger.info(f"⏳ 第 {attempt + 1} 次嘗試失敗，等待 {wait_time:.1f} 秒後重試: {url}")
                    await asyncio.sleep(wait_time)
                    
            except Exception as e:
                error_msg = f"重試過程中發生錯誤: {e}"
                logger.error(f"❌ {error_msg}")
                last_result = ScrapingResult(url=url, success=False, error=error_msg)
        
        logger.error(f"❌ 所有重試都失敗了: {url}")
        return last_result or ScrapingResult(url=url, success=False, error="所有重試都失敗")
    
    async def scrape_multiple(
        self, 
        urls: List[str], 
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> List[ScrapingResult]:
        """併發爬取多個URL"""
        
        if not urls:
            return []
            
        logger.info(f"🚀 開始併發爬取 {len(urls)} 個URL")
        
        # 創建信號量控制併發數
        semaphore = asyncio.Semaphore(self.config.max_concurrent)
        
        async def scrape_with_semaphore(session: aiohttp.ClientSession, url: str) -> ScrapingResult:
            async with semaphore:
                result = await self._make_request_with_retry(session, url)
                if progress_callback:
                    status = "✅ 成功" if result.success else f"❌ 失敗: {result.error}"
                    progress_callback(f"{url}: {status}")
                return result
        
        # 創建會話並執行所有請求
        connector = aiohttp.TCPConnector(
            limit=self.config.max_concurrent * 2,  # 連線池大小
            limit_per_host=self.config.max_concurrent,
            ttl_dns_cache=300,  # DNS快取5分鐘
            use_dns_cache=True
        )
        
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [scrape_with_semaphore(session, url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 處理異常結果
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    error_result = ScrapingResult(
                        url=urls[i], 
                        success=False, 
                        error=str(result)
                    )
                    processed_results.append(error_result)
                else:
                    processed_results.append(result)
        
        successful = sum(1 for r in processed_results if r.success)
        logger.info(f"✅ 爬取完成: {successful}/{len(urls)} 成功")
        
        return processed_results
    
    def scrape_multiple_sync(
        self, 
        urls: List[str], 
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> List[ScrapingResult]:
        """同步介面的併發爬取"""
        try:
            # 嘗試獲取現有的事件循環
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已經在事件循環中，使用新的事件循環
                import threading
                import concurrent.futures
                
                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(
                            self.scrape_multiple(urls, progress_callback)
                        )
                    finally:
                        new_loop.close()
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_thread)
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.scrape_multiple(urls, progress_callback)
                )
        except RuntimeError:
            # 沒有事件循環，創建新的
            return asyncio.run(self.scrape_multiple(urls, progress_callback))
    
    def _update_stats(self, domain: str, success: bool, response_time: float, encoding: str = None):
        """更新統計資訊"""
        self.stats['total_requests'] += 1
        
        if success:
            self.stats['successful_requests'] += 1
        else:
            self.stats['failed_requests'] += 1
            
        self.stats['total_response_time'] += response_time
        
        # 域名統計
        if domain not in self.stats['requests_by_domain']:
            self.stats['requests_by_domain'][domain] = {'total': 0, 'success': 0}
        self.stats['requests_by_domain'][domain]['total'] += 1
        if success:
            self.stats['requests_by_domain'][domain]['success'] += 1
            
        # 編碼統計
        if encoding:
            if encoding not in self.stats['encoding_stats']:
                self.stats['encoding_stats'][encoding] = 0
            self.stats['encoding_stats'][encoding] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """獲取爬蟲統計資訊"""
        total_requests = self.stats['total_requests']
        
        avg_response_time = (
            self.stats['total_response_time'] / total_requests 
            if total_requests > 0 else 0
        )
        
        success_rate = (
            self.stats['successful_requests'] / total_requests * 100 
            if total_requests > 0 else 0
        )
        
        return {
            **self.stats,
            'success_rate': f"{success_rate:.1f}%",
            'average_response_time': f"{avg_response_time:.2f}s",
            'cache_hit_rate': f"{(self.stats['cache_hits'] / total_requests * 100):.1f}%" if total_requests > 0 else "0%",
            'encoding_detector_stats': self.encoding_detector.get_stats(),
            'rate_limiter_stats': self.rate_limiter.get_stats(),
            'cache_manager_stats': self.cache_manager.get_stats()
        }
    
    def clear_cache(self):
        """清空快取"""
        self.cache_manager.clear_cache()
        logger.info("🧹 已清空爬蟲快取")
    
    def reset_stats(self):
        """重置統計資訊"""
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'cache_hits': 0,
            'total_response_time': 0.0,
            'requests_by_domain': {},
            'encoding_stats': {}
        }
        logger.info("📊 已重置爬蟲統計資訊")


class BatchWebScraper:
    """批次網路爬蟲 - 針對大量URL的優化版本"""
    
    def __init__(self, config: ScrapingConfig = None, batch_size: int = 20):
        self.config = config or ScrapingConfig()
        self.batch_size = batch_size
        self.scraper = AsyncWebScraper(config)
        
    def scrape_in_batches(
        self, 
        urls: List[str], 
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> List[ScrapingResult]:
        """分批爬取大量URL"""
        
        if not urls:
            return []
            
        total_batches = (len(urls) + self.batch_size - 1) // self.batch_size
        all_results = []
        
        logger.info(f"📦 開始分批爬取 {len(urls)} 個URL，分為 {total_batches} 批")
        
        for i in range(0, len(urls), self.batch_size):
            batch_urls = urls[i:i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            
            if progress_callback:
                progress_callback(f"處理批次 {batch_num}/{total_batches} ({len(batch_urls)} 個URL)...")
            
            logger.info(f"📦 處理批次 {batch_num}/{total_batches}")
            
            # 爬取當前批次
            batch_results = self.scraper.scrape_multiple_sync(
                batch_urls, 
                progress_callback
            )
            all_results.extend(batch_results)
            
            # 批次間暫停
            if i + self.batch_size < len(urls):
                pause_time = 2.0  # 批次間暫停2秒
                logger.info(f"⏸️ 批次間暫停 {pause_time} 秒...")
                time.sleep(pause_time)
        
        successful = sum(1 for r in all_results if r.success)
        logger.info(f"🎉 所有批次完成: {successful}/{len(urls)} 成功")
        
        return all_results