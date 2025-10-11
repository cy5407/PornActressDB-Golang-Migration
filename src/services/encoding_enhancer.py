# -*- coding: utf-8 -*-
"""
編碼處理增強模組 - 整合到現有搜尋器的編碼解決方案
"""

import logging
from typing import Tuple, Optional
from bs4 import BeautifulSoup
import httpx

logger = logging.getLogger(__name__)

class EncodingEnhancer:
    """編碼增強器 - 專為現有搜尋器設計"""
    
    def __init__(self):
        # 基於測試結果的編碼優先順序
        self.encoding_priority = [
            'cp932',      # 日文 Windows 編碼（測試中最佳）
            'shift_jis',  # 日文編碼
            'utf-8',      # 標準編碼
            'euc-jp',     # 日文 Unix 編碼
        ]
    
    def smart_decode_response(self, response: httpx.Response, url: str = "") -> Tuple[str, str]:
        """
        智慧解碼 HTTP 回應內容
        
        Args:
            response: httpx.Response 物件
            url: 來源 URL（用於日誌）
            
        Returns:
            (decoded_content, best_encoding)
        """
        content_bytes = response.content
        
        if not content_bytes:
            return "", "utf-8"
        
        # 嘗試各種編碼
        best_content = None
        best_encoding = 'utf-8'
        min_replacement_ratio = float('inf')
        
        for encoding in self.encoding_priority:
            try:
                decoded = content_bytes.decode(encoding, errors='replace')
                
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
            best_content = content_bytes.decode('utf-8', errors='replace')
            best_encoding = 'utf-8'
        else:
            logger.info(f"[{url}] 使用最佳編碼: {best_encoding} (替換比例: {min_replacement_ratio:.3f})")
        
        return best_content, best_encoding
    
    def create_enhanced_soup(self, response: httpx.Response, url: str = "") -> Optional[BeautifulSoup]:
        """
        建立增強的 BeautifulSoup 物件，包含編碼處理
        
        Args:
            response: httpx.Response 物件
            url: 來源 URL
            
        Returns:
            BeautifulSoup 物件或 None
        """
        try:
            # 智慧解碼內容
            content, encoding = self.smart_decode_response(response, url)
            
            # 驗證內容品質
            if not self._validate_content(content, url):
                return None
            
            # 建立 BeautifulSoup 物件
            soup = BeautifulSoup(content, 'html.parser')
            
            # 在 soup 物件上添加編碼資訊（可選）
            soup._encoding_info = {
                'used_encoding': encoding,
                'content_length': len(content),
                'replacement_chars': content.count('�')
            }
            
            return soup
            
        except Exception as e:
            logger.error(f"[{url}] 建立 BeautifulSoup 失敗: {e}")
            return None
    
    def _validate_content(self, content: str, url: str = "") -> bool:
        """驗證解碼內容的品質"""
        if not content or len(content.strip()) < 100:
            logger.warning(f"[{url}] 內容太短或為空")
            return False
        
        # 檢查替換字符比例
        replacement_ratio = content.count('�') / len(content)
        if replacement_ratio > 0.3:  # 超過 30% 的替換字符
            logger.warning(f"[{url}] 內容包含過多替換字符: {replacement_ratio:.1%}")
            return False
        
        return True

# 全域編碼增強器實例
encoding_enhancer = EncodingEnhancer()

def create_enhanced_soup(response: httpx.Response, url: str = "") -> Optional[BeautifulSoup]:
    """
    便捷函式：建立編碼增強的 BeautifulSoup 物件
    
    使用方式：
    # 原本的程式碼
    soup = BeautifulSoup(response.content, "html.parser")
    
    # 改為
    soup = create_enhanced_soup(response, url)
    """
    return encoding_enhancer.create_enhanced_soup(response, url)

def smart_decode_response(response: httpx.Response, url: str = "") -> Tuple[str, str]:
    """
    便捷函式：智慧解碼 HTTP 回應
    
    Returns:
        (decoded_content, encoding_used)
    """
    return encoding_enhancer.smart_decode_response(response, url)
