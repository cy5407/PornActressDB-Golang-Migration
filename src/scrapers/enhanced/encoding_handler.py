# -*- coding: utf-8 -*-
"""
改進的編碼處理模組
用於解決網路爬蟲中的編碼問題
"""

import logging
import time
import random
from typing import Dict, Any, Optional, Tuple
import requests
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class EnhancedEncodingHandler:
    """增強的編碼處理器"""
    
    def __init__(self):
        # 編碼優先順序（基於測試結果）
        self.encoding_priority = [
            'cp932',      # 日文 Windows 編碼（測試中最佳）
            'shift_jis',  # 日文編碼
            'utf-8',      # 標準編碼
            'euc-jp',     # 日文 Unix 編碼
            'iso-2022-jp', # 日文 ISO 編碼
            'gb2312',     # 簡體中文
            'big5'        # 繁體中文
        ]
        
        # 改進的瀏覽器標頭
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ja,zh-TW,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Connection': 'keep-alive'
        }
    
    def smart_decode(self, content: bytes, url: str = "") -> Tuple[str, str]:
        """
        智慧解碼內容
        
        Args:
            content: 原始位元組內容
            url: 來源 URL（用於日誌）
            
        Returns:
            (decoded_content, best_encoding)
        """
        best_content = None
        best_encoding = 'utf-8'
        min_replacement_ratio = float('inf')
        
        for encoding in self.encoding_priority:
            try:
                decoded = content.decode(encoding, errors='replace')
                
                # 計算替換字符比例
                replacement_count = decoded.count('�')
                total_chars = len(decoded)
                replacement_ratio = replacement_count / total_chars if total_chars > 0 else 1.0
                
                logger.debug(f"[{url}] {encoding}: {replacement_count} 替換字符, 比例: {replacement_ratio:.3f}")
                
                # 如果替換字符比例很低，直接使用這個編碼
                if replacement_ratio < 0.01:  # 少於 1% 的替換字符
                    logger.info(f"[{url}] 找到完美編碼: {encoding}")
                    return decoded, encoding
                
                # 記錄最佳編碼
                if replacement_ratio < min_replacement_ratio:
                    min_replacement_ratio = replacement_ratio
                    best_content = decoded
                    best_encoding = encoding
                    
            except Exception as e:
                logger.warning(f"[{url}] {encoding} 解碼失敗: {e}")
                continue
        
        if best_content is None:
            # 回退到 UTF-8
            logger.warning(f"[{url}] 所有編碼都失敗，回退到 UTF-8")
            best_content = content.decode('utf-8', errors='replace')
            best_encoding = 'utf-8'
        else:
            logger.info(f"[{url}] 使用最佳編碼: {best_encoding} (替換比例: {min_replacement_ratio:.3f})")
        
        return best_content, best_encoding
    
    def validate_content(self, content: str, url: str = "") -> bool:
        """
        驗證內容是否有意義
        
        Args:
            content: 解碼後的內容
            url: 來源 URL
            
        Returns:
            是否為有效內容
        """
        if not content or len(content.strip()) < 100:
            return False
        
        # 檢查替換字符比例
        replacement_ratio = content.count('�') / len(content)
        if replacement_ratio > 0.3:  # 超過 30% 的替換字符
            logger.warning(f"[{url}] 內容包含過多替換字符: {replacement_ratio:.1%}")
            return False
        
        # 使用 BeautifulSoup 檢查是否為有效 HTML
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # 檢查是否有標題
            title = soup.title
            if title and title.string and title.string.strip():
                logger.debug(f"[{url}] 找到頁面標題: {title.string.strip()[:50]}")
                return True
            
            # 檢查是否有有意義的文字內容
            text_content = soup.get_text(strip=True)
            if len(text_content) > 200:
                logger.debug(f"[{url}] 找到文字內容: {len(text_content)} 字符")
                return True
                
        except Exception as e:
            logger.warning(f"[{url}] HTML 解析失敗: {e}")
        
        return False

class RateLimitedRequester:
    """頻率限制的請求器"""
    
    def __init__(self, min_delay: float = 1.0, max_delay: float = 3.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.last_request_time = 0
    
    def _wait_if_needed(self):
        """如果需要，等待一段時間"""
        now = time.time()
        elapsed = now - self.last_request_time
        
        if elapsed < self.min_delay:
            sleep_time = random.uniform(self.min_delay - elapsed, self.max_delay)
            logger.debug(f"等待 {sleep_time:.2f} 秒")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def get(self, url: str, headers: Dict[str, str], timeout: int = 15) -> requests.Response:
        """執行 GET 請求"""
        self._wait_if_needed()
        
        try:
            session = requests.Session()
            session.headers.update(headers)
            
            logger.debug(f"請求 URL: {url}")
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            
            logger.info(f"成功獲取 {url}: {response.status_code}, {len(response.content)} bytes")
            return response
            
        except requests.exceptions.RequestException as e:
            logger.error(f"請求失敗 {url}: {e}")
            raise

class ImprovedScraper:
    """改進的爬蟲"""
    
    def __init__(self, min_delay: float = 1.0, max_delay: float = 3.0):
        self.encoding_handler = EnhancedEncodingHandler()
        self.requester = RateLimitedRequester(min_delay, max_delay)
        self.headers = self.encoding_handler.headers.copy()
    
    def scrape(self, url: str, validate_content: bool = True) -> Optional[Dict[str, Any]]:
        """
        爬取網頁內容
        
        Args:
            url: 目標 URL
            validate_content: 是否驗證內容有效性
            
        Returns:
            包含內容和元資料的字典，失敗時返回 None
        """
        try:
            # 發送請求
            response = self.requester.get(url, self.headers)
            
            # 智慧解碼
            content, encoding = self.encoding_handler.smart_decode(response.content, url)
            
            # 驗證內容（如果啟用）
            if validate_content and not self.encoding_handler.validate_content(content, url):
                logger.warning(f"[{url}] 內容驗證失敗")
                return None
            
            # 解析 HTML
            soup = BeautifulSoup(content, 'html.parser')
            
            return {
                'url': url,
                'status_code': response.status_code,
                'encoding': encoding,
                'content': content,
                'soup': soup,
                'title': soup.title.string if soup.title else None,
                'content_length': len(content),
                'replacement_chars': content.count('�'),
                'headers': dict(response.headers)
            }
            
        except Exception as e:
            logger.error(f"爬取失敗 {url}: {e}")
            return None
    
    def extract_video_info(self, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        從爬取結果中提取影片資訊
        
        Args:
            result: scrape() 方法的返回結果
            
        Returns:
            提取的影片資訊或 None
        """
        if not result or not result.get('soup'):
            return None
        
        soup = result['soup']
        url = result['url']
        
        # 基本資訊提取邏輯
        info = {
            'title': result.get('title', ''),
            'actresses': [],
            'studio': '',
            'code': '',
            'source_url': url
        }
        
        try:
            # 這裡可以添加特定網站的解析邏輯
            if 'av-wiki.net' in url:
                info.update(self._extract_avwiki_info(soup))
            elif 'chiba-f.net' in url:
                info.update(self._extract_chibaf_info(soup))
            
            return info if any(info.values()) else None
            
        except Exception as e:
            logger.error(f"資訊提取失敗 {url}: {e}")
            return None
    
    def _extract_avwiki_info(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """提取 av-wiki.net 的資訊"""
        # TODO: 根據網站實際結構實作
        return {}
    
    def _extract_chibaf_info(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """提取 chiba-f.net 的資訊"""
        # TODO: 根據網站實際結構實作
        return {}

# 使用範例
if __name__ == "__main__":
    # 設定日誌
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 建立改進的爬蟲
    scraper = ImprovedScraper(min_delay=2.0, max_delay=4.0)
    
    # 測試 URL
    test_urls = [
        'https://av-wiki.net/?s=MIDV-661&post_type=product',
        'https://chiba-f.net/search/?keyword=MIDV-661'
    ]
    
    for url in test_urls:
        logger.info(f"測試爬取: {url}")
        result = scraper.scrape(url)
        
        if result:
            logger.info(f"成功: 編碼={result['encoding']}, 內容長度={result['content_length']}, 替換字符={result['replacement_chars']}")
        else:
            logger.error(f"失敗: {url}")
        
        print("-" * 50)
