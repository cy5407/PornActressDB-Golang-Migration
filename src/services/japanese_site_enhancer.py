# -*- coding: utf-8 -*-
"""
日文網站編碼增強器 - 專門處理 av-wiki.net 和 chiba-f.net
修正版本，針對不同網站使用適當的編碼策略
"""

import logging
from typing import Tuple, Optional
from bs4 import BeautifulSoup
import httpx

logger = logging.getLogger(__name__)

class JapaneseSiteEnhancer:
    """日文網站編碼增強器 - 專為 av-wiki.net 和 chiba-f.net 設計"""
    
    def __init__(self):
        # 支援的日文網站
        self.supported_domains = [
            'av-wiki.net',
            'chiba-f.net'
        ]
    
    def _get_encoding_priority(self, url: str):
        """根據網站選擇適當的編碼優先順序"""
        if 'chiba-f.net' in url:
            # chiba-f.net 使用 UTF-8 編碼
            return ['utf-8', 'cp932', 'shift_jis', 'euc-jp']
        elif 'av-wiki.net' in url:
            # av-wiki.net 實際使用 UTF-8 編碼（根據實際測試結果調整）
            return ['utf-8', 'cp932', 'shift_jis', 'euc-jp']
        else:
            # 其他日文網站的預設編碼順序
            return ['cp932', 'shift_jis', 'utf-8', 'euc-jp', 'iso-2022-jp']
    
    def is_japanese_site(self, url: str) -> bool:
        """檢查是否為支援的日文網站"""
        return any(domain in url for domain in self.supported_domains)
    
    def create_enhanced_soup(self, response: httpx.Response, url: str = "") -> BeautifulSoup:
        """
        為日文網站創建經過編碼優化的 BeautifulSoup 物件
        
        Args:
            response: httpx.Response 物件
            url: 來源 URL
            
        Returns:
            BeautifulSoup 物件
        """
        if not self.is_japanese_site(url):
            # 如果不是日文網站，使用標準處理
            return BeautifulSoup(response.content, "html.parser")
        
        content_bytes = response.content
        if not content_bytes:
            return BeautifulSoup("", "html.parser")
        
        best_soup = None
        best_encoding = 'utf-8'
        min_replacement_ratio = float('inf')
        
        # 根據 URL 選擇適當的編碼優先順序
        encoding_priority = self._get_encoding_priority(url)
        
        for encoding in encoding_priority:
            try:
                decoded = content_bytes.decode(encoding, errors='replace')
                
                # 計算替換字符比例
                replacement_count = decoded.count('\ufffd')
                replacement_ratio = replacement_count / len(decoded) if decoded else 1.0
                
                # 改進的編碼品質檢測
                # 檢查是否包含可讀的HTML標籤和常見日文字符
                html_quality = 0
                if '<html' in decoded.lower() and '</html>' in decoded.lower():
                    html_quality += 1
                if '<div' in decoded.lower() and '<li' in decoded.lower():
                    html_quality += 1
                # 檢查日文字符
                import re
                if re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', decoded):
                    html_quality += 2
                
                # 如果這個編碼提供了更好的HTML結構或更少的替換字符
                quality_score = html_quality - replacement_ratio
                current_best_score = (2 if best_soup and best_soup.find() else 0) - min_replacement_ratio
                
                if quality_score > current_best_score or replacement_ratio < min_replacement_ratio:
                    min_replacement_ratio = replacement_ratio
                    best_encoding = encoding
                    best_soup = BeautifulSoup(decoded, "html.parser")
                    
                    # 如果HTML品質很好且替換字符很少，就使用這個編碼
                    if html_quality >= 3 and replacement_ratio < 0.02:  # 2% 以下
                        break
                        
            except (UnicodeDecodeError, LookupError) as e:
                logger.debug(f"編碼 {encoding} 解碼失敗: {e}")
                continue
        
        if best_soup is None:
            # 如果所有編碼都失敗，使用標準處理
            logger.warning(f"所有編碼嘗試都失敗，使用標準處理: {url}")
            return BeautifulSoup(response.content, "html.parser")
        
        logger.info(f"[{url}] 日文網站使用最佳編碼: {best_encoding} (替換比例: {min_replacement_ratio:.3f})")
        return best_soup
    
    def smart_decode_response(self, response: httpx.Response, url: str = "") -> Tuple[str, str]:
        """
        智慧解碼日文網站的 HTTP 回應內容
        
        Args:
            response: httpx.Response 物件
            url: 來源 URL
            
        Returns:
            (decoded_content, best_encoding)
        """
        if not self.is_japanese_site(url):
            # 如果不是日文網站，使用標準處理
            return response.text, response.encoding or 'utf-8'
        
        content_bytes = response.content
        if not content_bytes:
            return "", "utf-8"
        
        best_content = ""
        best_encoding = 'utf-8'
        min_replacement_ratio = float('inf')
        
        # 根據 URL 選擇適當的編碼優先順序
        encoding_priority = self._get_encoding_priority(url)
        
        for encoding in encoding_priority:
            try:
                decoded = content_bytes.decode(encoding, errors='replace')
                
                # 計算替換字符比例
                replacement_count = decoded.count('\ufffd')
                replacement_ratio = replacement_count / len(decoded) if decoded else 1.0
                
                # 改進的編碼品質檢測 (同樣的邏輯)
                html_quality = 0
                if '<html' in decoded.lower() and '</html>' in decoded.lower():
                    html_quality += 1
                if '<div' in decoded.lower() and '<li' in decoded.lower():
                    html_quality += 1
                # 檢查日文字符
                import re
                if re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', decoded):
                    html_quality += 2
                
                # 綜合品質評分
                quality_score = html_quality - replacement_ratio
                current_best_score = (2 if best_content and '<html' in best_content.lower() else 0) - min_replacement_ratio
                
                if quality_score > current_best_score or replacement_ratio < min_replacement_ratio:
                    min_replacement_ratio = replacement_ratio
                    best_encoding = encoding
                    best_content = decoded
                    
                    # 如果HTML品質很好且替換字符很少，就使用這個編碼
                    if html_quality >= 3 and replacement_ratio < 0.02:  # 2% 以下
                        break
                        
            except (UnicodeDecodeError, LookupError) as e:
                logger.debug(f"編碼 {encoding} 解碼失敗: {e}")
                continue
        
        if not best_content:
            # 如果所有編碼都失敗，使用標準處理
            logger.warning(f"所有編碼嘗試都失敗，使用標準處理: {url}")
            return response.text, response.encoding or 'utf-8'
        
        logger.info(f"[{url}] 日文網站使用最佳編碼: {best_encoding} (替換比例: {min_replacement_ratio:.3f})")
        return best_content, best_encoding


def create_japanese_soup(url: str, timeout: int = 10, max_retries: int = 3) -> Optional[BeautifulSoup]:
    """
    為日文網站建立 BeautifulSoup 物件，智慧處理編碼問題
    這是獨立函式版本，向後相容原有程式碼
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    enhancer = JapaneseSiteEnhancer()
    
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=timeout, headers=headers) as client:
                response = client.get(url)
                response.raise_for_status()
                
                # 使用增強器建立 soup
                soup = enhancer.create_enhanced_soup(response, url)
                
                # 驗證解析結果
                if soup and soup.find():
                    logger.info(f"成功取得日文網站內容: {url}")
                    return soup
                else:
                    logger.warning(f"取得的內容可能為空或無效: {url}")
                    
        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP 錯誤 (嘗試 {attempt + 1}/{max_retries}): {e.response.status_code} - {url}")
            if e.response.status_code in [404, 403]:
                break
        except httpx.RequestError as e:
            logger.warning(f"請求錯誤 (嘗試 {attempt + 1}/{max_retries}): {e} - {url}")
        except Exception as e:
            logger.error(f"未預期錯誤 (嘗試 {attempt + 1}/{max_retries}): {e} - {url}")
            
        if attempt < max_retries - 1:
            logger.info(f"等待 2 秒後重試...")
            import time
            time.sleep(2)
    
    logger.error(f"經過 {max_retries} 次嘗試後仍無法取得內容: {url}")
    return None
