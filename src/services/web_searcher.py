# -*- coding: utf-8 -*-
"""
網路搜尋器模組
"""
import re
import time
import logging
import threading
import concurrent.futures
import chardet
from typing import Dict, List, Optional
import httpx
from bs4 import BeautifulSoup
from urllib.parse import quote

import sys
from pathlib import Path

# 添加專案根目錄到系統路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.config import ConfigManager
from .safe_searcher import SafeSearcher, RequestConfig
from .safe_javdb_searcher import SafeJAVDBSearcher
# 移除不必要的 create_japanese_soup 匯入，直接使用 JapaneseSiteEnhancer 類別

logger = logging.getLogger(__name__)


class WebSearcher:
    """增強版搜尋器 - 支援搜尋結果頁面"""
    
    def __init__(self, config: ConfigManager):
        # 初始化安全搜尋器配置
        safe_config = RequestConfig(
            min_interval=config.getfloat('search', 'min_interval', fallback=1.0),
            max_interval=config.getfloat('search', 'max_interval', fallback=3.0),
            enable_cache=config.getboolean('search', 'enable_cache', fallback=True),
            cache_duration=config.getint('search', 'cache_duration', fallback=86400),
            max_retries=config.getint('search', 'max_retries', fallback=3),
            backoff_factor=config.getfloat('search', 'backoff_factor', fallback=2.0),
            rotate_headers=config.getboolean('search', 'rotate_headers', fallback=True)
        )
        
        # 初始化日文網站專用的更快速配置（av-wiki 和 chiba-f 比較不會擋爬蟲）
        japanese_config = RequestConfig(
            min_interval=config.getfloat('search', 'japanese_min_interval', fallback=0.5),
            max_interval=config.getfloat('search', 'japanese_max_interval', fallback=1.5),
            enable_cache=config.getboolean('search', 'enable_cache', fallback=True),
            cache_duration=config.getint('search', 'cache_duration', fallback=86400),
            max_retries=config.getint('search', 'max_retries', fallback=3),
            backoff_factor=config.getfloat('search', 'backoff_factor', fallback=1.5),
            rotate_headers=config.getboolean('search', 'rotate_headers', fallback=True)
        )
          # 初始化安全搜尋器
        self.safe_searcher = SafeSearcher(safe_config)
        
        # 為日文網站建立更快速的搜尋器（av-wiki 和 chiba-f 比較不會擋爬蟲）
        japanese_config = RequestConfig(
            min_interval=0.5,  # 日文網站較短延遲
            max_interval=1.5,
            enable_cache=True,
            cache_duration=86400,
            max_retries=3,
            backoff_factor=1.5,
            rotate_headers=True
        )
        self.japanese_searcher = SafeSearcher(japanese_config)
        self.japanese_searcher = SafeSearcher(japanese_config)  # 日文網站專用
        
        # 初始化 JAVDB 安全搜尋器
        cache_dir = config.get('search', 'cache_dir', fallback=None)
        self.javdb_searcher = SafeJAVDBSearcher(cache_dir)
          # 保留原有配置以向下相容
        self.headers = self.safe_searcher.get_headers()
        
        # 🔧 日文網站專用標頭（解決 Brotli 壓縮問題）
        self.japanese_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
            'Accept-Charset': 'UTF-8,Shift_JIS,EUC-JP,ISO-2022-JP,*;q=0.1',
            'Accept-Encoding': 'identity',  # 明確拒絕所有壓縮
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        self.search_cache = {}
        self.batch_size = config.getint('search', 'batch_size', fallback=10)
        self.thread_count = config.getint('search', 'thread_count', fallback=5)
        self.batch_delay = config.getfloat('search', 'batch_delay', fallback=2.0)
        self.timeout = config.getint('search', 'request_timeout', fallback=20)
        logger.info("🛡️ 已啟用安全搜尋器功能")
        logger.info("🇯🇵 已啟用日文網站快速搜尋功能")
        logger.info("🎬 已啟用 JAVDB 安全搜尋功能")

    def search_info(self, code: str, stop_event: threading.Event) -> Optional[Dict]:
        """多層級搜尋策略 - AV-WIKI -> chiba-f.net -> JAVDB"""
        if stop_event.is_set(): 
            return None
        if code in self.search_cache: 
            return self.search_cache[code]
        
        try:
            # 第一層：原有的 AV-WIKI 搜尋
            logger.debug(f"🔍 第一層搜尋 - AV-WIKI: {code}")
            result = self._search_av_wiki(code, stop_event)
            if result and result.get('actresses'):
                self.search_cache[code] = result
                return result
            
            # 第二層：chiba-f.net 搜尋  
            if not stop_event.is_set():
                logger.debug(f"🔍 第二層搜尋 - chiba-f.net: {code}")
                result = self._search_chiba_f_net(code, stop_event)
                if result and result.get('actresses'):
                    self.search_cache[code] = result
                    return result
            
            # 第三層：使用安全的 JAVDB 搜尋
            if not stop_event.is_set():
                logger.debug(f"🔍 第三層搜尋 - JAVDB: {code}")
                javdb_result = self.javdb_searcher.search_javdb(code)
                if javdb_result and javdb_result.get('actresses'):
                    # 轉換為統一格式
                    result = {
                        'source': javdb_result['source'],
                        'actresses': javdb_result['actresses'],
                        'studio': javdb_result.get('studio'),
                        'studio_code': javdb_result.get('studio_code'),
                        'release_date': javdb_result.get('release_date'),
                        'title': javdb_result.get('title'),
                        'duration': javdb_result.get('duration'),
                        'director': javdb_result.get('director'),
                        'series': javdb_result.get('series'),
                        'rating': javdb_result.get('rating'),
                        'categories': javdb_result.get('categories', [])
                    }
                    self.search_cache[code] = result
                    
                    # 豐富的日誌輸出
                    log_parts = [f"番號 {code} 透過 {result['source']} 找到:"]
                    log_parts.append(f"女優: {', '.join(result['actresses'])}")
                    log_parts.append(f"片商: {result.get('studio', '未知')}")
                    
                    if result.get('rating'):
                        log_parts.append(f"評分: {result['rating']}")
                    if result.get('categories'):
                        categories_str = ', '.join(result['categories'][:3])  # 只顯示前3個類別
                        if len(result['categories']) > 3:
                            categories_str += f" 等{len(result['categories'])}個類別"
                        log_parts.append(f"類別: {categories_str}")
                    
                    logger.info(" | ".join(log_parts))
                    return result
            
            logger.warning(f"番號 {code} 未在所有搜尋源中找到女優資訊。")
            return None            
        except Exception as e:
            logger.error(f"搜尋番號 {code} 時發生錯誤: {e}", exc_info=True)
            return None

    def _search_av_wiki(self, code: str, stop_event: threading.Event) -> Optional[Dict]:
        """AV-WIKI 搜尋方法"""
        if stop_event.is_set():
            return None
            
        search_url = f"https://av-wiki.net/?s={quote(code)}&post_type=product"
          # 使用日文網站專用標頭和增強編碼檢測
        def make_request(url, **kwargs):
            with httpx.Client(timeout=self.timeout, **kwargs) as client:
                # 🔧 使用不支援壓縮的標頭，避免 Brotli 問題
                response = client.get(url, headers=self.japanese_headers)
                response.raise_for_status()
                # 🔧 使用增強的編碼檢測機制
                decoded_content = self._detect_and_decode_content(response)
                logger.debug(f"📄 AV-WIKI 內容長度: {len(decoded_content)} 字符")
                logger.debug(f"📄 AV-WIKI 內容開頭: {decoded_content[:100]}...")
                return BeautifulSoup(decoded_content, 'html.parser')
        
        try:
            soup = self.safe_searcher.safe_request(make_request, search_url)
            
            if soup is None:
                logger.warning(f"無法獲取 {code} 的 AV-WIKI 搜尋頁面")
                return None
            
            # 先檢查是否有搜尋結果
            search_results = soup.find_all("div", class_="column-flex")
            logger.info(f"AV-WIKI 搜尋 {code}: 找到 {len(search_results)} 個搜尋結果")
            
            if not search_results:
                # 檢查是否是 "沒有找到結果" 的頁面
                no_results_indicators = ["該当なし", "見つかりませんでした", "検索結果：0", "0件"]
                page_text = soup.get_text()
                for indicator in no_results_indicators:
                    if indicator in page_text:
                        logger.info(f"AV-WIKI 明確顯示沒有找到 {code} 的結果")
                        return None
                        
            # 正確解析女優名稱：<li class="actress-name"><a>女優名稱</a></li>
            actress_elements = soup.find_all("li", class_="actress-name")
            actresses = []
            logger.info(f"AV-WIKI 解析: 找到 {len(actress_elements)} 個 actress-name 元素")
            for li in actress_elements:
                link = li.find("a")
                if link and link.text.strip():
                    actress_name = link.text.strip()
                    actresses.append(actress_name)
                    logger.info(f"AV-WIKI 提取到女優名稱: {actress_name}")
            
            if not actresses:
                logger.warning(f"AV-WIKI 未找到女優名稱，HTML開頭: {str(soup)[:200]}...")
            
            # 搜尋片商資訊
            studio_info = self._extract_studio_info(soup, code)
            
            if not actresses:
                page_text = soup.get_text()
                lines = [line.strip() for line in page_text.split('\n') if line.strip()]
                for i, line in enumerate(lines):
                    if code in line:
                        for j in range(max(0, i-3), min(len(lines), i+1)):
                            potential_name = lines[j].strip()
                            if potential_name and self._is_actress_name(potential_name):
                                if potential_name not in actresses: 
                                    actresses.append(potential_name)                
            if actresses:
                result = {
                    'source': 'AV-WIKI (安全增強版)', 
                    'actresses': actresses,
                    'studio': studio_info.get('studio'),
                    'studio_code': studio_info.get('studio_code'),
                    'release_date': studio_info.get('release_date')
                }
                logger.info(f"番號 {code} 透過 {result['source']} 找到: {', '.join(result['actresses'])}, 片商: {result.get('studio', '未知')}")
                return result

        except Exception as e:
            logger.error(f"AV-WIKI 搜尋 {code} 時發生錯誤: {e}", exc_info=True)
        
        return None

    def _is_actress_name(self, text: str) -> bool:
        """判斷文字是否可能是女優名稱"""
        if not text or len(text) < 2 or len(text) > 20: 
            return False
        exclude_keywords = [
            'SOD', 'STARS', 'FANZA', 'MGS', 'MIDV', 'SSIS', 'IPX', 'IPZZ', 
            '続きを読む', '検索', '件', '特典', '映像', '付き', 'star', 'SOKMIL', 
            'Menu', 'セール', '限定', '最大'
        ]
        if any(keyword in text for keyword in exclude_keywords): 
            return False
        if re.match(r'^\d+$', text) or len(re.findall(r'\d', text)) > len(text) // 2: 
            return False
        if re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', text): 
            return True
        return False
    
    def _detect_and_decode_content(self, response: httpx.Response) -> str:
        """多重編碼檢測和解碼機制（支援壓縮內容處理）"""
        content_bytes = response.content
        
        # 🔧 首先檢查是否為壓縮內容
        content_bytes = self._handle_compression(response, content_bytes)
        
        # 檢查內容是否看起來像二進制壓縮數據
        if self._is_likely_compressed(content_bytes):
            logger.warning("⚠️ 內容仍然看起來像壓縮數據，嘗試強制解壓")
            content_bytes = self._force_decompress(content_bytes)
        
        # 如果檢測到 brotli 但沒有庫，強制嘗試解壓
        content_encoding = response.headers.get('content-encoding', '').lower()
        if content_encoding == 'br' and len(content_bytes) > 0:
            logger.warning("⚠️ 服務器發送了 brotli 壓縮內容，嘗試強制解壓")
            content_bytes = self._force_decompress(content_bytes)
        
        # 優先順序：UTF-8 > Shift_JIS > EUC-JP > CP932 > 自動檢測
        encoding_attempts = ['utf-8', 'shift_jis', 'euc-jp', 'cp932', 'iso-2022-jp']
        
        # 如果 response 已經有編碼信息，優先嘗試
        if response.encoding and response.encoding.lower() not in [enc.lower() for enc in encoding_attempts]:
            encoding_attempts.insert(0, response.encoding.lower())
        
        # 嘗試每種編碼
        for encoding in encoding_attempts:
            try:
                decoded_text = content_bytes.decode(encoding)
                # 驗證解碼是否成功（檢查是否有明顯的亂碼）
                if self._is_valid_decoded_text(decoded_text):
                    logger.debug(f"✅ 成功使用編碼 {encoding} 解碼內容")
                    return decoded_text
            except (UnicodeDecodeError, LookupError):
                logger.debug(f"❌ 編碼 {encoding} 解碼失敗")
                continue
        
        # 如果所有預設編碼都失敗，使用 chardet 自動檢測
        try:
            detected = chardet.detect(content_bytes[:10000])  # 只檢測前10K字節以提高效率
            if detected and detected['encoding'] and detected['confidence'] > 0.6:
                encoding = detected['encoding']
                decoded_text = content_bytes.decode(encoding)
                if self._is_valid_decoded_text(decoded_text):
                    logger.info(f"🔍 通過自動檢測使用編碼 {encoding} (置信度: {detected['confidence']:.2f})")
                    return decoded_text
        except Exception as e:
            logger.warning(f"自動編碼檢測失敗: {e}")
        
        # 最後手段：使用 errors='replace' 強制解碼
        logger.warning("所有編碼嘗試失敗，使用 UTF-8 強制解碼")
        return content_bytes.decode('utf-8', errors='replace')
    
    def _handle_compression(self, response: httpx.Response, content_bytes: bytes) -> bytes:
        """處理HTTP壓縮內容"""
        import gzip
        import zlib
        
        # 嘗試導入 brotli（可選）
        try:
            import brotli
            brotli_available = True
        except ImportError:
            logger.debug("❌ brotli 庫未安裝，跳過 brotli 解壓縮")
            brotli_available = False
        
        # 檢查 Content-Encoding 標頭
        content_encoding = response.headers.get('content-encoding', '').lower()
        
        try:
            if content_encoding == 'gzip':
                logger.debug("🔧 檢測到 gzip 壓縮，正在解壓")
                return gzip.decompress(content_bytes)
            elif content_encoding == 'br' and brotli_available:
                logger.debug("🔧 檢測到 brotli 壓縮，正在解壓")
                return brotli.decompress(content_bytes)
            elif content_encoding == 'br' and not brotli_available:
                logger.warning("⚠️ 檢測到 brotli 壓縮但未安裝 brotli 庫，嘗試其他方法")
            elif content_encoding == 'deflate':
                logger.debug("🔧 檢測到 deflate 壓縮，正在解壓")
                return zlib.decompress(content_bytes)
        except Exception as e:
            logger.warning(f"⚠️ 壓縮解碼失敗: {e}")
        
        return content_bytes
    
    def _is_likely_compressed(self, content_bytes: bytes) -> bool:
        """檢查內容是否看起來像壓縮數據"""
        if len(content_bytes) < 10:
            return False
        
        # 檢查常見壓縮格式的魔術字節
        # gzip: 1f 8b
        # brotli: 通常有高熵值
        # deflate: 78 9c, 78 01, 78 da, 78 5e
        
        first_bytes = content_bytes[:10]
        
        # gzip 魔術字節
        if first_bytes.startswith(b'\x1f\x8b'):
            return True
        
        # deflate 魔術字節
        if first_bytes.startswith((b'\x78\x9c', b'\x78\x01', b'\x78\xda', b'\x78\x5e')):
            return True
        
        # 檢查是否有過多的非ASCII字符（可能是壓縮數據）
        non_ascii_count = sum(1 for b in first_bytes if b > 127)
        if non_ascii_count > len(first_bytes) * 0.5:
            return True
        
        return False
    
    def _force_decompress(self, content_bytes: bytes) -> bytes:
        """強制嘗試所有可能的解壓方法"""
        import gzip
        import zlib
        
        # 嘗試導入 brotli（可選）
        try:
            import brotli
            brotli_available = True
        except ImportError:
            brotli_available = False
        
        decompress_methods = [
            ("gzip", gzip.decompress),
            ("deflate", zlib.decompress),
            ("deflate (raw)", lambda x: zlib.decompress(x, -15))  # raw deflate
        ]
        
        # 如果 brotli 可用，添加到解壓方法列表
        if brotli_available:
            decompress_methods.insert(1, ("brotli", brotli.decompress))
        
        for method_name, decompress_func in decompress_methods:
            try:
                decompressed = decompress_func(content_bytes)
                logger.info(f"🎉 成功使用 {method_name} 解壓縮")
                return decompressed
            except Exception as e:
                logger.debug(f"❌ {method_name} 解壓失敗: {e}")
                continue
        
        logger.warning("⚠️ 所有解壓方法都失敗，返回原始內容")
        return content_bytes
    
    def _is_valid_decoded_text(self, text: str) -> bool:
        """驗證解碼後的文字是否有效（無明顯亂碼）"""
        if not text or len(text) < 10:
            return False
        
        # 檢查是否有過多的替換字符（�）
        replacement_ratio = text.count('�') / len(text)
        if replacement_ratio > 0.1:  # 放寬到10%，因為有些網站可能包含特殊字符
            logger.debug(f"❌ 替換字符比例過高: {replacement_ratio:.2%}")
            return False
        
        # 檢查是否包含基本的HTML標籤
        html_tags = ['<html', '<body', '<div', '<span', '<a', '<title', '<head', '<!doctype']
        has_html = any(tag in text.lower() for tag in html_tags)
        
        # 檢查是否包含日文字符
        has_japanese = re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', text)
        
        # 檢查是否包含常見的HTML實體或標準字符
        has_entities = any(entity in text for entity in ['&lt;', '&gt;', '&amp;', '&quot;'])
        
        # 檢查字符分佈是否合理（不是純二進制數據）
        printable_chars = sum(1 for c in text[:1000] if c.isprintable() or c.isspace())
        printable_ratio = printable_chars / min(len(text), 1000)
        
        is_valid = (has_html or has_japanese or has_entities) and printable_ratio > 0.7
        
        if not is_valid:
            logger.debug(f"❌ 內容驗證失敗 - HTML:{has_html} 日文:{bool(has_japanese)} 實體:{has_entities} 可列印比例:{printable_ratio:.2%}")
        
        return is_valid

    def batch_search(self, items: List, task_func, stop_event: threading.Event, progress_callback=None) -> Dict:
        results = {}
        total_batches = (len(items) + self.batch_size - 1) // self.batch_size
        for i in range(0, len(items), self.batch_size):
            if stop_event.is_set(): 
                logger.info("任務被使用者中止。")
                break
            batch = items[i:i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            if progress_callback: 
                progress_callback(f"處理批次 {batch_num}/{total_batches}...\n")
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.thread_count) as executor:
                future_to_item = {executor.submit(task_func, item, stop_event): item for item in batch}
                for future in concurrent.futures.as_completed(future_to_item):
                    if stop_event.is_set(): 
                        break
                    item = future_to_item[future]
                    try:
                        result = future.result()
                        results[item] = result
                        if progress_callback:
                            if result and result.get('actresses'): 
                                progress_callback(f"✅ {item}: 找到資料\n")
                            else: 
                                progress_callback(f"❌ {item}: 未找到結果\n")
                    except Exception as e:
                        logger.error(f"批次處理 {item} 時發生錯誤: {e}")
                        if progress_callback: 
                            progress_callback(f"💥 {item}: 處理失敗 - {e}\n")
            if i + self.batch_size < len(items) and total_batches > 1:                time.sleep(self.batch_delay)
        return results
    
    def _search_chiba_f_net(self, code: str, stop_event: threading.Event) -> Optional[Dict]:
        """使用 chiba-f.net 搜尋女優資訊"""
        if stop_event.is_set():
            return None
            
        search_url = f"https://chiba-f.net/search/?keyword={quote(code)}"
          # 使用日文網站專用標頭和增強編碼檢測
        def make_request(url, **kwargs):
            with httpx.Client(timeout=self.timeout, **kwargs) as client:
                # 🔧 使用不支援壓縮的標頭，避免 Brotli 問題
                response = client.get(url, headers=self.japanese_headers)
                response.raise_for_status()
                # 🔧 使用增強的編碼檢測機制
                decoded_content = self._detect_and_decode_content(response)
                logger.debug(f"📄 chiba-f.net 內容長度: {len(decoded_content)} 字符")
                logger.debug(f"📄 chiba-f.net 內容開頭: {decoded_content[:100]}...")
                return BeautifulSoup(decoded_content, 'html.parser')
        
        try:
            soup = self.safe_searcher.safe_request(make_request, search_url)
            
            if soup is None:
                logger.warning(f"無法獲取 {code} 的 chiba-f.net 搜尋頁面")
                return None
                
            # 查找產品區塊
            product_divs = soup.find_all('div', class_='product-div')
            logger.info(f"chiba-f.net 解析: 找到 {len(product_divs)} 個 product-div 元素")
                
            for product_div in product_divs:
                # 檢查番號是否匹配
                pno_element = product_div.find('div', class_='pno')
                if pno_element and code.upper() in pno_element.text.upper():
                    logger.info(f"chiba-f.net 找到匹配番號: {code}")
                    return self._extract_chiba_product_info(product_div, code)
            
            # 如果沒有找到完全匹配，嘗試模糊匹配
            for product_div in product_divs:
                product_text = product_div.get_text()
                if code.upper() in product_text.upper():
                    logger.info(f"chiba-f.net 模糊匹配找到番號: {code}")
                    return self._extract_chiba_product_info(product_div, code)
            
            if not product_divs:
                logger.warning(f"chiba-f.net 未找到任何產品區塊，HTML開頭: {str(soup)[:200]}...")
                        
        except Exception as e:
            logger.error(f"chiba-f.net 搜尋 {code} 時發生錯誤: {e}", exc_info=True)
            
        logger.debug(f"番號 {code} 未在 chiba-f.net 中找到女優資訊。")
        return None
    
    def _extract_chiba_product_info(self, product_div, code: str) -> Dict:
        """從 chiba-f.net 產品區塊提取資訊"""
        result = {
            'source': 'chiba-f.net (安全增強版)',
            'actresses': [],
            'studio': None,
            'studio_code': None,
            'release_date': None
        }
        
        try:
            # 提取女優名稱
            actress_span = product_div.find('span', class_='fw-bold')
            if actress_span:
                result['actresses'] = [actress_span.text.strip()]
            
            # 提取系列/片商資訊
            series_link = product_div.find('a', href=re.compile(r'../series/'))
            if series_link:
                result['studio'] = series_link.text.strip()
                # 從 href 提取片商代碼
                href = series_link.get('href', '')
                if '../series/' in href:
                    result['studio_code'] = href.replace('../series/', '').strip()
            
            # 提取發行日期
            date_span = product_div.find('span', class_='start_date')
            if date_span:
                result['release_date'] = date_span.text.strip()
            
            # 如果沒有找到片商，嘗試從番號推測
            if not result['studio_code']:
                result['studio_code'] = self._extract_studio_code_from_number(code)
            
            if result['actresses']:
                self.search_cache[code] = result
                logger.info(f"番號 {code} 透過 {result['source']} 找到: {', '.join(result['actresses'])}, 片商: {result.get('studio', '未知')}")
                
        except Exception as e:
            logger.warning(f"提取 {code} 從 chiba-f.net 資訊時發生部分錯誤: {str(e)}")
        
        return result if result.get('actresses') else None
    
    def _extract_studio_info(self, soup: BeautifulSoup, code: str) -> Dict:
        """從網頁中提取片商資訊"""
        studio_info = {
            'studio': None,
            'studio_code': None,
            'release_date': None
        }
        
        try:
            # 先取得網頁文字內容，後續方法都可能用到
            page_text = soup.get_text()
            
            # 方法1: 從 AV-WIKI HTML 結構中直接提取片商資訊
            # 查找包含 fa-clone 圖標的 li 元素
            studio_elements = soup.find_all("li")
            for li in studio_elements:
                icon = li.find("i", class_="fa-clone")
                if icon:
                    link = li.find("a")
                    if link and link.text.strip():
                        studio_text = link.text.strip()
                        # 解析片商名稱，例如 "エスワン - SONE" -> studio="エスワン", code="SONE"
                        if " - " in studio_text:
                            parts = studio_text.split(" - ")
                            studio_info['studio'] = parts[0].strip()
                            studio_info['studio_code'] = parts[1].strip()
                        else:
                            studio_info['studio'] = studio_text
                        break
            
            # 方法2: 如果方法1失敗，嘗試從番號中提取片商代碼
            if not studio_info['studio']:
                studio_code = self._extract_studio_code_from_number(code)
                if studio_code:
                    studio_info['studio_code'] = studio_code
                    studio_info['studio'] = self._get_studio_name_by_code(studio_code)
            
            # 方法3: 從網頁內容中搜尋片商資訊（最後手段）
            if not studio_info['studio']:
                # 搜尋常見的片商名稱和模式
                studio_patterns = [
                # 直接片商名稱匹配
                (r'(S1|SOD|MOODYZ|PREMIUM|WANZ|FALENO|ATTACKERS|E-BODY|KAWAII|FITCH|MADONNA|PRESTIGE)', r'\1'),
                # 製作公司/發行商模式
                (r'製作[：:]\s*([^\n\r]+)', r'\1'),
                (r'發行[：:]\s*([^\n\r]+)', r'\1'),
                (r'メーカー[：:]\s*([^\n\r]+)', r'\1'),
                # 番號前綴模式 
                (r'品番[：:]\s*([A-Z]+)-?\d+', r'\1'),
            ]
            
                for pattern, replacement in studio_patterns:
                    match = re.search(pattern, page_text, re.IGNORECASE)
                    if match:
                        extracted_studio = match.group(1).strip()
                        if extracted_studio and len(extracted_studio) < 50:  # 合理長度限制
                            if not studio_info['studio']:
                                studio_info['studio'] = extracted_studio
                            if not studio_info['studio_code'] and len(extracted_studio) <= 10:
                                studio_info['studio_code'] = extracted_studio
                            break
            
            # 方法4: 嘗試提取發行日期（總是執行）
            date_patterns = [
                r'發售日[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
                r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
                r'(\d{4}\.\d{1,2}\.\d{1,2})'
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, page_text)
                if match:
                    studio_info['release_date'] = match.group(1)
                    break                    
        except Exception as e:
            logger.warning(f"提取片商資訊時發生錯誤: {e}")
        
        return studio_info
    
    def _extract_studio_code_from_number(self, code: str) -> Optional[str]:
        """從番號中提取片商代碼"""
        if not code:
            return None
            
        # 提取字母部分作為片商代碼
        match = re.match(r'^([A-Z]+)', code.upper())
        if match:
            return match.group(1)
        return None
    
    def _get_studio_name_by_code(self, studio_code: str) -> Optional[str]:
        """根據片商代碼獲取片商名稱（從 studios.json 載入）"""
        try:
            import json
            from pathlib import Path
            
            # 載入 studios.json 檔案
            studios_file = Path(__file__).parent.parent.parent / 'studios.json'
            if studios_file.exists():
                with open(studios_file, 'r', encoding='utf-8') as f:
                    studios_data = json.load(f)
                
                # 反向查找：從代碼找到片商
                studio_code_upper = studio_code.upper()
                for studio_name, codes in studios_data.items():
                    if studio_code_upper in [code.upper() for code in codes]:
                        return studio_name
        except Exception as e:
            logger.warning(f"載入 studios.json 失敗: {e}")
        
        # 回退到內建對應表
        studio_mapping = {
            'STAR': 'SOD',
            'STARS': 'SOD', 
            'SDJS': 'SOD',
            'SSIS': 'S1',
            'SSNI': 'S1',
            'IPX': 'IdeaPocket',
            'IPZZ': 'IdeaPocket',
            'MIDV': 'MOODYZ',
            'MIAA': 'MOODYZ',
            'WANZ': 'WANZ FACTORY',
            'FSDSS': 'FALENO',
            'PRED': 'PREMIUM',
            'ABW': 'Prestige',
            'BF': 'BeFree',
            'CAWD': 'kawaii',
            'JUFD': 'Fitch',
            'JUL': 'MADONNA',
            'JUY': 'MADONNA',
        }
        
        return studio_mapping.get(studio_code.upper(), studio_code)
    
    def get_safe_searcher_stats(self) -> Dict:
        """獲取安全搜尋器統計資訊"""
        return self.safe_searcher.get_stats()
    
    def clear_cache(self):
        """清空快取"""
        self.search_cache.clear()
        self.safe_searcher.clear_cache()
        logger.info("🧹 已清空所有搜尋快取")
    
    def configure_safe_searcher(self, **kwargs):
        """動態配置安全搜尋器"""
        self.safe_searcher.configure(**kwargs)
        # 更新本地標頭
        self.headers = self.safe_searcher.get_headers()
    
    def get_javdb_stats(self) -> Dict:
        """獲取 JAVDB 搜尋器統計資訊"""
        return self.javdb_searcher.get_stats()
    
    def get_all_search_stats(self) -> Dict:
        """獲取所有搜尋器的統計資訊"""
        return {
            'safe_searcher': self.get_safe_searcher_stats(),
            'javdb_searcher': self.get_javdb_stats(),
            'local_cache_entries': len(self.search_cache)
        }
    
    def clear_all_cache(self):
        """清空所有搜尋快取"""
        self.search_cache.clear()
        self.safe_searcher.clear_cache()
        self.javdb_searcher.clear_cache()
        logger.info("🧹 已清空所有搜尋快取 (包含 JAVDB)")
    
    def search_japanese_sites_only(self, code: str, stop_event: threading.Event) -> Optional[Dict]:
        """僅搜尋日文網站 - AV-WIKI 和 chiba-f.net"""
        if stop_event.is_set(): 
            return None
        if code in self.search_cache: 
            return self.search_cache[code]
        
        try:
            # 第一層：AV-WIKI 搜尋
            logger.debug(f"🇯🇵 日文網站搜尋 - AV-WIKI: {code}")
            result = self._search_av_wiki(code, stop_event)
            if result and result.get('actresses'):
                self.search_cache[code] = result
                return result
            
            # 第二層：chiba-f.net 搜尋
            if not stop_event.is_set():
                logger.debug(f"🇯🇵 日文網站搜尋 - chiba-f.net: {code}")
                result = self._search_chiba_f_net(code, stop_event)
                if result and result.get('actresses'):
                    self.search_cache[code] = result
                    return result
            
            logger.debug(f"🇯🇵 日文網站未找到: {code}")
            return None
            
        except Exception as e:
            logger.error(f"搜尋 {code} 時發生錯誤: {e}", exc_info=True)
            return None
    
    def search_javdb_only(self, code: str, stop_event: threading.Event) -> Optional[Dict]:
        """僅搜尋 JAVDB"""
        if stop_event.is_set(): 
            return None
        if code in self.search_cache: 
            return self.search_cache[code]
        
        try:
            logger.debug(f"📊 JAVDB 搜尋: {code}")
            javdb_result = self.javdb_searcher.search_javdb(code)
            if javdb_result and javdb_result.get('actresses'):
                # 轉換為統一格式
                result = {
                    'source': javdb_result['source'],
                    'actresses': javdb_result['actresses'],
                    'studio': javdb_result.get('studio'),
                    'studio_code': javdb_result.get('studio_code'),
                    'release_date': javdb_result.get('release_date'),
                    'title': javdb_result.get('title'),
                    'duration': javdb_result.get('duration'),
                    'director': javdb_result.get('director'),
                    'series': javdb_result.get('series'),
                    'rating': javdb_result.get('rating'),
                    'categories': javdb_result.get('categories', [])
                }
                self.search_cache[code] = result
                return result
            
            logger.debug(f"📊 JAVDB 未找到: {code}")
            return None
            
        except Exception as e:
            logger.error(f"JAVDB 搜尋 {code} 時發生錯誤: {e}", exc_info=True)
            return None

    def search_japanese_sites(self, code: str, stop_event: threading.Event) -> Optional[Dict]:
        """只搜尋日文網站 (AV-WIKI 和 chiba-f.net)"""
        if stop_event.is_set(): 
            return None
        if code in self.search_cache: 
            return self.search_cache[code]
        
        try:
            # 第一層：AV-WIKI 搜尋
            logger.debug(f"🇯🇵 日文網站搜尋 - AV-WIKI: {code}")
            result = self._search_av_wiki(code, stop_event)
            if result and result.get('actresses'):
                self.search_cache[code] = result
                return result
            
            # 第二層：chiba-f.net 搜尋  
            if not stop_event.is_set():
                logger.debug(f"🇯🇵 日文網站搜尋 - chiba-f.net: {code}")
                result = self._search_chiba_f_net(code, stop_event)
                if result and result.get('actresses'):
                    self.search_cache[code] = result
                    return result
              
            logger.warning(f"番號 {code} 未在日文網站中找到女優資訊。")
            return None            
        except Exception as e:
            logger.error(f"日文網站搜尋番號 {code} 時發生錯誤: {e}", exc_info=True)
            return None

