"""
網路搜尋器模組
"""

import asyncio
import concurrent.futures
import logging
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import chardet
import httpx
from bs4 import BeautifulSoup

from models.config import ConfigManager
from models.studio import StudioIdentifier
from scrapers.sources.avwiki_scraper import AVWikiScraper  # noqa: E402
from scrapers.sources.shiroutowiki_scraper import ShiroutoWikiScraper  # noqa: E402
from src.utils.log_sanitizer import sanitize_url_for_log

from .safe_javdb_searcher import SafeJAVDBSearcher  # noqa: E402
from .safe_searcher import RequestConfig, SafeSearcher  # noqa: E402
from .unified_cache import get_cache_manager  # noqa: E402

# 移除不必要的 create_japanese_soup 匯入，直接使用 JapaneseSiteEnhancer 類別

logger = logging.getLogger(__name__)

AV_WIKI_SEARCH_METHOD = "AV-WIKI (安全增強版)"


class WebSearcher:
    """增強版搜尋器 - 支援搜尋結果頁面"""

    def __init__(self, config: ConfigManager):
        # 初始化安全搜尋器配置
        safe_config = RequestConfig(
            min_interval=config.getfloat("search", "min_interval", fallback=1.0),
            max_interval=config.getfloat("search", "max_interval", fallback=3.0),
            enable_cache=config.getboolean("search", "enable_cache", fallback=True),
            cache_duration=config.getint("search", "cache_duration", fallback=86400),
            max_retries=config.getint("search", "max_retries", fallback=3),
            backoff_factor=config.getfloat("search", "backoff_factor", fallback=2.0),
            rotate_headers=config.getboolean("search", "rotate_headers", fallback=True),
        )

        # 初始化安全搜尋器
        self.safe_searcher = SafeSearcher(safe_config)

        # 初始化日文網站專用的更快速配置（av-wiki 比較不會擋爬蟲）
        japanese_config = RequestConfig(
            min_interval=config.getfloat(
                "search", "japanese_min_interval", fallback=0.5
            ),
            max_interval=config.getfloat(
                "search", "japanese_max_interval", fallback=1.5
            ),
            enable_cache=config.getboolean("search", "enable_cache", fallback=True),
            cache_duration=config.getint("search", "cache_duration", fallback=86400),
            max_retries=config.getint("search", "max_retries", fallback=3),
            backoff_factor=config.getfloat("search", "backoff_factor", fallback=1.5),
            rotate_headers=config.getboolean("search", "rotate_headers", fallback=True),
        )
        self.japanese_searcher = SafeSearcher(japanese_config)

        # 初始化 JAVDB 安全搜尋器
        cache_dir = config.get("search", "cache_dir", fallback=None)
        self.javdb_searcher = SafeJAVDBSearcher(cache_dir)
        # 保留原有配置以向下相容
        self.headers = self.safe_searcher.get_headers()

        # 🔧 日文網站專用標頭（解決 403 Forbidden 和 Brotli 壓縮問題）
        self.japanese_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8,zh-TW;q=0.7",
            "Accept-Charset": "UTF-8,Shift_JIS,EUC-JP,ISO-2022-JP,*;q=0.1",
            "Accept-Encoding": "gzip, deflate, br",  # 接受壓縮（已安裝 brotli）
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Cache-Control": "max-age=0",
        }

        self.search_cache = {}
        self.batch_size = config.getint("search", "batch_size", fallback=10)
        self.thread_count = config.getint("search", "thread_count", fallback=5)
        self.batch_delay = config.getfloat("search", "batch_delay", fallback=2.0)
        self.timeout = config.getint("search", "request_timeout", fallback=20)
        self.shiroutowiki_scraper = ShiroutoWikiScraper(
            self.japanese_searcher, self.japanese_headers, self.timeout
        )
        self._studio_code_mapping = self._load_studio_code_mapping()

        # 初始化片商識別器（用於標準化片商名稱）
        self.studio_identifier = StudioIdentifier()

        # AV-WIKI 批次併發配置
        self.avwiki_concurrent_enabled = config.getboolean(
            "search", "avwiki_concurrent_enabled", fallback=True
        )
        self.avwiki_max_concurrent = config.getint(
            "search", "avwiki_max_concurrent", fallback=15
        )

        # 註冊到統一快取管理器
        cache_manager = get_cache_manager(config)
        cache_manager.register_cache_source("web_searcher", self.search_cache)
        cache_manager.register_cache_source("javdb_searcher", self.javdb_searcher.cache)

        logger.info("🛡️ 已啟用安全搜尋器功能")
        logger.info("🇯🇵 已啟用日文網站快速搜尋功能")
        logger.info("🎬 已啟用 JAVDB 安全搜尋功能")
        logger.info("🧑 已啟用 shiroutowiki 獨立搜尋功能")
        if self.avwiki_concurrent_enabled:
            logger.info(
                f"🚀 已啟用 AV-WIKI 批次併發搜尋 (併發數: {self.avwiki_max_concurrent})"
            )

    def _build_code_candidates(self, code: str) -> list[str]:
        """建立搜尋候選番號。

        目前僅對英文-00xxx 的可疑 FANZA 形式加入去除雙 0 的 fallback，
        避免直接改壞合法保留前導 0 的番號。
        """
        candidates = [code]
        match = re.match(r"^([A-Z]{2,6})-00(\d{3})$", code.upper())
        if match:
            alias_code = f"{match.group(1)}-{match.group(2)}"
            if alias_code not in candidates:
                candidates.append(alias_code)
        return candidates

    @staticmethod
    def _attach_alias_metadata(
        result: dict | None, original_code: str, matched_code: str
    ) -> dict | None:
        """保留原始搜尋碼，並標記別名命中結果。"""
        if not result:
            return None

        enriched = dict(result)
        enriched["searched_code"] = original_code
        if matched_code != original_code:
            enriched["matched_code"] = matched_code
            enriched["search_alias_used"] = True
        return enriched

    def _build_shiroutowiki_candidates(self, code: str) -> list[str]:
        """建立 shiroutowiki 查詢候選。

        先保留既有 00xxx alias fallback，再展開網站專用候選格式。
        """
        candidates: list[str] = []
        for base_candidate in self._build_code_candidates(code):
            for candidate in self.shiroutowiki_scraper.build_search_candidates(
                base_candidate
            ):
                if candidate not in candidates:
                    candidates.append(candidate)
        return candidates

    def search_info(self, code: str, stop_event: threading.Event) -> dict | None:
        """多層級搜尋策略 - AV-WIKI -> JAVDB"""
        if stop_event.is_set():
            return None
        if code in self.search_cache:
            return self.search_cache[code]

        try:
            candidates = self._build_code_candidates(code)
            avwiki_result = self._search_candidates_in_av_wiki(
                code, candidates, stop_event
            )
            if avwiki_result:
                return avwiki_result

            javdb_result = self._search_candidates_in_javdb(
                code, candidates, stop_event
            )
            if javdb_result:
                return javdb_result

            logger.warning(f"番號 {code} 未在所有搜尋源中找到女優資訊。")
            return None
        except Exception as e:
            logger.error(f"搜尋番號 {code} 時發生錯誤: {e}", exc_info=True)
            return None

    def _search_candidates_in_av_wiki(
        self, code: str, candidates: list[str], stop_event: threading.Event
    ) -> dict | None:
        for candidate in candidates:
            logger.debug(f"🔍 第一層搜尋 - AV-WIKI: {candidate}")
            result = self._search_av_wiki(candidate, stop_event)
            if not result or not result.get("actresses"):
                continue
            result = self._attach_alias_metadata(result, code, candidate)
            self.search_cache[code] = result
            return result
        return None

    def _search_candidates_in_javdb(
        self, code: str, candidates: list[str], stop_event: threading.Event
    ) -> dict | None:
        if stop_event.is_set():
            return None
        for candidate in candidates:
            logger.debug(f"🔍 第三層搜尋 - JAVDB: {candidate}")
            javdb_result = self.javdb_searcher.search_javdb(candidate)
            if not self._has_usable_javdb_result(javdb_result):
                continue
            result = self._build_javdb_search_result(code, candidate, javdb_result)
            if result.get("actresses"):
                self.search_cache[code] = result
            self._log_javdb_result(code, result)
            return result
        return None

    @staticmethod
    def _has_usable_javdb_result(javdb_result: dict | None) -> bool:
        return bool(
            javdb_result
            and (
                javdb_result.get("actresses")
                or javdb_result.get("search_status") == "search_error"
            )
        )

    def _build_javdb_search_result(
        self, code: str, candidate: str, javdb_result: dict
    ) -> dict:
        normalized_studio = self.studio_identifier.normalize_studio_name(
            javdb_result.get("studio"), candidate
        )
        result = {
            "source": javdb_result["source"],
            "actresses": javdb_result["actresses"],
            "studio": normalized_studio,
            "studio_code": javdb_result.get("studio_code"),
            "release_date": javdb_result.get("release_date"),
            "title": javdb_result.get("title"),
            "duration": javdb_result.get("duration"),
            "director": javdb_result.get("director"),
            "series": javdb_result.get("series"),
            "rating": javdb_result.get("rating"),
            "categories": javdb_result.get("categories", []),
            "search_status": javdb_result.get("search_status"),
            "search_error_reason": javdb_result.get("search_error_reason"),
            "search_url": javdb_result.get("search_url"),
        }
        return self._attach_alias_metadata(result, code, candidate)

    def _log_javdb_result(self, code: str, result: dict) -> None:
        if not result.get("actresses"):
            logger.warning(
                "⚠️ JAVDB 搜尋 %s 發生暫時性異常: %s",
                code,
                result.get("search_error_reason", "未知原因"),
            )
            return

        log_parts = [f"番號 {code} 透過 {result['source']} 找到:"]
        log_parts.append(f"女優: {', '.join(result['actresses'])}")
        log_parts.append(f"片商: {result.get('studio', '未知')}")
        if result.get("rating"):
            log_parts.append(f"評分: {result['rating']}")
        if result.get("categories"):
            categories_str = ", ".join(result["categories"][:3])
            if len(result["categories"]) > 3:
                categories_str += f" 等{len(result['categories'])}個類別"
            log_parts.append(f"類別: {categories_str}")
        logger.info(" | ".join(log_parts))

    @staticmethod
    def _build_search_error_result(source: str, reason: str) -> dict:
        return {
            "source": source,
            "actresses": [],
            "search_status": "search_error",
            "search_error_reason": reason,
            "last_search_date": datetime.now(UTC).isoformat(),
        }

    def _extract_avwiki_detail_url(self, soup: BeautifulSoup, code: str) -> str | None:
        """從 AV-WIKI 搜尋結果頁提取作品詳情頁網址。"""
        code_slug = code.lower().replace("/", "-")
        candidates = self._collect_avwiki_candidate_urls(soup)

        if not candidates:
            return None

        for url in candidates:
            if code_slug in url.lower():
                return url

        return candidates[0]

    def _collect_avwiki_candidate_urls(self, soup: BeautifulSoup) -> list[str]:
        candidates: list[str] = []
        for link in soup.find_all("a", href=True):
            href = (link.get("href") or "").strip()
            if not href:
                continue

            link_text = link.get_text(strip=True)
            is_readmore = "続きを読む" in link_text
            is_avwiki_link = "av-wiki.net/" in href or href.startswith("/")
            if not (is_readmore and is_avwiki_link):
                continue

            if href.startswith("/"):
                href = f"https://av-wiki.net{href}"
            if href.startswith("https://av-wiki.net/"):
                candidates.append(href)
        return candidates

    def _is_actress_name(self, text: str) -> bool:
        """判斷文字是否可能是女優名稱。"""
        if not text or len(text) < 2 or len(text) > 20:
            return False

        exclude_keywords = [
            "SOD",
            "STARS",
            "FANZA",
            "MGS",
            "MIDV",
            "SSIS",
            "IPX",
            "IPZZ",
            "続きを読む",
            "検索",
            "件",
            "特典",
            "映像",
            "付き",
            "star",
            "SOKMIL",
            "Menu",
            "セール",
            "限定",
            "最大",
        ]
        if any(keyword in text for keyword in exclude_keywords):
            return False
        if re.match(r"^\d+$", text) or len(re.findall(r"\d", text)) > len(text) // 2:
            return False
        return bool(re.search(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]", text))

    def _detect_and_decode_content(self, response: httpx.Response) -> str:
        """多重編碼檢測和解碼機制（支援壓縮內容處理）。"""
        content_bytes = response.content
        content_bytes = self._handle_compression(response, content_bytes)

        if self._is_likely_compressed(content_bytes):
            logger.warning("⚠️ 內容仍然看起來像壓縮數據，嘗試強制解壓")
            content_bytes = self._force_decompress(content_bytes)

        content_encoding = response.headers.get("content-encoding", "").lower()
        if content_encoding == "br" and len(content_bytes) > 0:
            logger.warning("⚠️ 服務器發送了 brotli 壓縮內容，嘗試強制解壓")
            content_bytes = self._force_decompress(content_bytes)

        encoding_attempts = ["utf-8", "shift_jis", "euc-jp", "cp932", "iso-2022-jp"]
        if response.encoding and response.encoding.lower() not in [enc.lower() for enc in encoding_attempts]:
            encoding_attempts.insert(0, response.encoding.lower())

        for encoding in encoding_attempts:
            try:
                decoded_text = content_bytes.decode(encoding)
                if self._is_valid_decoded_text(decoded_text):
                    logger.debug(f"✅ 成功使用編碼 {encoding} 解碼內容")
                    return decoded_text
            except (UnicodeDecodeError, LookupError):
                logger.debug(f"❌ 編碼 {encoding} 解碼失敗")
                continue

        try:
            detected = chardet.detect(content_bytes[:10000])
            if detected and detected["encoding"] and detected["confidence"] > 0.6:
                encoding = detected["encoding"]
                decoded_text = content_bytes.decode(encoding)
                if self._is_valid_decoded_text(decoded_text):
                    logger.info(f"🔍 通過自動檢測使用編碼 {encoding} (置信度: {detected['confidence']:.2f})")
                    return decoded_text
        except Exception as e:
            logger.warning(f"自動編碼檢測失敗: {e}")

        logger.warning("所有編碼嘗試失敗，使用 UTF-8 強制解碼")
        return content_bytes.decode("utf-8", errors="replace")

    def _handle_compression(
        self, response: httpx.Response, content_bytes: bytes
    ) -> bytes:
        """處理HTTP壓縮內容。"""
        import gzip
        import zlib

        try:
            import brotli
            brotli_available = True
        except ImportError:
            logger.debug("❌ brotli 庫未安裝，跳過 brotli 解壓縮")
            brotli_available = False

        content_encoding = response.headers.get("content-encoding", "").lower()

        try:
            if content_encoding == "gzip":
                logger.debug("🔧 檢測到 gzip 壓縮，正在解壓")
                return gzip.decompress(content_bytes)
            elif content_encoding == "br" and brotli_available:
                logger.debug("🔧 檢測到 brotli 壓縮，正在解壓")
                return brotli.decompress(content_bytes)
            elif content_encoding == "br" and not brotli_available:
                logger.warning("⚠️ 檢測到 brotli 壓縮但未安裝 brotli 庫，嘗試其他方法")
            elif content_encoding == "deflate":
                logger.debug("🔧 檢測到 deflate 壓縮，正在解壓")
                return zlib.decompress(content_bytes)
        except Exception as e:
            logger.warning(f"⚠️ 壓縮解碼失敗: {e}")

        return content_bytes

    def _force_decompress(self, content_bytes: bytes) -> bytes:
        """強制嘗試所有可能的解壓方法。"""
        import gzip
        import zlib

        try:
            import brotli
            brotli_available = True
        except ImportError:
            brotli_available = False

        decompress_methods = [
            ("gzip", gzip.decompress),
            ("deflate", zlib.decompress),
            ("deflate (raw)", lambda x: zlib.decompress(x, -15)),
        ]
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

    def _is_likely_compressed(self, content_bytes: bytes) -> bool:
        """檢查內容是否看起來像壓縮數據。"""
        if len(content_bytes) < 10:
            return False

        first_bytes = content_bytes[:10]
        if first_bytes.startswith(b"\x1f\x8b"):
            return True
        if first_bytes.startswith((b"\x78\x9c", b"\x78\x01", b"\x78\xda", b"\x78\x5e")):
            return True

        non_ascii_count = sum(1 for b in first_bytes if b > 127)
        return non_ascii_count > len(first_bytes) * 0.5

    def _is_valid_decoded_text(self, text: str) -> bool:
        """驗證解碼後的文字是否有效（無明顯亂碼）。"""
        if not text or len(text) < 10:
            return False

        replacement_ratio = text.count("�") / len(text)
        if replacement_ratio > 0.1:
            logger.debug(f"❌ 替換字符比例過高: {replacement_ratio:.2%}")
            return False

        html_tags = [
            "<html",
            "<body",
            "<div",
            "<span",
            "<a",
            "<title",
            "<head",
            "<!doctype",
        ]
        has_html = any(tag in text.lower() for tag in html_tags)
        has_japanese = re.search(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]", text)
        has_entities = any(
            entity in text for entity in ["&lt;", "&gt;", "&amp;", "&quot;"]
        )

        printable_chars = sum(1 for c in text[:1000] if c.isprintable() or c.isspace())
        printable_ratio = printable_chars / min(len(text), 1000)

        is_valid = (has_html or has_japanese or has_entities) and printable_ratio > 0.7
        if not is_valid:
            logger.debug(
                f"❌ 內容驗證失敗 - HTML:{has_html} 日文:{bool(has_japanese)} 實體:{has_entities} 可列印比例:{printable_ratio:.2%}"
            )

        return is_valid

    def _fetch_avwiki_search_soup(self, url: str) -> BeautifulSoup:
        def make_request(req_url, **kwargs):
            kwargs.pop("timeout", None)
            with httpx.Client(timeout=self.timeout, **kwargs) as client:
                response = client.get(req_url, headers=self.japanese_headers)
                response.raise_for_status()
                decoded_content = self._detect_and_decode_content(response)
                logger.debug(f"📄 AV-WIKI 內容長度: {len(decoded_content)} 字符")
                logger.debug(f"📄 AV-WIKI 內容開頭: {decoded_content[:100]}...")
                return BeautifulSoup(decoded_content, "html.parser")

        return self.safe_searcher.safe_request(make_request, url)

    @staticmethod
    def _is_avwiki_no_results_page(soup: BeautifulSoup) -> bool:
        page_text = soup.get_text()
        return any(indicator in page_text for indicator in ["該当なし", "見つかりませんでした", "検索結果：0", "0件"])

    def _extract_avwiki_actresses(self, soup: BeautifulSoup) -> list[str]:
        actresses: list[str] = []
        seen_actresses: set[str] = set()
        tag_links = soup.find_all("a", rel="tag")
        logger.info(f"AV-WIKI 解析: 找到 {len(tag_links)} 個 tag 連結")
        for link in tag_links:
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if "/av-actress/" in href and text and text not in seen_actresses:
                seen_actresses.add(text)
                actresses.append(text)
                logger.info(f"AV-WIKI 提取到女優: {text} (來自 {href})")

        actress_name_elements = soup.find_all(class_="actress-name")
        for element in actress_name_elements:
            for link in element.find_all("a"):
                href = link.get("href", "")
                text = link.get_text(strip=True)
                if "/av-actress/" not in href or not text or text in seen_actresses:
                    continue
                seen_actresses.add(text)
                actresses.append(text)
                logger.info(f"AV-WIKI 提取到女優: {text} (來自 {href})")
        return actresses

    def _fetch_avwiki_detail_studio_info(self, soup: BeautifulSoup, code: str) -> dict:
        studio_info = self._extract_studio_info(soup, code)
        if studio_info.get("studio"):
            return studio_info
        detail_url = self._extract_avwiki_detail_url(soup, code)
        if not detail_url:
            return studio_info
        logger.debug(f"🔍 AV-WIKI 詳情頁補抓片商: {code} -> {sanitize_url_for_log(detail_url)}")
        detail_soup = self.safe_searcher.safe_request(self._fetch_avwiki_search_soup, detail_url)
        if detail_soup is not None:
            detail_studio = self._extract_studio_info(detail_soup, code)
            for key in ("studio", "studio_code", "release_date"):
                if detail_studio.get(key):
                    studio_info[key] = detail_studio[key]
        return studio_info

    def _scan_avwiki_text_for_actresses(self, soup: BeautifulSoup, code: str) -> list[str]:
        page_text = soup.get_text()
        lines = [line.strip() for line in page_text.split("\n") if line.strip()]
        actresses: list[str] = []
        for i, line in enumerate(lines):
            if code not in line:
                continue
            for j in range(max(0, i - 3), min(len(lines), i + 1)):
                for name in re.findall(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{2,8}", lines[j]):
                    if name not in actresses and self._is_valid_actress_name(name):
                        actresses.append(name)
            if actresses:
                break
        return actresses

    def _finalize_avwiki_search_result(self, code: str, actresses: list[str], studio_info: dict) -> dict | None:
        if len(actresses) > 10:
            logger.info(f"AV-WIKI 搜尋 {code}: 找到過多女優，視為可能錯誤結果")
            return None
        if not actresses:
            logger.info(f"AV-WIKI 搜尋 {code}: 未找到有效女優資訊")
            return None
        return {"source": AV_WIKI_SEARCH_METHOD, "actresses": actresses, "studio": self.studio_identifier.normalize_studio_name(studio_info.get("studio"), code), "studio_code": studio_info.get("studio_code"), "release_date": studio_info.get("release_date")}

    def _search_av_wiki(self, code: str, stop_event: threading.Event) -> dict | None:
        """AV-WIKI 搜尋方法"""
        if stop_event.is_set():
            return None
        search_url = f"https://av-wiki.net/?s={quote(code)}&post_type=product"
        try:
            soup = self._fetch_avwiki_search_soup(search_url)
            if soup is None:
                logger.warning(f"無法獲取 {code} 的 AV-WIKI 搜尋頁面")
                return self._build_search_error_result(AV_WIKI_SEARCH_METHOD, "無法獲取搜尋頁面")
            search_results = soup.find_all("div", class_="column-flex")
            logger.info(f"AV-WIKI 搜尋 {code}: 找到 {len(search_results)} 個搜尋結果")
            if not search_results and self._is_avwiki_no_results_page(soup):
                logger.info(f"AV-WIKI 明確顯示沒有找到 {code} 的結果")
                return None
            actresses = self._extract_avwiki_actresses(soup)
            logger.info(f"AV-WIKI 最終找到 {len(actresses)} 位女優: {actresses}")
            if not actresses:
                logger.warning(f"AV-WIKI 未找到結構化女優名稱，HTML開頭: {str(soup)[:200]}...")
            studio_info = self._fetch_avwiki_detail_studio_info(soup, code)
            return self._finalize_avwiki_search_result(code, actresses, studio_info)
        except Exception as e:
            logger.error(f"搜尋 AV-WIKI 番號 {code} 時發生錯誤: {e}", exc_info=True)
            return self._build_search_error_result(AV_WIKI_SEARCH_METHOD, str(e))

    def _split_cached_avwiki_codes(self, codes: list) -> tuple[list, dict[str, dict]]:
        uncached_codes = [code for code in codes if code not in self.search_cache]
        cached_results = {
            code: self.search_cache[code] for code in codes if code in self.search_cache
        }
        return uncached_codes, cached_results

    @staticmethod
    def _build_avwiki_progress_callback(progress_callback, global_total: int):
        if not progress_callback:
            return None

        import threading as _threading

        progress_lock = _threading.Lock()
        displayed_codes = set()

        def wrapped_progress_callback(_current, _total, code):
            with progress_lock:
                if code in displayed_codes:
                    return
                displayed_codes.add(code)
                progress_callback(f"[{len(displayed_codes)}/{global_total}] 搜尋 {code}\n")

        return wrapped_progress_callback

    async def _run_avwiki_batch_search(self, uncached_codes: list, stop_event: threading.Event, progress_callback=None) -> dict[str, dict | None]:
        avwiki_scraper = AVWikiScraper()
        chunk_size = max(200, min(500, self.avwiki_max_concurrent * 20))
        batch_results: dict[str, dict | None] = {}
        for i in range(0, len(uncached_codes), chunk_size):
            if stop_event.is_set():
                break
            chunk = uncached_codes[i : i + chunk_size]
            if not chunk:
                continue
            chunk_results = await avwiki_scraper.batch_search_concurrent(
                chunk,
                max_concurrent=self.avwiki_max_concurrent,
                progress_callback=progress_callback,
            )
            batch_results.update(chunk_results)
        return batch_results

    def _cache_avwiki_batch_results(self, batch_results: dict[str, dict | None]) -> None:
        for code, result in batch_results.items():
            if result and result.get("actresses"):
                self.search_cache[code] = result

    def search_japanese_sites_only(
        self, code: str, stop_event: threading.Event
    ) -> dict | None:
        """search_japanese_sites 的別名，保持向下相容。"""
        return self.search_japanese_sites(code, stop_event)

    def search_japanese_sites(
        self, code: str, stop_event: threading.Event
    ) -> dict | None:
        """只搜尋 AV-WIKI。"""
        if stop_event.is_set():
            return None
        if code in self.search_cache:
            return self.search_cache[code]

        try:
            last_error_result = None
            for candidate in self._build_code_candidates(code):
                logger.debug(f"🇯🇵 AV-WIKI 搜尋: {candidate}")
                result = self._search_av_wiki(candidate, stop_event)
                if result and result.get("search_status") == "search_error":
                    last_error_result = self._attach_alias_metadata(result, code, candidate)
                    continue
                if result and result.get("actresses"):
                    result = self._attach_alias_metadata(result, code, candidate)
                    self.search_cache[code] = result
                    return result

            if last_error_result:
                return last_error_result

            logger.warning(f"番號 {code} 未在 AV-WIKI 中找到女優資訊。")
            return None
        except Exception as e:
            logger.error(f"AV-WIKI 搜尋番號 {code} 時發生錯誤: {e}", exc_info=True)
            return self._build_search_error_result(AV_WIKI_SEARCH_METHOD, str(e))

    def batch_search_avwiki_concurrent(
        self, codes: list, stop_event: threading.Event, progress_callback=None
    ) -> dict[str, dict | None]:
        """使用 AV-WIKI 批次併發搜尋

        Args:
            codes: 番號列表
            stop_event: 停止事件
            progress_callback: 進度回調函式

        Returns:
            Dict[番號, 搜尋結果]
        """
        if not codes:
            return {}

        uncached_codes, cached_results = self._split_cached_avwiki_codes(codes)
        if progress_callback and cached_results:
            progress_callback(f"📦 使用快取: {len(cached_results)} 個番號\n")
        if not uncached_codes:
            return cached_results

        wrapped_progress_callback = self._build_avwiki_progress_callback(
            progress_callback, len(uncached_codes)
        )

        try:
            if progress_callback:
                progress_callback(
                    f"🚀 開始 AV-WIKI 批次併發搜尋 ({len(uncached_codes)} 個番號)...\n"
                )

            batch_results = asyncio.run(
                self._run_avwiki_batch_search(
                    uncached_codes, stop_event, wrapped_progress_callback
                )
            )
            self._cache_avwiki_batch_results(batch_results)
            all_results = {**cached_results, **batch_results}
            success_count = sum(
                1 for r in batch_results.values() if r and r.get("actresses")
            )
            if progress_callback:
                progress_callback(
                    f"\n✅ AV-WIKI 批次搜尋完成: {success_count}/{len(uncached_codes)} 個番號找到資料\n"
                )
            return all_results
        except Exception as e:
            logger.error(f"AV-WIKI 批次併發搜尋發生錯誤: {e}", exc_info=True)
            if progress_callback:
                progress_callback(f"❌ AV-WIKI 批次搜尋失敗: {e}\n")
            return cached_results

    # ============================================================
    # 級聯搜尋功能（新增）
    # ============================================================

    def _apply_cascade_avwiki_results(
        self,
        codes: list[str],
        avwiki_results: dict[str, dict | None],
        progress,
        result_callback=None,
        stop_event: threading.Event | None = None,
    ) -> tuple[dict[str, dict], list[str]]:
        results: dict[str, dict] = {}
        failed_codes: list[str] = []
        for code in codes:
            if stop_event and stop_event.is_set():
                break
            result = avwiki_results.get(code)
            if result and result.get("actresses"):
                results[code] = {
                    **result,
                    "tried_sources": ["AV-WIKI"],
                    "final_source": "AV-WIKI",
                }
                if result_callback:
                    result_callback(code, results[code], None)
                progress.update(code, is_success=True, source="AV-WIKI")
            else:
                failed_codes.append(code)
                results[code] = {
                    "actresses": [],
                    "source": None,
                    "tried_sources": ["AV-WIKI"],
                    "final_source": None,
                }
        return results, failed_codes

    def _build_cascade_alias_map(self, failed_codes: list[str]) -> tuple[dict[str, str], list[str]]:
        alias_map: dict[str, str] = {}
        alias_codes: list[str] = []
        for code in failed_codes:
            candidates = self._build_code_candidates(code)
            if len(candidates) > 1:
                alias_code = candidates[1]
                alias_map[code] = alias_code
                alias_codes.append(alias_code)
        return alias_map, list(dict.fromkeys(alias_codes))

    def _apply_cascade_alias_results(
        self,
        failed_codes: list[str],
        alias_map: dict[str, str],
        alias_results: dict[str, dict | None],
        results: dict[str, dict],
        progress,
        result_callback=None,
    ) -> list[str]:
        remaining_failed_codes: list[str] = []
        for code in failed_codes:
            alias_code = alias_map.get(code)
            alias_result = alias_results.get(alias_code) if alias_code else None
            if alias_result and alias_result.get("actresses"):
                results[code] = {
                    **self._attach_alias_metadata(alias_result, code, alias_code),
                    "tried_sources": ["AV-WIKI", f"AV-WIKI alias:{alias_code}"],
                    "final_source": "AV-WIKI",
                }
                if result_callback:
                    result_callback(code, results[code], None)
                progress.update(
                    code,
                    is_success=True,
                    source="AV-WIKI alias",
                    increment=False,
                )
            else:
                remaining_failed_codes.append(code)
        return remaining_failed_codes

    def batch_cascade_search(
        self,
        codes: list[str],
        stop_event: threading.Event,
        progress_callback=None,
        result_callback=None,
    ) -> dict[str, dict]:
        """批次智慧搜尋：AV-WIKI 主流程 + alias fallback。"""
        from utils.progress_tracker import SearchProgressInfo

        if not codes:
            return {}

        total_codes = len(codes)
        progress = SearchProgressInfo(total=total_codes)
        if progress_callback:
            progress_callback(f"\n{'=' * 60}\n")
            progress_callback(f"📡 第一階段：AV-WIKI 批次併發搜尋 ({total_codes} 個番號)\n")
            progress_callback(f"{'=' * 60}\n")
        progress.set_phase(1, "AV-WIKI 批次搜尋", 2)

        def phase1_callback(msg):
            if progress_callback:
                progress_callback(msg)

        avwiki_results = self.batch_search_avwiki_concurrent(codes, stop_event, phase1_callback)
        results, failed_codes = self._apply_cascade_avwiki_results(
            codes, avwiki_results, progress, result_callback, stop_event
        )

        if stop_event.is_set():
            return results

        progress.set_phase(2, "整理 AV-WIKI 搜尋結果")
        alias_map, unique_alias_codes = self._build_cascade_alias_map(failed_codes)
        if unique_alias_codes and not stop_event.is_set():
            if progress_callback:
                progress_callback(f"\n{'=' * 60}\n")
                progress_callback(f"🧪 第二階段：可疑番號別名 fallback ({len(unique_alias_codes)} 個候選)\n")
                progress_callback(f"{'=' * 60}\n")

            alias_results = self.batch_search_avwiki_concurrent(
                unique_alias_codes, stop_event, phase1_callback
            )
            failed_codes = self._apply_cascade_alias_results(
                failed_codes, alias_map, alias_results, results, progress, result_callback
            )

        for code in failed_codes:
            if result_callback:
                result_callback(code, results[code], None)
            progress.update(code, is_success=False, increment=False)

        if progress_callback:
            progress_callback(f"\n{progress.format_summary()}\n")

        return results

    def _extract_studio_info(self, soup: BeautifulSoup, code: str) -> dict:
        """從網頁中提取片商資訊。"""
        studio_info = {"studio": None, "studio_code": None, "release_date": None}

        try:
            page_text = soup.get_text()

            studio, studio_code = self._extract_studio_from_html(soup)
            if studio:
                studio_info["studio"] = studio
                studio_info["studio_code"] = studio_code

            if not studio_info["studio"]:
                studio, studio_code = self._extract_studio_from_text(page_text)
                if studio:
                    studio_info["studio"] = studio
                    studio_info["studio_code"] = studio_code

            if not studio_info["studio"]:
                extracted_code = self._extract_studio_code_from_number(code)
                if extracted_code:
                    studio_info["studio_code"] = extracted_code
                    studio_info["studio"] = self._get_studio_name_by_code(extracted_code)

            studio_info["release_date"] = self._extract_release_date(page_text)
        except Exception as e:
            logger.warning(f"提取片商資訊時發生錯誤: {e}")

        return studio_info

    def _extract_studio_from_html(self, soup: BeautifulSoup) -> tuple[str | None, str | None]:
        for li in soup.find_all("li"):
            icon = li.find("i", class_="fa-clone")
            if not icon:
                continue
            link = li.find("a")
            if not (link and link.text.strip()):
                continue
            studio_text = link.text.strip()
            if " - " in studio_text:
                parts = studio_text.split(" - ")
                return parts[0].strip(), parts[1].strip()
            return studio_text, None
        return None, None

    def _extract_studio_from_text(self, page_text: str) -> tuple[str | None, str | None]:
        studio_patterns = [
            r"(S1|SOD|MOODYZ|PREMIUM|WANZ|FALENO|ATTACKERS|E-BODY|KAWAII|FITCH|MADONNA|PRESTIGE)",
            r"製作[：:]\s*([^\n\r]+)",
            r"發行[：:]\s*([^\n\r]+)",
            r"メーカー[：:]\s*([^\n\r]+)",
            r"メーカー\s*[\r\n]+\s*([^\n\r]+)",
            r"品番[：:]\s*([A-Z]+)-?\d+",
        ]
        for pattern in studio_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if not match:
                continue
            extracted = match.group(1).strip()
            if not extracted or len(extracted) >= 50:
                continue
            studio_code = extracted if len(extracted) <= 10 else None
            return extracted, studio_code
        return None, None

    def _extract_release_date(self, page_text: str) -> str | None:
        date_patterns = [
            r"發售日[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            r"(\d{4}\.\d{1,2}\.\d{1,2})",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, page_text)
            if match:
                return match.group(1)
        return None

    def _load_studio_code_mapping(self) -> dict[str, str]:
        """載入片商代碼對照表，避免批次搜尋時重複讀取磁碟。"""
        studio_mapping = {
            "STAR": "SOD",
            "STARS": "SOD",
            "SDJS": "SOD",
            "SSIS": "S1",
            "SSNI": "S1",
            "IPX": "IdeaPocket",
            "IPZZ": "IdeaPocket",
            "MIDV": "MOODYZ",
            "MIAA": "MOODYZ",
            "WANZ": "WANZ FACTORY",
            "FSDSS": "FALENO",
            "PRED": "PREMIUM",
            "ABW": "Prestige",
            "BF": "BeFree",
            "CAWD": "kawaii",
            "JUFD": "Fitch",
            "JUL": "MADONNA",
            "JUY": "MADONNA",
        }

        try:
            try:
                from utils.json_utils import load as json_load
            except ImportError:  # pragma: no cover
                from src.utils.json_utils import load as json_load

            studios_file = Path(__file__).parent.parent.parent / "studios.json"
            if studios_file.exists():
                with open(studios_file, encoding="utf-8") as f:
                    studios_data = json_load(f)

                for studio_name, codes in studios_data.items():
                    for code in codes:
                        studio_mapping[code.upper()] = studio_name
        except Exception as e:
            logger.warning(f"載入 studios.json 失敗: {e}")

        return studio_mapping

    def _extract_studio_code_from_number(self, code: str) -> str | None:
        """從番號中提取片商代碼。"""
        if not code:
            return None
        match = re.match(r"^([A-Z]+)", code.upper())
        if match:
            return match.group(1)
        return None

    def _get_studio_name_by_code(self, studio_code: str) -> str | None:
        """根據片商代碼獲取片商名稱。"""
        return self._studio_code_mapping.get(studio_code.upper(), studio_code)

    def get_safe_searcher_stats(self) -> dict:
        """獲取安全搜尋器統計資訊。"""
        return self.safe_searcher.get_stats()

    def clear_cache(self):
        """清空快取。"""
        self.search_cache.clear()
        self.safe_searcher.clear_cache()
        logger.info("🧹 已清空所有搜尋快取")

    def configure_safe_searcher(self, **kwargs):
        """動態配置安全搜尋器。"""
        self.safe_searcher.configure(**kwargs)
        self.headers = self.safe_searcher.get_headers()

    def get_javdb_stats(self) -> dict:
        """獲取 JAVDB 搜尋器統計資訊。"""
        return self.javdb_searcher.get_stats()

    def get_all_search_stats(self) -> dict:
        """獲取所有搜尋器的統計資訊。"""
        return {
            "safe_searcher": self.get_safe_searcher_stats(),
            "javdb_searcher": self.get_javdb_stats(),
            "local_cache_entries": len(self.search_cache),
        }

    def clear_all_cache(self):
        """清空所有搜尋快取。"""
        self.search_cache.clear()
        self.safe_searcher.clear_cache()
        self.javdb_searcher.clear_cache()
        logger.info("🧹 已清空所有搜尋快取 (包含 JAVDB)")

    def search_shiroutowiki_only(
        self, code: str, stop_event: threading.Event
    ) -> dict | None:
        """僅搜尋 shiroutowiki。保留舊 API，內部委派到網站專用實作。"""
        if stop_event.is_set():
            return None
        if code in self.search_cache:
            return self.search_cache[code]

        try:
            candidates = self._build_shiroutowiki_candidates(code)
            result = self.shiroutowiki_scraper.search_video(code, candidates)
            if result and result.get("actresses"):
                result = self._attach_alias_metadata(
                    result, code, result.get("matched_code", code)
                )
                self.search_cache[code] = result
                self.search_cache[f"shiroutowiki::{code}"] = result
            return result
        except Exception as e:
            logger.error(f"shiroutowiki 搜尋番號 {code} 時發生錯誤: {e}", exc_info=True)
            return self._build_search_error_result("shiroutowiki", str(e))

    def search_avwiki_only(self, code: str, stop_event: threading.Event) -> dict | None:
        """僅搜尋 AV-WIKI。"""
        return self.search_japanese_sites(code, stop_event)

    def search_javdb_only(self, code: str, stop_event: threading.Event) -> dict | None:
        """僅搜尋 JAVDB。"""
        if stop_event.is_set():
            return None
        if code in self.search_cache:
            return self.search_cache[code]

        try:
            logger.debug(f"📊 JAVDB 搜尋: {code}")
            candidates = self._build_code_candidates(code)
            return self._search_candidates_in_javdb(code, candidates, stop_event)
        except Exception as e:
            logger.error(f"JAVDB 搜尋 {code} 時發生錯誤: {e}", exc_info=True)
            return self._build_search_error_result("JAVDB (安全增強版)", str(e))

    def batch_search(
        self,
        items: list,
        task_func,
        stop_event: threading.Event,
        progress_callback=None,
        result_callback=None,
    ) -> dict:
        """
        批次執行搜尋任務。

        task_func 成功回傳值必須是 dict；回傳 None 屬於 unsupported
        behavior，會與 task exception 使用的 None sentinel 不可區分。
        """
        results = {}
        total_batches = (len(items) + self.batch_size - 1) // self.batch_size
        for i in range(0, len(items), self.batch_size):
            if stop_event.is_set():
                logger.info("任務被使用者中止。")
                break
            batch = items[i : i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            if progress_callback:
                progress_callback(f"處理批次 {batch_num}/{total_batches}...\n")
            results.update(
                self._run_batch(
                    batch, task_func, stop_event, result_callback, progress_callback
                )
            )
            if i + self.batch_size < len(items) and total_batches > 1:
                time.sleep(self.batch_delay)
        return results

    def _run_batch(
        self,
        batch: list,
        task_func,
        stop_event: threading.Event,
        result_callback=None,
        progress_callback=None,
    ) -> dict:
        results = {}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.thread_count
        ) as executor:
            future_to_item = {
                executor.submit(task_func, item, stop_event): item for item in batch
            }
            for future in concurrent.futures.as_completed(future_to_item):
                if stop_event.is_set():
                    break
                item = future_to_item[future]
                self._collect_future(
                    item, future, results, result_callback, progress_callback
                )
        return results

    def _collect_future(
        self,
        item,
        future,
        results: dict,
        result_callback=None,
        progress_callback=None,
    ) -> dict | None:
        """收集單一 future；None 僅代表 exception path，不代表 not-found。"""
        try:
            result = future.result()
            results[item] = result
            if result_callback:
                result_callback(item, result, None)
            if progress_callback:
                progress_callback(self._format_item_progress(item, result))
            return result
        except Exception as e:
            logger.error(f"批次處理 {item} 時發生錯誤: {e}")
            results[item] = None
            if result_callback:
                result_callback(item, None, e)
            if progress_callback:
                progress_callback(f"💥 {item}: 處理失敗 - {e}\n")
            return None

    @staticmethod
    def _format_item_progress(item, result) -> str:
        if result and result.get("actresses"):
            return f"✅ {item}: 找到資料\n"
        if result and result.get("search_status") == "search_error":
            return f"⚠️ {item}: 搜尋頁面異常 - {result.get('search_error_reason', '未知原因')}\n"
        return f"❌ {item}: 未找到結果\n"

    def cascade_search_single(
        self, code: str, stop_event: threading.Event, sources: list[str] = None
    ) -> dict:
        """
        對單一番號執行 AV-WIKI 搜尋

        Args:
            code: 影片番號
            stop_event: 停止事件
            sources: 搜尋來源順序，預設 ['avwiki']

        Returns:
            搜尋結果（含 tried_sources 欄位）
        """
        sources = sources or ["avwiki"]
        tried = []

        # 檢查快取
        if code in self.search_cache:
            return {
                **self.search_cache[code],
                "tried_sources": ["cache"],
                "final_source": "cache",
            }

        for source in sources:
            if stop_event.is_set():
                break

            tried.append(source)
            result = None

            try:
                if source == "avwiki":
                    result = self._search_av_wiki(code, stop_event)

                if result and result.get("actresses"):
                    result["tried_sources"] = tried
                    result["final_source"] = source
                    self.search_cache[code] = result
                    return result

            except Exception as e:
                logger.warning(f"[級聯搜尋] {code} 在 {source} 失敗: {e}")
                continue

        # 全部失敗
        return {
            "code": code,
            "actresses": [],
            "source": None,
            "tried_sources": tried,
            "final_source": None,
            "status": "not_found",
        }
