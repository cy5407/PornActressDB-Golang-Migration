# -*- coding: utf-8 -*-
"""
网络爬虫模块
优化的网络爬虫架构，包含多编码检测、异步处理和智能缓存
"""

__version__ = "2.0.0"
__author__ = "女優分類系統開發團隊"

from .encoding_utils import EncodingDetector, safe_decode_content
from .async_scraper import AsyncWebScraper
from .cache_manager import CacheManager
from .rate_limiter import RateLimiter

__all__ = [
    'EncodingDetector',
    'safe_decode_content', 
    'AsyncWebScraper',
    'CacheManager',
    'RateLimiter'
]