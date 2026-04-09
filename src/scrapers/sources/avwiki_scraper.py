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

from ..base_scraper import BaseScraper, ErrorType, ScrapingException
from ..encoding_utils import create_safe_soup, validate_japanese_content

try:
    from ...utils.retry_utils import AdaptiveConcurrencyController, ExponentialBackoff
    from ...utils.actress_name_filter import ActressNameFilter
except ImportError:  # pragma: no cover
    from src.utils.retry_utils import AdaptiveConcurrencyController, ExponentialBackoff
    from src.utils.actress_name_filter import ActressNameFilter

logger = logging.getLogger(__name__)


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
        seen_actresses = set()
        actress_elements = []

        # 首先檢查是否為「沒有結果」頁面
        page_text = soup.get_text()
        if any(
            keyword in page_text
            for keyword in [
                "見つかりませんでした",  # 日文：未找到
                "No results",
                "検索ワードに一致する記事は見つかりませんでした",  # 沒有找到匹配的文章
            ]
        ):
            # 這是一個搜尋無結果頁面，直接返回空結果
            return {
                "search_results": [],
                "total_results": 0,
                "unique_actresses": [],
                "actress_elements": [],
                "found": False,
            }

        # 方法1: 使用 rel="tag" 且 href 包含 /av-actress/ 的連結（最可靠）
        tag_links = soup.find_all("a", rel="tag")

        for link in tag_links:
            href = link.get("href", "")
            text = link.get_text(strip=True)

            # 只提取女優標籤（href 包含 /av-actress/）
            if "/av-actress/" in href and text and text not in seen_actresses:
                actress_elements.append(
                    {"name": text, "href": href, "source": "tag_link"}
                )
                seen_actresses.add(text)

        # 如果通過標籤沒找到女優，嘗試備選方法
        if not actress_elements:
            # 方法2: 尋找專用的女優名稱元素 (actress-name class 內的 <a> 標籤)
            actress_name_elements = soup.find_all(class_="actress-name")
            if actress_name_elements:
                for element in actress_name_elements:
                    # 首先嘗試從元素內的 <a> 標籤提取
                    actress_links = element.find_all("a")
                    for link in actress_links:
                        href = link.get("href", "")
                        text = link.get_text(strip=True)

                        # 優先使用帶有 /av-actress/ 連結的
                        if (
                            "/av-actress/" in href
                            and text
                            and text not in seen_actresses
                        ):
                            actress_elements.append(
                                {
                                    "name": text,
                                    "href": href,
                                    "source": "actress-name-link",
                                }
                            )
                            seen_actresses.add(text)

                    # 如果沒找到連結，則使用元素的完整文本
                    if not actress_elements:
                        actress_name = element.text.strip()
                        if (
                            actress_name not in seen_actresses
                            and self._is_valid_actress_name(actress_name)
                        ):
                            actress_elements.append(
                                {"name": actress_name, "source": "actress-name-class"}
                            )
                            seen_actresses.add(actress_name)

            # 方法3: 搜尋產品文章中的結構化女優資訊
            if not actress_elements:
                articles = soup.find_all("article") or soup.find_all(
                    "div", class_="post"
                )

                for article in articles:
                    try:
                        # 只尋找帶有 tag 連結的女優
                        article_tags = article.find_all("a", rel="tag")
                        for tag in article_tags:
                            href = tag.get("href", "")
                            text = tag.get_text(strip=True)

                            if "/av-actress/" in href and text not in seen_actresses:
                                actress_elements.append(
                                    {
                                        "name": text,
                                        "href": href,
                                        "source": "article_tag",
                                    }
                                )
                                seen_actresses.add(text)
                    except Exception as e:
                        logger.debug(f"解析 AV-WIKI 文章失敗: {e}")
                        continue

            # 方法4: 通用文本掃描（僅當其他方法都失敗時）
            if not actress_elements:
                # 使用改進的文本掃描，限制提取數量
                extracted = self._extract_actresses_from_text(page_text)
                for actress in extracted:
                    if actress not in seen_actresses:
                        actress_elements.append(
                            {"name": actress, "source": "text_scan"}
                        )
                        seen_actresses.add(actress)
                        # 限制最多 10 位（避免垃圾文本）
                        if len(actress_elements) >= 10:
                            break

        # 轉換為結果格式
        unique_actresses = list(seen_actresses)

        return {
            "search_results": unique_actresses,
            "total_results": len(unique_actresses),
            "unique_actresses": unique_actresses,
            "actress_elements": actress_elements,
            "found": True,
        }

    def _parse_detail_page(self, soup: BeautifulSoup) -> dict[str, Any]:
        """解析詳情頁面"""
        result = {
            "actresses": [],
            "studio": None,
            "studio_code": None,
            "title": None,
            "release_date": None,
            "series": None,
            "categories": [],
        }

        # 提取標題
        title_element = (
            soup.find("h1")
            or soup.find("h2", class_="entry-title")
            or soup.find("title")
        )
        if title_element:
            result["title"] = title_element.text.strip()

        # 從頁面內容中提取資訊
        page_text = soup.get_text()

        # 分層女優名稱提取：優先使用 tag 連結，備選 actress-name class，最後文本掃描
        actresses = []

        # 方法1: 優先使用 tag 連結
        tag_links = soup.find_all("a", rel="tag")
        for link in tag_links:
            href = link.get("href", "")
            text = link.get_text(strip=True)

            # 只提取女優標籤（href 包含 /av-actress/）
            if "/av-actress/" in href and text and text not in actresses:
                actresses.append(text)

        # 方法2: 如果沒找到，嘗試從 actress-name class 提取
        if not actresses:
            actress_name_elements = soup.find_all(class_="actress-name")
            for element in actress_name_elements:
                # 首先嘗試從元素內的 <a> 標籤提取
                actress_links = element.find_all("a")
                for link in actress_links:
                    href = link.get("href", "")
                    text = link.get_text(strip=True)

                    if "/av-actress/" in href and text and text not in actresses:
                        actresses.append(text)

                # 如果沒找到連結，則使用元素的完整文本
                if not actresses:
                    actress_name = element.text.strip()
                    if actress_name and self._is_valid_actress_name(actress_name):
                        actresses.append(actress_name)

        # 方法3: 如果仍沒找到，嘗試文本掃描
        if not actresses:
            actresses = self._extract_actresses_from_text(page_text)

        result["actresses"] = actresses

        # 提取片商資訊
        studio_info = self._extract_studio_info(page_text, result.get("title", ""))
        result.update(studio_info)

        # 提取發行日期
        date_match = re.search(r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})", page_text)
        if date_match:
            result["release_date"] = date_match.group(1)

        result["found"] = True
        return result

    def _extract_actresses_from_text(self, text: str) -> list[str]:
        """從文本中提取女優名稱（改進版本，更聰明的過濾）"""
        actresses = []
        seen = set()

        # 分割成行
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        # 尋找可能包含女優名稱的行（包含「出演」「女優」等關鍵詞）
        potential_actress_lines = []

        for i, line in enumerate(lines):
            # 檢查是否為潛在的女優資訊行
            if any(
                keyword in line
                for keyword in [
                    "出演",
                    "女優",
                    "演員",
                    "Cast",
                    "cast",
                    "actress",
                    "出演者",
                ]
            ):
                # 添加該行及其前後幾行的上下文
                start = max(0, i - 1)
                end = min(len(lines), i + 3)
                potential_actress_lines.extend(lines[start:end])

        # 如果沒有找到關鍵詞行，則掃描整個文本但限制數量
        if not potential_actress_lines:
            # 只掃描文本的前 30% 和後 20%（避免掃描導航和側邊欄）
            text_lines_count = len(lines)
            upper_bound = int(text_lines_count * 0.3)
            lower_bound = int(text_lines_count * 0.8)

            potential_actress_lines = lines[:upper_bound] + lines[lower_bound:]

        # 從候選行中提取名稱
        for line in potential_actress_lines:
            # 尋找可能的女優名稱
            potential_names = re.findall(
                r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{2,8}", line
            )

            for name in potential_names:
                # 驗證並去重
                if self._is_valid_actress_name(name) and name not in seen:
                    actresses.append(name)
                    seen.add(name)

                    # 限制最多 15 位女優
                    if len(actresses) >= 15:
                        return actresses

        return actresses

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

    async def get_actress_info(self, actress_name: str) -> dict[str, Any]:
        """獲取女優資訊"""
        search_url = f"{self.base_url}/?s={quote(actress_name)}"

        try:
            result = await self.safe_scrape(search_url)

            # 處理女優資訊
            works = []
            if "search_results" in result:
                works = result["search_results"]

            return {
                "actress_name": actress_name,
                "total_works": len(works),
                "works": works,
                "search_url": search_url,
            }

        except Exception as e:
            logger.error(f"獲取 AV-WIKI 女優資訊 {actress_name} 失敗: {e}")
            return {
                "actress_name": actress_name,
                "total_works": 0,
                "works": [],
                "error": str(e),
            }

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
        results = {}
        started_count = 0  # 追蹤「開始」的數量
        total_count = len(video_codes)
        count_lock = asyncio.Lock()  # 使用 asyncio.Lock 保護計數器

        # 初始化自適應併發控制器與退避計算器
        concurrency_controller = AdaptiveConcurrencyController(
            initial=max_concurrent,
            minimum=2,
            maximum=max_concurrent,
        )
        backoff = ExponentialBackoff(base_delay=0.5, max_delay=10.0)

        async def search_single_video(code: str) -> tuple[str, dict[str, Any]]:
            """直接搜尋單個影片（繞過 rate_limiter）"""
            nonlocal started_count

            # 動態建立 semaphore（每次取得併發控制器的最新值）
            current_semaphore = asyncio.Semaphore(
                concurrency_controller.get_concurrency()
            )

            async with current_semaphore:
                # 在開始搜尋時就更新進度（而非完成後）
                async with count_lock:
                    started_count += 1
                    current_num = started_count

                # 呼叫進度回調 - 顯示「開始搜尋」
                if progress_callback:
                    try:
                        progress_callback(current_num, total_count, code)
                    except Exception as e:
                        logger.warning(f"進度回調函式執行失敗: {e}")

                try:
                    # 直接使用 scrape_url 繞過 rate_limiter
                    search_url = f"{self.base_url}/?s={quote(code)}&post_type=product"

                    # 記錄開始搜尋
                    logger.debug(f"[批次搜尋] 開始搜尋番號 {code}, URL: {search_url}")

                    result = await self.scrape_url(search_url)

                    # 詳細記錄返回的資料結構
                    logger.debug(
                        f"[批次搜尋] 番號 {code} 返回字段: {list(result.keys())}"
                    )

                    # 處理搜尋結果
                    # 注意：_parse_search_results() 返回 'unique_actresses' 作為女優列表
                    actresses = result.get("unique_actresses", []) or result.get(
                        "actresses", []
                    )

                    # 記錄提取的女優
                    if actresses:
                        logger.debug(f"[批次搜尋] 番號 {code} 提取到女優: {actresses}")

                    # 確保是列表且去重
                    if actresses:
                        actresses = list(set(actresses))
                    else:
                        actresses = []
                        # 詳細記錄為何沒有女優
                        logger.debug(
                            f"[批次搜尋] 番號 {code} 未提取到女優 - unique_actresses: {result.get('unique_actresses')}, actresses: {result.get('actresses')}"
                        )

                    # 品質檢查：如果找到超過 10 位女優，很可能是錯誤解析
                    search_status = "searched_found"

                    # 檢查是否找到影片
                    found = result.get("found", True)

                    if not found:
                        search_status = "video_not_found"
                        logger.info(f"番號 {code} 在 AV-WIKI 上未找到")
                    elif len(actresses) == 0:
                        search_status = "no_actress_found"
                        logger.warning(
                            f"番號 {code} 已找到頁面但未提取到女優資訊 (返回字段: {list(result.keys())})"
                        )
                    elif len(actresses) > 10:
                        logger.warning(
                            f"番號 {code} 找到 {len(actresses)} 位女優，可能是解析錯誤: {actresses[:10]}..."
                        )
                        search_status = "search_error"
                        # 清空結果，避免儲存錯誤資料
                        actresses = []
                    elif len(actresses) > 3:
                        logger.info(
                            f"番號 {code} 找到 {len(actresses)} 位女優，可能需要人工確認: {actresses}"
                        )
                        search_status = "searched_multiple"
                    else:
                        logger.debug(
                            f"[批次搜尋] 番號 {code} 搜尋成功，找到 {len(actresses)} 位女優: {actresses}"
                        )

                    # 搜尋成功，回報給併發控制器
                    concurrency_controller.report_success()
                    backoff.reset()

                    return code, {
                        "video_code": code,
                        "actresses": actresses,
                        "source": "AV-WIKI",
                        "search_url": search_url,
                        "search_status": search_status,
                        "actress_count": len(actresses),
                    }

                except (
                    TimeoutError,
                    aiohttp.ClientResponseError,
                    aiohttp.ClientConnectionError,
                ) as e:
                    # 暫時性錯誤：回報失敗並加退避
                    error_type = type(e).__name__
                    is_temporary = True

                    # 檢查是否為 HTTP 錯誤且狀態碼表示暫時性問題
                    if isinstance(e, aiohttp.ClientResponseError):
                        if e.status in (429, 500, 502, 503, 504):
                            is_temporary = True
                        elif e.status == 404:
                            is_temporary = False

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

                    return code, {
                        "video_code": code,
                        "actresses": [],
                        "error": error_detail,
                        "error_type": error_type,
                        "source": "AV-WIKI",
                    }

                except Exception as e:
                    error_type = type(e).__name__
                    error_detail = str(e)

                    # 詳細記錄錯誤資訊
                    logger.error(
                        f"[批次搜尋] 番號 {code} 搜尋失敗 - 錯誤類型: {error_type}, 錯誤訊息: {error_detail}"
                    )

                    # 記錄完整的堆疊追蹤（僅在 DEBUG 模式）
                    import traceback

                    logger.debug(
                        f"[批次搜尋] 番號 {code} 完整錯誤堆疊:\n{traceback.format_exc()}"
                    )

                    return code, {
                        "video_code": code,
                        "actresses": [],
                        "error": error_detail,
                        "error_type": error_type,
                        "source": "AV-WIKI",
                    }

        # 建立所有任務
        tasks = [search_single_video(code) for code in video_codes]

        # 併發執行所有搜尋
        logger.info(
            f"🚀 開始批次搜尋 {total_count} 個番號，併發數: {max_concurrent}（繞過 rate_limiter）"
        )
        completed_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 整理結果並統計
        success_count = 0
        error_count = 0
        no_actress_count = 0

        for item in completed_results:
            if isinstance(item, tuple):
                code, result = item
                results[code] = result

                # 統計結果
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

        # 詳細的完成報告
        logger.info(
            f"✅ 批次搜尋完成 - 總計: {total_count}, 成功: {success_count} ({success_count / total_count * 100:.1f}%), "
            f"無女優: {no_actress_count} ({no_actress_count / total_count * 100:.1f}%), "
            f"錯誤: {error_count} ({error_count / total_count * 100:.1f}%)"
        )

        return results

    async def search_batch_concurrent(
        self,
        video_codes: list[str],
        max_concurrent: int = 15,
        progress_callback: callable | None = None,
    ) -> dict[str, dict[str, Any]]:
        """相容 wrapper。

        遷移註記：
        1. `batch_search_concurrent` 已是正式主名稱
        2. 保留此舊名稱到下一個 checkpoint，避免外部呼叫端立即中斷
        3. 下一輪若確認無對外依賴，再移除此 wrapper
        """
        return await self.batch_search_concurrent(
            video_codes,
            max_concurrent=max_concurrent,
            progress_callback=progress_callback,
        )
