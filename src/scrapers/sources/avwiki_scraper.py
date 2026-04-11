"""
AV-WIKI 專用爬蟲
針對 av-wiki.net 優化的爬蟲實作
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote

import aiohttp
from bs4 import BeautifulSoup

from src.utils.log_sanitizer import sanitize_url_for_log
from ..base_scraper import BaseScraper, ErrorType, ScrapingException
from ..encoding_utils import create_safe_soup, validate_japanese_content

try:
    from ...utils.retry_utils import AdaptiveConcurrencyController, ExponentialBackoff
    from ...utils.actress_name_filter import ActressNameFilter
except ImportError:  # pragma: no cover
    from src.utils.retry_utils import AdaptiveConcurrencyController, ExponentialBackoff
    from src.utils.actress_name_filter import ActressNameFilter

logger = logging.getLogger(__name__)

_AV_ACTRESS_PATH = "/av-actress/"


class AVWikiScraper(BaseScraper):
    """AV-WIKI 專用爬蟲類"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.base_url = "https://av-wiki.net"

        # AV-WIKI 專用配置
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8,zh;q=0.7",  # 日語優先
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": self.base_url,
            "Cache-Control": "no-cache",
        }

        logger.info("📚 AV-WIKI 爬蟲已初始化")

    async def scrape_url(self, url: str) -> dict[str, Any]:
        """爬取 AV-WIKI URL"""
        try:
            timeout = aiohttp.ClientTimeout(total=30)

            async with aiohttp.ClientSession(
                headers=self.headers, timeout=timeout
            ) as session, session.get(url) as response:
                if response.status == 404:
                    raise ScrapingException(
                        "頁面不存在", ErrorType.CLIENT_ERROR, url, 404
                    )
                elif response.status >= 500:
                    raise ScrapingException(
                        "伺服器錯誤", ErrorType.SERVER_ERROR, url, response.status
                    )
                elif response.status == 429:
                    raise ScrapingException(
                        "請求過於頻繁", ErrorType.RATE_LIMIT_ERROR, url, 429
                    )

                response.raise_for_status()

                # 讀取內容並進行編碼檢測
                content_bytes = await response.read()
                soup, encoding = create_safe_soup(content_bytes)

                logger.debug(f"✅ AV-WIKI 頁面載入成功，編碼: {encoding}")

                # 解析內容
                parsed_data = self.parse_content(str(soup), url)
                parsed_data["source"] = "AV-WIKI"
                parsed_data["encoding"] = encoding

                return parsed_data

        except aiohttp.ClientError as e:
            raise ScrapingException(f"網路連線錯誤: {e}", ErrorType.NETWORK_ERROR, url) from e
        except Exception as e:
            if isinstance(e, ScrapingException):
                raise
            raise ScrapingException(f"未知錯誤: {e}", ErrorType.UNKNOWN_ERROR, url) from e

    def parse_content(self, content: str, url: str) -> dict[str, Any]:
        """解析 AV-WIKI 頁面內容"""
        soup = BeautifulSoup(content, "html.parser")

        try:
            # 檢查是否為搜尋結果頁面
            if "?s=" in url:
                return self._parse_search_results(soup)
            else:
                return self._parse_detail_page(soup)

        except Exception as e:
            logger.error(f"解析 AV-WIKI 內容失敗: {e}")
            raise ScrapingException(f"內容解析錯誤: {e}", ErrorType.PARSING_ERROR, url) from e

    def _parse_search_results(self, soup: BeautifulSoup) -> dict[str, Any]:
        """解析搜尋結果頁面"""
        page_text = soup.get_text()
        if self._is_no_results_page(page_text):
            # 這是一個搜尋無結果頁面，直接返回空結果
            return {
                "search_results": [],
                "total_results": 0,
                "unique_actresses": [],
                "actress_elements": [],
                "found": False,
            }

        actress_elements = self._extract_search_result_actress_elements(soup)
        unique_actresses = [element["name"] for element in actress_elements]

        return {
            "search_results": unique_actresses,
            "total_results": len(unique_actresses),
            "unique_actresses": unique_actresses,
            "actress_elements": actress_elements,
            "found": True,
        }

    @staticmethod
    def _is_no_results_page(page_text: str) -> bool:
        return any(
            keyword in page_text
            for keyword in [
                "見つかりませんでした",
                "No results",
                "検索ワードに一致する記事は見つかりませんでした",
            ]
        )

    @staticmethod
    def _append_unique_actress_element(
        actress_elements: list[dict[str, Any]],
        seen_actresses: set[str],
        name: str | None,
        source: str,
        href: str | None = None,
    ) -> None:
        if not name or name in seen_actresses:
            return

        element: dict[str, Any] = {"name": name, "source": source}
        if href:
            element["href"] = href
        actress_elements.append(element)
        seen_actresses.add(name)

    def _extract_search_result_actress_elements(
        self, soup: BeautifulSoup
    ) -> list[dict[str, Any]]:
        page_text = soup.get_text()
        actress_elements: list[dict[str, Any]] = []
        seen_actresses: set[str] = set()

        extraction_strategies = (
            self._extract_tag_link_actresses,
            self._extract_actress_name_elements,
            self._extract_article_tag_actresses,
            lambda s, _, seen: self._extract_text_scan_actresses(
                page_text, actress_elements, seen
            ),
        )

        for strategy in extraction_strategies:
            strategy(soup, actress_elements, seen_actresses)
            if actress_elements:
                break

        return actress_elements

    def _extract_tag_link_actresses(
        self,
        soup: BeautifulSoup,
        actress_elements: list[dict[str, Any]],
        seen_actresses: set[str],
    ) -> None:
        for link in soup.find_all("a", rel="tag"):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if _AV_ACTRESS_PATH in href:
                self._append_unique_actress_element(
                    actress_elements,
                    seen_actresses,
                    text,
                    "tag_link",
                    href,
                )

    def _extract_actress_name_elements(
        self,
        soup: BeautifulSoup,
        actress_elements: list[dict[str, Any]],
        seen_actresses: set[str],
    ) -> None:
        actress_name_elements = soup.find_all(class_="actress-name")

        for element in actress_name_elements:
            for link in element.find_all("a"):
                href = link.get("href", "")
                text = link.get_text(strip=True)
                if _AV_ACTRESS_PATH not in href:
                    continue

                self._append_unique_actress_element(
                    actress_elements,
                    seen_actresses,
                    text,
                    "actress-name-link",
                    href,
                )

        if actress_elements:
            return

        for element in actress_name_elements:
            actress_name = element.text.strip()
            if self._is_valid_actress_name(actress_name):
                self._append_unique_actress_element(
                    actress_elements,
                    seen_actresses,
                    actress_name,
                    "actress-name-class",
                )

    def _extract_article_tag_actresses(
        self,
        soup: BeautifulSoup,
        actress_elements: list[dict[str, Any]],
        seen_actresses: set[str],
    ) -> None:
        articles = soup.find_all("article") or soup.find_all("div", class_="post")

        for article in articles:
            try:
                for tag in article.find_all("a", rel="tag"):
                    href = tag.get("href", "")
                    text = tag.get_text(strip=True)
                    if _AV_ACTRESS_PATH in href:
                        self._append_unique_actress_element(
                            actress_elements,
                            seen_actresses,
                            text,
                            "article_tag",
                            href,
                        )
            except Exception as e:
                logger.debug(f"解析 AV-WIKI 文章失敗: {e}")

    def _extract_text_scan_actresses(
        self,
        page_text: str,
        actress_elements: list[dict[str, Any]],
        seen_actresses: set[str],
    ) -> None:
        for actress in self._extract_actresses_from_text(page_text):
            self._append_unique_actress_element(
                actress_elements,
                seen_actresses,
                actress,
                "text_scan",
            )
            if len(actress_elements) >= 10:
                break

    def _extract_detail_title(self, soup: BeautifulSoup) -> str | None:
        title_element = soup.find("h1") or soup.find("h2", class_="entry-title") or soup.find("title")
        return title_element.text.strip() if title_element else None

    def _extract_detail_actresses(self, soup: BeautifulSoup, page_text: str) -> list[str]:
        actresses: list[str] = []
        for link in soup.find_all("a", rel="tag"):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if _AV_ACTRESS_PATH in href and text and text not in actresses:
                actresses.append(text)
        if actresses:
            return actresses
        actress_name_elements = soup.find_all(class_="actress-name")
        for element in actress_name_elements:
            for link in element.find_all("a"):
                href = link.get("href", "")
                text = link.get_text(strip=True)
                if _AV_ACTRESS_PATH in href and text and text not in actresses:
                    actresses.append(text)
            if actresses:
                break
            actress_name = element.text.strip()
            if actress_name and self._is_valid_actress_name(actress_name):
                actresses.append(actress_name)
        if actresses:
            return actresses
        return self._extract_actresses_from_text(page_text)

    def _parse_detail_page(self, soup: BeautifulSoup) -> dict[str, Any]:
        """解析詳情頁面"""
        page_text = soup.get_text()
        result = {
            "actresses": self._extract_detail_actresses(soup, page_text),
            "studio": None,
            "studio_code": None,
            "title": self._extract_detail_title(soup),
            "release_date": None,
            "series": None,
            "categories": [],
        }
        result.update(self._extract_studio_info(page_text, result.get("title", "")))
        date_match = re.search(r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})", page_text)
        if date_match:
            result["release_date"] = date_match.group(1)
        result["found"] = True
        return result

    def _select_actress_scan_lines(self, lines: list[str]) -> list[str]:
        potential_actress_lines: list[str] = []
        keywords = (
            "出演",
            "女優",
            "演員",
            "Cast",
            "cast",
            "actress",
            "出演者",
        )

        for i, line in enumerate(lines):
            if any(keyword in line for keyword in keywords):
                start = max(0, i - 1)
                end = min(len(lines), i + 3)
                potential_actress_lines.extend(lines[start:end])

        if potential_actress_lines:
            return potential_actress_lines

        text_lines_count = len(lines)
        upper_bound = int(text_lines_count * 0.3)
        lower_bound = int(text_lines_count * 0.8)
        return lines[:upper_bound] + lines[lower_bound:]

    def _extract_actress_names_from_lines(
        self, lines: list[str], seen: set[str], actresses: list[str]
    ) -> list[str]:
        for line in lines:
            potential_names = re.findall(
                r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{2,8}", line
            )

            for name in potential_names:
                if self._is_valid_actress_name(name) and name not in seen:
                    actresses.append(name)
                    seen.add(name)
                    if len(actresses) >= 15:
                        return actresses

        return actresses

    def _extract_actresses_from_text(self, text: str) -> list[str]:
        """從文本中提取女優名稱（改進版本，更聰明的過濾）"""
        actresses: list[str] = []
        seen: set[str] = set()
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        potential_actress_lines = self._select_actress_scan_lines(lines)
        return self._extract_actress_names_from_lines(
            potential_actress_lines, seen, actresses
        )

    def _extract_studio_info(self, text: str, title: str = "") -> dict[str, Any]:
        """提取片商資訊"""
        studio_info = {"studio": None, "studio_code": None}

        # 從標題中提取片商代碼
        if title:
            code_match = re.search(r"^([A-Z]+)-?\d+", title)
            if code_match:
                studio_info["studio_code"] = code_match.group(1)

        # 從文本中提取片商名稱
        studio_patterns = [
            r"片商[：:]\s*([^\n\r]+)",
            r"製作[：:]\s*([^\n\r]+)",
            r"メーカー[：:]\s*([^\n\r]+)",
            r"(S1|SOD|MOODYZ|PREMIUM|WANZ|FALENO|ATTACKERS|E-BODY|KAWAII|FITCH|MADONNA)",
        ]

        for pattern in studio_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                studio_name = match.group(1).strip()
                if len(studio_name) < 50:  # 合理長度限制
                    studio_info["studio"] = studio_name
                    break

        return studio_info

    def _is_valid_actress_name(self, name: str) -> bool:
        """驗證是否為有效的女優名稱（使用增強過濾器）"""
        return ActressNameFilter.is_valid_actress_name(name)

    async def search_video(self, video_code: str) -> dict[str, Any]:
        """搜尋指定番號的影片"""
        search_url = f"{self.base_url}/?s={quote(video_code)}&post_type=product"

        try:
            # 執行安全爬取
            result = await self.safe_scrape(search_url)

            # 處理搜尋結果
            if "unique_actresses" in result and result["unique_actresses"]:
                actresses = result["unique_actresses"]

                # 驗證內容品質
                content_quality = {}
                for actress in actresses:
                    quality = validate_japanese_content(actress)
                    content_quality[actress] = quality

                return {
                    "video_code": video_code,
                    "search_url": search_url,
                    "actresses": actresses,
                    "content_quality": content_quality,
                    "search_results": result.get("search_results", []),
                }

            # 沒有找到結果
            return {
                "video_code": video_code,
                "search_url": search_url,
                "actresses": [],
                "message": f"未找到番號 {video_code} 的資訊",
            }

        except Exception as e:
            logger.error(f"搜尋 AV-WIKI 影片 {video_code} 失敗: {e}")
            raise ScrapingException(
                f"搜尋失敗: {e}", ErrorType.UNKNOWN_ERROR, search_url
            ) from e

    def _is_temporary_batch_search_error(self, error: Exception) -> bool:
        if isinstance(error, aiohttp.ClientResponseError):
            return error.status in (429, 500, 502, 503, 504)
        return isinstance(error, (TimeoutError, aiohttp.ClientConnectionError))

    def _notify_batch_search_progress(
        self,
        progress_callback: callable | None,
        current_num: int,
        total_count: int,
        code: str,
    ) -> None:
        if not progress_callback:
            return

        try:
            progress_callback(current_num, total_count, code)
        except Exception as e:
            logger.warning(f"進度回調函式執行失敗: {e}")

    async def _search_single_video_batch(
        self,
        code: str,
        total_count: int,
        shared_semaphore: asyncio.Semaphore,
        count_lock: asyncio.Lock,
        progress_callback: callable | None,
        concurrency_controller: AdaptiveConcurrencyController,
        backoff: ExponentialBackoff,
        started_count_ref: list[int],
    ) -> tuple[str, dict[str, Any]]:
        async with shared_semaphore:
            async with count_lock:
                started_count_ref[0] += 1
                current_num = started_count_ref[0]

            self._notify_batch_search_progress(
                progress_callback, current_num, total_count, code
            )

            try:
                search_url = f"{self.base_url}/?s={quote(code)}&post_type=product"
                logger.debug(
                    f"[批次搜尋] 開始搜尋番號 {code}, URL: {sanitize_url_for_log(search_url)}"
                )

                result = await self.scrape_url(search_url)
                concurrency_controller.report_success()
                backoff.reset()
                return code, self._build_batch_search_result(
                    code=code,
                    search_url=search_url,
                    raw_result=result,
                )
            except (
                TimeoutError,
                aiohttp.ClientResponseError,
                aiohttp.ClientConnectionError,
            ) as e:
                error_type = type(e).__name__
                is_temporary = self._is_temporary_batch_search_error(e)

                if is_temporary:
                    concurrency_controller.report_failure()
                    backoff_delay = backoff.next_delay()
                    logger.warning(
                        f"[批次搜尋] 番號 {code} 暫時性錯誤 ({error_type})，"
                        f"退避 {backoff_delay:.1f}s，併發降至 {concurrency_controller.get_concurrency()}"
                    )
                    await asyncio.sleep(backoff_delay)

                error_detail = str(e)
                logger.error(
                    f"[批次搜尋] 番號 {code} 搜尋失敗 - 錯誤類型: {error_type}, 錯誤訊息: {error_detail}"
                )
                return code, self._build_batch_error_result(
                    code, error_detail, error_type
                )
            except Exception as e:
                error_type = type(e).__name__
                error_detail = str(e)
                logger.error(
                    f"[批次搜尋] 番號 {code} 搜尋失敗 - 錯誤類型: {error_type}, 錯誤訊息: {error_detail}"
                )

                import traceback

                logger.debug(
                    f"[批次搜尋] 番號 {code} 完整錯誤堆疊:\n{traceback.format_exc()}"
                )
                return code, self._build_batch_error_result(
                    code, error_detail, error_type
                )

    def _summarize_batch_search_results(
        self, completed_results: list[Any]
    ) -> tuple[dict[str, dict[str, Any]], int, int, int]:
        results: dict[str, dict[str, Any]] = {}
        success_count = 0
        error_count = 0
        no_actress_count = 0

        for item in completed_results:
            if isinstance(item, tuple):
                code, result = item
                results[code] = result

                if "error" in result:
                    error_count += 1
                    logger.debug(
                        f"[批次搜尋統計] {code}: 發生錯誤 - {result.get('error_type', 'Unknown')}"
                    )
                elif result.get("actress_count", 0) > 0:
                    success_count += 1
                else:
                    no_actress_count += 1
            elif isinstance(item, Exception):
                error_count += 1
                logger.error(
                    f"[批次搜尋] 任務執行發生例外: {type(item).__name__} - {item}"
                )

        return results, success_count, error_count, no_actress_count

    async def batch_search_concurrent(
        self,
        video_codes: list[str],
        max_concurrent: int = 15,
        progress_callback: callable | None = None,
    ) -> dict[str, dict[str, Any]]:
        """
        批次併發搜尋多個影片資訊（僅限 AV-WIKI，繞過 rate_limiter）

        根據測試結果，AV-WIKI 沒有速率限制，支援高併發（15 併發 24 請求/秒）。
        此方法直接使用 scrape_url 繞過 rate_limiter，避免誤觸保護機制。
        整合自適應併發控制：連續錯誤時自動降載併發數，恢復後逐步升載。

        Args:
            video_codes: 影片番號列表
            max_concurrent: 最大併發數（預設 15，根據測試結果最佳配置）
            progress_callback: 進度回調函式，接收 (當前數量, 總數量, 番號) 參數

        Returns:
            Dict[番號, 搜尋結果]
        """
        total_count = len(video_codes)
        count_lock = asyncio.Lock()
        concurrency_controller = AdaptiveConcurrencyController(
            initial=max_concurrent,
            minimum=2,
            maximum=max_concurrent,
        )
        backoff = ExponentialBackoff(base_delay=0.5, max_delay=10.0)
        shared_semaphore = asyncio.Semaphore(max_concurrent)
        started_count_ref = [0]

        tasks = [
            self._search_single_video_batch(
                code,
                total_count,
                shared_semaphore,
                count_lock,
                progress_callback,
                concurrency_controller,
                backoff,
                started_count_ref,
            )
            for code in video_codes
        ]

        logger.info(
            f"🚀 開始批次搜尋 {total_count} 個番號，併發數: {max_concurrent}（繞過 rate_limiter）"
        )
        completed_results = await asyncio.gather(*tasks, return_exceptions=True)
        results, success_count, error_count, no_actress_count = (
            self._summarize_batch_search_results(completed_results)
        )

        logger.info(
            f"✅ 批次搜尋完成 - 總計: {total_count}, 成功: {success_count} ({success_count / total_count * 100:.1f}%), "
            f"無女優: {no_actress_count} ({no_actress_count / total_count * 100:.1f}%), "
            f"錯誤: {error_count} ({error_count / total_count * 100:.1f}%)"
        )

        return results

    @staticmethod
    def _deduplicate_actresses(actresses: list[str]) -> list[str]:
        return list(dict.fromkeys(actresses))

    def _extract_batch_actresses(self, raw_result: dict[str, Any]) -> list[str]:
        actresses = raw_result.get("unique_actresses", []) or raw_result.get(
            "actresses", []
        )
        if actresses:
            logger.debug(f"[批次搜尋] 提取到女優: {actresses}")
            return self._deduplicate_actresses(actresses)

        logger.debug(
            "[批次搜尋] 未提取到女優 - unique_actresses: %s, actresses: %s",
            raw_result.get("unique_actresses"),
            raw_result.get("actresses"),
        )
        return []

    def _determine_batch_search_status(
        self, code: str, raw_result: dict[str, Any], actresses: list[str]
    ) -> tuple[str, list[str]]:
        found = raw_result.get("found", True)
        if not found:
            logger.info(f"番號 {code} 在 AV-WIKI 上未找到")
            return "video_not_found", actresses

        if len(actresses) == 0:
            logger.warning(
                f"番號 {code} 已找到頁面但未提取到女優資訊 (返回字段: {list(raw_result.keys())})"
            )
            return "no_actress_found", actresses

        if len(actresses) > 10:
            logger.warning(
                f"番號 {code} 找到 {len(actresses)} 位女優，可能是解析錯誤: {actresses[:10]}..."
            )
            return "search_error", []

        if len(actresses) > 3:
            logger.info(
                f"番號 {code} 找到 {len(actresses)} 位女優，可能需要人工確認: {actresses}"
            )
            return "searched_multiple", actresses

        logger.debug(
            f"[批次搜尋] 番號 {code} 搜尋成功，找到 {len(actresses)} 位女優: {actresses}"
        )
        return "searched_found", actresses

    def _build_batch_search_result(
        self, code: str, search_url: str, raw_result: dict[str, Any]
    ) -> dict[str, Any]:
        logger.debug(f"[批次搜尋] 番號 {code} 返回字段: {list(raw_result.keys())}")
        actresses = self._extract_batch_actresses(raw_result)
        search_status, actresses = self._determine_batch_search_status(
            code, raw_result, actresses
        )
        return {
            "video_code": code,
            "actresses": actresses,
            "source": "AV-WIKI",
            "search_url": search_url,
            "search_status": search_status,
            "actress_count": len(actresses),
        }

    @staticmethod
    def _build_batch_error_result(
        code: str, error_detail: str, error_type: str
    ) -> dict[str, Any]:
        return {
            "video_code": code,
            "actresses": [],
            "error": error_detail,
            "error_type": error_type,
            "source": "AV-WIKI",
        }
