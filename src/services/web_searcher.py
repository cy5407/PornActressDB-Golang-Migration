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
                logger.warning(f"AV-WIKI 未找到女優名稱，HTML開頭: {str(soup)[:200]}...")
                actresses = self._scan_avwiki_text_for_actresses(soup, code)
            studio_info = self._fetch_avwiki_detail_studio_info(soup, code)
            return self._finalize_avwiki_search_result(code, actresses, studio_info)
        except Exception as e:
            logger.error(f"搜尋 AV-WIKI 番號 {code} 時發生錯誤: {e}", exc_info=True)
            return None

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

        # 過濾已快取的番號
        uncached_codes = [code for code in codes if code not in self.search_cache]
        cached_results = {
            code: self.search_cache[code] for code in codes if code in self.search_cache
        }

        if progress_callback and cached_results:
            progress_callback(f"📦 使用快取: {len(cached_results)} 個番號\n")

        if not uncached_codes:
            return cached_results

        global_total = len(uncached_codes)

        # 使用 threading.Lock 確保進度計數的執行緒安全
        import threading as _threading

        progress_lock = _threading.Lock()
        displayed_codes = set()  # 追蹤已顯示的番號

        # 定義進度回調轉換
        def wrapped_progress_callback(current, _total, code):
            if progress_callback:
                with progress_lock:
                    # 避免重複顯示同一番號
                    if code not in displayed_codes:
                        displayed_codes.add(code)
                        # 使用已顯示的數量作為進度，確保順序一致
                        display_num = len(displayed_codes)
                        progress_callback(
                            f"[{display_num}/{global_total}] 搜尋 {code}\n"
                        )

        # 定義異步執行函式
        async def run_batch_search_all():
            # 在 async 環境中初始化 AVWikiScraper
            avwiki_scraper = AVWikiScraper()

            # 分段執行：避免一次建立過多 tasks 造成記憶體/排程尖峰
            chunk_size = max(200, min(500, self.avwiki_max_concurrent * 20))
            batch_results: dict[str, dict | None] = {}
            for i in range(0, len(uncached_codes), chunk_size):
                if stop_event.is_set():
                    break

                chunk = uncached_codes[i : i + chunk_size]
                chunk_results = await avwiki_scraper.batch_search_concurrent(
                    chunk,
                    max_concurrent=self.avwiki_max_concurrent,
                    progress_callback=wrapped_progress_callback,
                )
                batch_results.update(chunk_results)

            return batch_results

        try:
            # 使用 asyncio.run 執行併發搜尋
            if progress_callback:
                progress_callback(
                    f"🚀 開始 AV-WIKI 批次併發搜尋 ({len(uncached_codes)} 個番號)...\n"
                )

            batch_results = asyncio.run(run_batch_search_all())

            # 將結果加入快取
            for code, result in batch_results.items():
                if result and result.get("actresses"):
                    self.search_cache[code] = result

            # 合併快取結果和新結果
            all_results = {**cached_results, **batch_results}

            # 統計
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

    def batch_cascade_search(
        self,
        codes: list[str],
        stop_event: threading.Event,
        progress_callback=None,
        result_callback=None,
    ) -> dict[str, dict]:
        """
        批次智慧搜尋

        策略：
        1. 先用 AV-WIKI 批次併發搜尋所有番號
        2. 收集失敗的番號
        3. 回傳整理後的結果

        Args:
            codes: 番號列表
            stop_event: 停止事件
            progress_callback: 進度回調函式

        Returns:
            Dict[番號, 搜尋結果（含 tried_sources 欄位）]
        """
        from utils.progress_tracker import SearchProgressInfo

        if not codes:
            return {}

        total_codes = len(codes)
        results = {}

        # 初始化進度追蹤
        progress = SearchProgressInfo(total=total_codes)

        # 第一階段：AV-WIKI 批次併發搜尋
        if progress_callback:
            progress_callback(f"\n{'=' * 60}\n")
            progress_callback(
                f"📡 第一階段：AV-WIKI 批次併發搜尋 ({total_codes} 個番號)\n"
            )
            progress_callback(f"{'=' * 60}\n")

        progress.set_phase(1, "AV-WIKI 批次搜尋", 2)

        def phase1_callback(msg):
            if progress_callback:
                progress_callback(msg)

        avwiki_results = self.batch_search_avwiki_concurrent(
            codes, stop_event, phase1_callback
        )

        # 處理 AV-WIKI 結果
        failed_codes = []
        for code in codes:
            if stop_event.is_set():
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

        if stop_event.is_set():
            return results

        progress.set_phase(2, "整理 AV-WIKI 搜尋結果")

        # 第二階段：僅對可疑的 00xxx 番號追加 AV-WIKI 別名 fallback
        alias_map = {}
        alias_codes = []
        for code in failed_codes:
            candidates = self._build_code_candidates(code)
            if len(candidates) > 1:
                alias_code = candidates[1]
                alias_map[code] = alias_code
                alias_codes.append(alias_code)

        if alias_codes and not stop_event.is_set():
            unique_alias_codes = list(dict.fromkeys(alias_codes))

            if progress_callback:
                progress_callback(f"\n{'=' * 60}\n")
                progress_callback(
                    f"🧪 第二階段：可疑番號別名 fallback ({len(unique_alias_codes)} 個候選)\n"
                )
                progress_callback(f"{'=' * 60}\n")

            alias_results = self.batch_search_avwiki_concurrent(
                unique_alias_codes, stop_event, phase1_callback
            )

            remaining_failed_codes = []
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

            failed_codes = remaining_failed_codes

        for code in failed_codes:
            if result_callback:
                result_callback(code, results[code], None)
            progress.update(code, is_success=False, increment=False)

        # 輸出摘要
        if progress_callback:
            progress_callback(f"\n{progress.format_summary()}\n")

        return results

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
