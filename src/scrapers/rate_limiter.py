# -*- coding: utf-8 -*-
"""
請求頻率控制模組
智慧頻率限制，防止被網站封鎖
"""

import asyncio
import time
import logging
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from urllib.parse import urlparse
import random

logger = logging.getLogger(__name__)


@dataclass
class DomainConfig:
    """域名配置類"""
    requests_per_minute: int = 15           # 每分鐘請求數
    requests_per_hour: int = 600            # 每小時請求數  
    burst_limit: int = 5                    # 突發請求限制
    min_interval: float = 1.0               # 最小請求間隔(秒)
    max_interval: float = 3.0               # 最大請求間隔(秒)
    backoff_factor: float = 1.5             # 退避因子
    respect_retry_after: bool = True        # 遵守Retry-After標頭
    adaptive_delay: bool = True             # 自適應延遲


@dataclass 
class RequestRecord:
    """請求記錄"""
    timestamp: float
    success: bool
    response_time: float
    status_code: Optional[int] = None


class DomainLimiter:
    """單域名限流器"""
    
    def __init__(self, domain: str, config: DomainConfig):
        self.domain = domain
        self.config = config
        
        # 請求記錄
        self.minute_requests: deque = deque()  # 最近一分鐘的請求
        self.hour_requests: deque = deque()    # 最近一小時的請求
        self.request_history: List[RequestRecord] = []
        
        # 狀態追蹤
        self.last_request_time = 0.0
        self.consecutive_failures = 0
        self.retry_after_until = 0.0  # Retry-After 直到這個時間
        self.current_delay = config.min_interval
        
        # 鎖
        self.lock = threading.RLock()
        
        # 統計
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'blocked_requests': 0,
            'total_wait_time': 0.0,
            'average_response_time': 0.0
        }
    
    def _cleanup_old_records(self, current_time: float):
        """清理過期的請求記錄"""
        # 清理一分鐘外的記錄
        while self.minute_requests and current_time - self.minute_requests[0] > 60:
            self.minute_requests.popleft()
        
        # 清理一小時外的記錄
        while self.hour_requests and current_time - self.hour_requests[0] > 3600:
            self.hour_requests.popleft()
        
        # 保留最近的請求歷史（最多1000條）
        if len(self.request_history) > 1000:
            self.request_history = self.request_history[-1000:]
    
    def _calculate_adaptive_delay(self) -> float:
        """計算自適應延遲"""
        if not self.config.adaptive_delay or len(self.request_history) < 5:
            return self.current_delay
        
        # 分析最近的請求模式
        recent_requests = self.request_history[-10:]
        failure_rate = sum(1 for r in recent_requests if not r.success) / len(recent_requests)
        avg_response_time = sum(r.response_time for r in recent_requests) / len(recent_requests)
        
        # 根據失敗率和響應時間調整延遲
        if failure_rate > 0.3:  # 30%以上失敗率
            self.current_delay = min(self.current_delay * self.config.backoff_factor, self.config.max_interval * 2)
        elif failure_rate < 0.1 and avg_response_time < 2.0:  # 低失敗率且響應快
            self.current_delay = max(self.current_delay * 0.9, self.config.min_interval)
        
        # 添加隨機化避免同步
        jitter = random.uniform(0.8, 1.2)
        return self.current_delay * jitter
    
    def can_make_request(self) -> Tuple[bool, float]:
        """
        檢查是否可以發送請求
        
        Returns:
            Tuple[bool, float]: (是否可以請求, 需要等待的時間)
        """
        with self.lock:
            current_time = time.time()
            self._cleanup_old_records(current_time)
            
            # 檢查 Retry-After
            if current_time < self.retry_after_until:
                wait_time = self.retry_after_until - current_time
                return False, wait_time
            
            # 檢查每分鐘限制
            if len(self.minute_requests) >= self.config.requests_per_minute:
                oldest_minute_request = self.minute_requests[0]
                wait_time = 60 - (current_time - oldest_minute_request)
                return False, max(wait_time, 0)
            
            # 檢查每小時限制
            if len(self.hour_requests) >= self.config.requests_per_hour:
                oldest_hour_request = self.hour_requests[0]
                wait_time = 3600 - (current_time - oldest_hour_request)
                return False, max(wait_time, 0)
            
            # 檢查最小間隔
            time_since_last = current_time - self.last_request_time
            adaptive_delay = self._calculate_adaptive_delay()
            
            if time_since_last < adaptive_delay:
                wait_time = adaptive_delay - time_since_last
                return False, wait_time
            
            return True, 0.0
    
    def record_request(self, success: bool, response_time: float, status_code: Optional[int] = None, retry_after: Optional[int] = None):
        """記錄請求結果"""
        with self.lock:
            current_time = time.time()
            
            # 記錄請求時間
            self.minute_requests.append(current_time)
            self.hour_requests.append(current_time)
            self.last_request_time = current_time
            
            # 記錄詳細信息
            record = RequestRecord(
                timestamp=current_time,
                success=success,
                response_time=response_time,
                status_code=status_code
            )
            self.request_history.append(record)
            
            # 更新統計
            self.stats['total_requests'] += 1
            if success:
                self.stats['successful_requests'] += 1
                self.consecutive_failures = 0
            else:
                self.stats['failed_requests'] += 1
                self.consecutive_failures += 1
            
            # 處理 Retry-After
            if retry_after and self.config.respect_retry_after:
                self.retry_after_until = current_time + retry_after
                logger.info(f"🚫 {self.domain} 設置 Retry-After: {retry_after}秒")
            
            # 根據連續失敗調整策略
            if self.consecutive_failures >= 3:
                self.current_delay = min(
                    self.config.min_interval * (2 ** min(self.consecutive_failures - 2, 3)),
                    self.config.max_interval * 2
                )
                logger.warning(f"⚠️ {self.domain} 連續失敗 {self.consecutive_failures} 次，調整延遲至 {self.current_delay:.2f}秒")
    
    def get_stats(self) -> Dict:
        """獲取統計資訊"""
        with self.lock:
            current_time = time.time()
            self._cleanup_old_records(current_time)
            
            total_requests = self.stats['total_requests']
            success_rate = (self.stats['successful_requests'] / total_requests * 100) if total_requests > 0 else 0
            
            # 計算平均響應時間
            if self.request_history:
                avg_response_time = sum(r.response_time for r in self.request_history) / len(self.request_history)
            else:
                avg_response_time = 0.0
            
            return {
                **self.stats,
                'success_rate': f"{success_rate:.1f}%",
                'average_response_time': f"{avg_response_time:.2f}s",
                'current_delay': f"{self.current_delay:.2f}s",
                'consecutive_failures': self.consecutive_failures,
                'minute_requests_count': len(self.minute_requests),
                'hour_requests_count': len(self.hour_requests),
                'is_retry_after_active': current_time < self.retry_after_until,
                'retry_after_remaining': max(0, self.retry_after_until - current_time)
            }


class RateLimiter:
    """多域名頻率限制器"""
    
    def __init__(self):
        self.domain_limiters: Dict[str, DomainLimiter] = {}
        self.default_config = DomainConfig()
        self.lock = threading.RLock()
        
        # 預設域名配置
        self.domain_configs = {
            'av-wiki.net': DomainConfig(
                requests_per_minute=10,
                requests_per_hour=300,
                burst_limit=3,
                min_interval=2.0,
                max_interval=5.0
            ),
            'javdb.com': DomainConfig(
                requests_per_minute=20,
                requests_per_hour=800,
                burst_limit=5,
                min_interval=1.0,
                max_interval=3.0
            ),
            'chiba-f.net': DomainConfig(
                requests_per_minute=15,
                requests_per_hour=500,
                burst_limit=4,
                min_interval=1.5,
                max_interval=4.0
            )
        }
        
        logger.info("🚦 頻率限制器已初始化")
    
    def _get_domain_limiter(self, domain: str) -> DomainLimiter:
        """獲取域名限流器"""
        with self.lock:
            if domain not in self.domain_limiters:
                config = self.domain_configs.get(domain, self.default_config)
                self.domain_limiters[domain] = DomainLimiter(domain, config)
                logger.debug(f"📋 為域名 {domain} 創建限流器")
            return self.domain_limiters[domain]
    
    def _extract_domain(self, url: str) -> str:
        """從URL提取域名"""
        try:
            return urlparse(url).netloc.lower()
        except:
            return 'unknown'
    
    def can_make_request(self, url: str) -> Tuple[bool, float]:
        """檢查是否可以發送請求"""
        domain = self._extract_domain(url)
        limiter = self._get_domain_limiter(domain)
        return limiter.can_make_request()
    
    def wait_if_needed(self, url: str) -> float:
        """如需要則等待（同步版本）"""
        can_request, wait_time = self.can_make_request(url)
        
        if not can_request and wait_time > 0:
            domain = self._extract_domain(url)
            logger.info(f"⏱️ 域名 {domain} 需要等待 {wait_time:.2f} 秒")
            time.sleep(wait_time)
            return wait_time
        
        return 0.0
    
    async def wait_if_needed_async(self, url: str) -> float:
        """如需要則等待（非同步版本）"""
        can_request, wait_time = self.can_make_request(url)
        
        if not can_request and wait_time > 0:
            domain = self._extract_domain(url)
            logger.info(f"⏱️ 域名 {domain} 需要等待 {wait_time:.2f} 秒")
            await asyncio.sleep(wait_time)
            return wait_time
        
        return 0.0
    
    def record_request(self, url: str, success: bool, response_time: float, status_code: Optional[int] = None, retry_after: Optional[int] = None):
        """記錄請求結果"""
        domain = self._extract_domain(url)
        limiter = self._get_domain_limiter(domain)
        limiter.record_request(success, response_time, status_code, retry_after)
    
    def add_domain_config(self, domain: str, config: DomainConfig):
        """新增域名配置"""
        with self.lock:
            self.domain_configs[domain] = config
            # 如果已有限流器，更新配置
            if domain in self.domain_limiters:
                self.domain_limiters[domain].config = config
        logger.info(f"⚙️ 已更新域名 {domain} 的配置")
    
    def get_domain_stats(self, domain: str) -> Optional[Dict]:
        """獲取特定域名的統計"""
        if domain in self.domain_limiters:
            return self.domain_limiters[domain].get_stats()
        return None
    
    def get_stats(self) -> Dict:
        """獲取所有統計資訊"""
        with self.lock:
            domain_stats = {}
            total_stats = {
                'total_requests': 0,
                'successful_requests': 0,
                'failed_requests': 0,
                'blocked_requests': 0
            }
            
            for domain, limiter in self.domain_limiters.items():
                stats = limiter.get_stats()
                domain_stats[domain] = stats
                
                # 累加總統計
                for key in total_stats:
                    if key in stats:
                        total_stats[key] += stats[key]
            
            # 計算總成功率
            total_requests = total_stats['total_requests']
            success_rate = (
                total_stats['successful_requests'] / total_requests * 100
                if total_requests > 0 else 0
            )
            
            return {
                'total_stats': {
                    **total_stats,
                    'success_rate': f"{success_rate:.1f}%"
                },
                'domain_stats': domain_stats,
                'active_domains': list(self.domain_limiters.keys()),
                'configured_domains': list(self.domain_configs.keys())
            }
    
    def reset_domain(self, domain: str):
        """重置特定域名的限流器"""
        with self.lock:
            if domain in self.domain_limiters:
                del self.domain_limiters[domain]
                logger.info(f"🔄 已重置域名 {domain} 的限流器")
    
    def reset_all(self):
        """重置所有限流器"""
        with self.lock:
            self.domain_limiters.clear()
            logger.info("🔄 已重置所有限流器")


# 全局限流器實例
_global_rate_limiter = None

def get_global_rate_limiter() -> RateLimiter:
    """獲取全局限流器實例"""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter()
    return _global_rate_limiter


# 便利裝飾器
def rate_limited(url_param: str = 'url'):
    """頻率限制裝飾器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # 從參數中提取URL
            url = kwargs.get(url_param)
            if not url and len(args) > 0:
                url = args[0] if url_param == 'url' else None
            
            if url:
                limiter = get_global_rate_limiter()
                limiter.wait_if_needed(url)
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def async_rate_limited(url_param: str = 'url'):
    """非同步頻率限制裝飾器"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 從參數中提取URL
            url = kwargs.get(url_param)
            if not url and len(args) > 0:
                url = args[0] if url_param == 'url' else None
            
            if url:
                limiter = get_global_rate_limiter()
                await limiter.wait_if_needed_async(url)
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator