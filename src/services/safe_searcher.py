# -*- coding: utf-8 -*-
"""
安全搜尋器模組 - 防止被網站封鎖的網路搜尋增強功能
"""
import time
import random
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from pathlib import Path
import json
import threading
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class RequestConfig:
    """請求配置類"""
    min_interval: float = 1.0  # 最小請求間隔(秒)
    max_interval: float = 3.0  # 最大請求間隔(秒)
    enable_cache: bool = True  # 啟用快取
    cache_duration: int = 86400  # 快取持續時間(秒, 預設24小時)
    max_retries: int = 3  # 最大重試次數
    backoff_factor: float = 2.0  # 指數退避因子
    rotate_headers: bool = True  # 輪替請求標頭


@dataclass 
class CacheEntry:
    """快取項目"""
    data: Any
    timestamp: float
    url: str
    request_hash: str


class SafeSearcher:
    """安全搜尋器 - 防止IP被封鎖的智能搜尋器"""
    
    def __init__(self, config: RequestConfig = None, cache_file: str = None):
        self.config = config or RequestConfig()
        self.last_request_time = 0.0
        self._request_lock = threading.Lock()
        
        # 初始化快取系統
        self.cache_file = cache_file or str(Path(__file__).parent.parent.parent / 'cache' / 'search_cache.json')
        self.cache: Dict[str, CacheEntry] = {}
        self._load_cache()
        
        # 初始化瀏覽器標頭池
        self.browser_headers = self._init_browser_headers()
        self.current_header_index = 0
        
        logger.info(f"🛡️ 安全搜尋器已啟動 - 間隔: {self.config.min_interval}-{self.config.max_interval}s")

    def _init_browser_headers(self) -> List[Dict[str, str]]:
        """初始化真實瀏覽器標頭池"""
        return [
            {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8,ja;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"'
            },
            {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-TW,zh;q=0.8,en-US;q=0.5,en;q=0.3',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none'
            },
            {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"macOS"'
            },
            {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Linux"'
            },
            {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Microsoft Edge";v="120"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"'
            }
        ]

    def get_headers(self) -> Dict[str, str]:
        """獲取當前請求標頭"""
        if not self.config.rotate_headers:
            return self.browser_headers[0]
            
        # 輪替標頭
        headers = self.browser_headers[self.current_header_index].copy()
        self.current_header_index = (self.current_header_index + 1) % len(self.browser_headers)
        
        # 隨機化部分標頭
        headers['Cache-Control'] = random.choice(['no-cache', 'max-age=0', 'no-store'])
        
        return headers

    def _wait_for_next_request(self):
        """智能請求間隔控制"""
        with self._request_lock:
            current_time = time.time()
            elapsed = current_time - self.last_request_time
            
            # 計算隨機延遲
            min_wait = self.config.min_interval
            max_wait = self.config.max_interval
            wait_time = random.uniform(min_wait, max_wait)
            
            if elapsed < wait_time:
                sleep_time = wait_time - elapsed
                logger.debug(f"⏱️ 等待 {sleep_time:.2f} 秒後發送下一個請求...")
                time.sleep(sleep_time)
            
            self.last_request_time = time.time()

    def _generate_cache_key(self, url: str, params: dict = None) -> str:
        """生成快取鍵值"""
        cache_string = f"{url}_{str(params or {})}"
        return hashlib.md5(cache_string.encode('utf-8')).hexdigest()

    def _is_cache_valid(self, cache_entry: CacheEntry) -> bool:
        """檢查快取是否有效"""
        if not self.config.enable_cache:
            return False
            
        current_time = time.time()
        return (current_time - cache_entry.timestamp) < self.config.cache_duration

    def _load_cache(self):
        """載入快取資料"""
        if not self.config.enable_cache:
            return
            
        try:
            cache_path = Path(self.cache_file)
            if cache_path.exists():
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    
                # 轉換為 CacheEntry 物件
                for key, value in cache_data.items():
                    self.cache[key] = CacheEntry(**value)
                    
                # 清理過期快取
                self._cleanup_expired_cache()
                logger.info(f"📦 已載入 {len(self.cache)} 個快取項目")
        except Exception as e:
            logger.warning(f"載入快取失敗: {e}")
            self.cache = {}

    def _save_cache(self):
        """保存快取資料"""
        if not self.config.enable_cache:
            return
            
        try:
            cache_path = Path(self.cache_file)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 轉換為可序列化的格式，過濾掉 BeautifulSoup 物件
            from bs4 import BeautifulSoup
            cache_data = {}
            
            for key, entry in self.cache.items():
                # 檢查資料是否為 BeautifulSoup 物件
                if isinstance(entry.data, BeautifulSoup):
                    logger.debug(f"跳過 BeautifulSoup 物件快取: {entry.url}")
                    continue
                    
                try:
                    # 測試是否可序列化
                    json.dumps(entry.data, ensure_ascii=False)
                    cache_data[key] = asdict(entry)
                except (TypeError, ValueError):
                    logger.debug(f"跳過不可序列化資料: {entry.url}")
                    continue
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
                
            logger.debug(f"💾 已儲存 {len(cache_data)} 個快取項目 (跳過 {len(self.cache) - len(cache_data)} 個不可序列化項目)")
        except Exception as e:
            logger.warning(f"保存快取失敗: {e}")

    def _cleanup_expired_cache(self):
        """清理過期快取"""
        if not self.config.enable_cache:
            return
            
        expired_keys = []
        current_time = time.time()
        
        for key, entry in self.cache.items():
            if (current_time - entry.timestamp) >= self.config.cache_duration:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
            
        if expired_keys:
            logger.info(f"🧹 已清理 {len(expired_keys)} 個過期快取項目")

    def get_from_cache(self, url: str, params: dict = None) -> Optional[Any]:
        """從快取獲取資料"""
        if not self.config.enable_cache:
            return None
            
        cache_key = self._generate_cache_key(url, params)
        entry = self.cache.get(cache_key)
        
        if entry and self._is_cache_valid(entry):
            logger.debug(f"📋 從快取獲取: {url}")
            return entry.data
            
        return None

    def save_to_cache(self, url: str, data: Any, params: dict = None):
        """保存資料到快取"""
        if not self.config.enable_cache:
            return
            
        # 檢查資料是否可序列化
        try:
            # 嘗試序列化測試
            import json
            from bs4 import BeautifulSoup
            
            # 如果是 BeautifulSoup 物件，則不快取
            if isinstance(data, BeautifulSoup):
                logger.debug(f"🚫 BeautifulSoup 物件不可快取: {url}")
                return
            
            # 測試是否可以序列化為 JSON
            json.dumps(data, ensure_ascii=False)
            
        except (TypeError, ValueError) as e:
            logger.debug(f"🚫 資料不可序列化，跳過快取: {url} - {e}")
            return
            
        cache_key = self._generate_cache_key(url, params)
        entry = CacheEntry(
            data=data,
            timestamp=time.time(),
            url=url,
            request_hash=cache_key
        )
        
        self.cache[cache_key] = entry
        logger.debug(f"💾 已快取: {url}")

    def safe_request(self, request_func: Callable, url: str, *args, **kwargs) -> Optional[Any]:
        """安全請求包裝器 - 包含間隔控制、快取和重試機制"""
        
        # 檢查快取
        params = kwargs.get('params', {})
        cached_result = self.get_from_cache(url, params)
        if cached_result is not None:
            return cached_result
        
        # 控制請求間隔
        self._wait_for_next_request()
        
        # 設置請求標頭
        if 'headers' not in kwargs:
            kwargs['headers'] = self.get_headers()
        
        # 實施重試機制
        last_exception = None
        for attempt in range(self.config.max_retries + 1):
            try:
                logger.debug(f"🌐 發送請求 (嘗試 {attempt + 1}/{self.config.max_retries + 1}): {url}")
                
                result = request_func(url, *args, **kwargs)
                
                # 保存到快取
                if result is not None:
                    self.save_to_cache(url, result, params)
                    
                return result
                
            except Exception as e:
                last_exception = e
                logger.warning(f"⚠️ 請求失敗 (嘗試 {attempt + 1}): {e}")
                
                if attempt < self.config.max_retries:
                    # 指數退避延遲
                    wait_time = self.config.backoff_factor ** attempt
                    logger.info(f"⏳ 等待 {wait_time:.1f} 秒後重試...")
                    time.sleep(wait_time)
                    
                    # 輪替標頭
                    if self.config.rotate_headers:
                        kwargs['headers'] = self.get_headers()
        
        logger.error(f"❌ 所有重試都失敗了: {url}")
        if last_exception:
            raise last_exception
        
        return None

    def __del__(self):
        """析構函數 - 保存快取"""
        try:
            self._save_cache()
        except:
            pass

    def get_stats(self) -> Dict[str, Any]:
        """獲取統計資訊"""
        valid_cache_count = sum(1 for entry in self.cache.values() if self._is_cache_valid(entry))
        
        return {
            'config': asdict(self.config),
            'cache_stats': {
                'total_entries': len(self.cache),
                'valid_entries': valid_cache_count,
                'expired_entries': len(self.cache) - valid_cache_count,
                'cache_file': self.cache_file
            },
            'browser_headers_count': len(self.browser_headers),
            'current_header_index': self.current_header_index
        }

    def clear_cache(self):
        """清空快取"""
        self.cache.clear()
        try:
            cache_path = Path(self.cache_file)
            if cache_path.exists():
                cache_path.unlink()
            logger.info("🧹 已清空所有快取")
        except Exception as e:
            logger.warning(f"清空快取檔案失敗: {e}")

    def configure(self, **kwargs):
        """動態配置搜尋器"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info(f"⚙️ 已更新配置: {key} = {value}")
            else:
                logger.warning(f"未知配置項目: {key}")