"""
JAVDB 專用爬蟲
針對 JAVDB.com 優化的爬蟲實作
"""

import logging
import re
from typing import Any
from urllib.parse import quote, urljoin

import aiohttp
from bs4 import BeautifulSoup

from ..base_scraper import BaseScraper, ErrorType, ScrapingException
from ..encoding_utils import create_safe_soup, validate_japanese_content

try:
    from ...utils.actress_name_filter import ActressNameFilter
except ImportError:  # pragma: no cover
    from src.utils.actress_name_filter import ActressNameFilter

logger = logging.getLogger(__name__)


def _parse_retry_after_value(header_value: str | None) -> int | None:
    """解析 Retry-After 標頭秒數，無法解析時返回 None。"""
    if not header_value:
        return None

    try:
        retry_after = int(header_value.strip())
    except (TypeError, ValueError):
        return None

    return retry_after if retry_after > 0 else None


class JAVDBScraper(BaseScraper):
    """JAVDB 專用爬蟲類"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.base_url = "https://javdb.com"
        self.search_url = f"{self.base_url}/search"

        # JAVDB 專用配置
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8,ja;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": self.base_url,
            "Cache-Control": "no-cache",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
        }

        logger.info("🎬 JAVDB 爬蟲已初始化")

    async def scrape_url(self, url: str) -> dict[str, Any]:
        """爬取 JAVDB URL"""
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
                    retry_after = _parse_retry_after_value(
                        response.headers.get("Retry-After")
                    )
                    raise ScrapingException(
                        "請求過於頻繁",
                        ErrorType.RATE_LIMIT_ERROR,
                        url,
                        429,
                        retry_after=retry_after,
                    )

                response.raise_for_status()

                # 讀取內容並進行編碼檢測
                content_bytes = await response.read()
                soup, encoding = create_safe_soup(content_bytes)

                logger.debug(f"✅ JAVDB 頁面載入成功，編碼: {encoding}")

                # 解析內容
                parsed_data = self.parse_content(str(soup), url)
                parsed_data["source"] = "JAVDB"
                parsed_data["encoding"] = encoding

                return parsed_data

        except aiohttp.ClientError as e:
            raise ScrapingException(f"網路連線錯誤: {e}", ErrorType.NETWORK_ERROR, url) from e
        except Exception as e:
            if isinstance(e, ScrapingException):
                raise
            raise ScrapingException(f"未知錯誤: {e}", ErrorType.UNKNOWN_ERROR, url) from e

    def parse_content(self, content: str, url: str) -> dict[str, Any]:
        """解析 JAVDB 頁面內容"""
        soup = BeautifulSoup(content, "html.parser")

        try:
            # 檢查是否為搜尋結果頁面
            if "/search?" in url:
                return self._parse_search_results(soup)
            else:
                return self._parse_detail_page(soup)

        except Exception as e:
            logger.error(f"解析 JAVDB 內容失敗: {e}")
            raise ScrapingException(f"內容解析錯誤: {e}", ErrorType.PARSING_ERROR, url) from e

    def _parse_search_results(self, soup: BeautifulSoup) -> dict[str, Any]:
        """解析搜尋結果頁面"""
        results = []

        # 查找影片卡片
        movie_items = soup.find_all("div", class_="item")

        for item in movie_items:
            try:
                # 提取基本資訊
                link_element = item.find("a")
                if not link_element:
                    continue

                detail_url = urljoin(self.base_url, link_element.get("href"))

                # 提取標題
                title_element = item.find("div", class_="video-title")
                title = title_element.text.strip() if title_element else ""

                # 提取演員資訊
                actresses = []
                actor_elements = item.find_all("a", href=re.compile(r"/actors/"))
                for actor in actor_elements:
                    actress_name = actor.text.strip()
                    if actress_name and self._is_valid_actress_name(actress_name):
                        actresses.append(actress_name)

                # 提取片商資訊
                studio = None
                studio_element = item.find("a", href=re.compile(r"/makers/"))
                if studio_element:
                    studio = studio_element.text.strip()

                # 提取發布日期
                date_element = item.find("div", class_="meta")
                release_date = None
                if date_element:
                    date_text = date_element.text
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", date_text)
                    if date_match:
                        release_date = date_match.group(1)

                if actresses or title:
                    results.append(
                        {
                            "title": title,
                            "actresses": actresses,
                            "studio": studio,
                            "release_date": release_date,
                            "detail_url": detail_url,
                        }
                    )

            except Exception as e:
                logger.warning(f"解析搜尋結果項目失敗: {e}")
                continue

        return {"search_results": results, "total_results": len(results)}

    def _parse_detail_page(self, soup: BeautifulSoup) -> dict[str, Any]:
        """解析詳情頁面"""
        result = {
            "actresses": [],
            "studio": None,
            "studio_code": None,
            "title": None,
            "release_date": None,
            "duration": None,
            "director": None,
            "series": None,
            "rating": None,
            "categories": [],
            "cover_url": None,
        }

        # 提取標題
        title_element = soup.find("h2", class_="title")
        if title_element:
            result["title"] = title_element.text.strip()

        # 提取封面圖片
        cover_element = soup.find("img", class_="video-cover")
        if cover_element:
            result["cover_url"] = cover_element.get("src")

        result.update(
            self._extract_detail_panel_data(soup.find_all("div", class_="panel-block"))
        )

        # 提取評分
        result["rating"] = self._extract_rating(soup.find("span", class_="score"))

        # 從標題中提取片商代碼
        if result["title"]:
            code_match = re.search(r"^([A-Z]+)-?\d+", result["title"])
            if code_match:
                result["studio_code"] = code_match.group(1)

        return result

    def _extract_detail_panel_data(
        self, info_panels: list[BeautifulSoup]
    ) -> dict[str, Any]:
        detail = {
            "actresses": [],
            "studio": None,
            "release_date": None,
            "duration": None,
            "director": None,
            "series": None,
            "categories": [],
        }

        for panel in info_panels:
            try:
                label_element = panel.find("strong")
                if not label_element:
                    continue

                label = label_element.text.strip()
                self._apply_detail_panel(detail, label, panel)
            except Exception as e:
                logger.warning(f"解析詳情面板失敗: {e}")

        return detail

    def _apply_detail_panel(
        self, detail: dict[str, Any], label: str, panel: BeautifulSoup
    ) -> None:
        if "演員" in label or "Actor" in label:
            detail["actresses"].extend(self._extract_panel_actresses(panel))
        elif "片商" in label or "Maker" in label:
            detail["studio"] = self._extract_first_link_text(panel, r"/makers/")
        elif "發行日期" in label or "Release Date" in label:
            detail["release_date"] = self._extract_panel_date(panel.text)
        elif "時長" in label or "Duration" in label:
            detail["duration"] = self._extract_panel_duration(panel.text)
        elif "導演" in label or "Director" in label:
            detail["director"] = self._extract_first_link_text(panel)
        elif "系列" in label or "Series" in label:
            detail["series"] = self._extract_first_link_text(panel)
        elif "類別" in label or "Genre" in label:
            detail["categories"].extend(
                self._extract_panel_categories(panel, r"/genres/")
            )

    def _extract_panel_actresses(self, panel: BeautifulSoup) -> list[str]:
        actresses = []
        for link in panel.find_all("a", href=re.compile(r"/actors/")):
            actress_name = link.text.strip()
            if self._is_valid_actress_name(actress_name):
                actresses.append(actress_name)
        return actresses

    @staticmethod
    def _extract_first_link_text(
        panel: BeautifulSoup, href_pattern: str | None = None
    ) -> str | None:
        link = (
            panel.find("a", href=re.compile(href_pattern))
            if href_pattern
            else panel.find("a")
        )
        return link.text.strip() if link else None

    @staticmethod
    def _extract_panel_date(date_text: str) -> str | None:
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", date_text)
        return date_match.group(1) if date_match else None

    @staticmethod
    def _extract_panel_duration(duration_text: str) -> str | None:
        duration_match = re.search(r"(\d+)", duration_text)
        return f"{duration_match.group(1)}分鐘" if duration_match else None

    @staticmethod
    def _extract_panel_categories(
        panel: BeautifulSoup, href_pattern: str
    ) -> list[str]:
        return [
            link.text.strip()
            for link in panel.find_all("a", href=re.compile(href_pattern))
            if link.text.strip()
        ]

    @staticmethod
    def _extract_rating(rating_element: BeautifulSoup | None) -> float | None:
        if not rating_element:
            return None

        try:
            rating_text = rating_element.text.strip()
            rating_match = re.search(r"([\d.]+)", rating_text)
            if rating_match:
                return float(rating_match.group(1))
        except (TypeError, ValueError) as e:
            logger.debug(f"JAVDB 評分解析失敗，略過 rating 欄位: {e}")

        return None

    def _is_valid_actress_name(self, name: str) -> bool:
        """驗證是否為有效的女優名稱（使用增強過濾器）"""
        return ActressNameFilter.is_valid_actress_name(name)

    async def search_video(self, video_code: str) -> dict[str, Any]:
        """搜尋指定番號的影片"""
        search_url = f"{self.search_url}?q={quote(video_code)}&f=all"

        try:
            # 執行安全爬取
            result = await self.safe_scrape(search_url)

            # 如果有搜尋結果，取第一個結果的詳情
            if "search_results" in result and result["search_results"]:
                first_result = result["search_results"][0]

                # 如果有詳情頁面URL，進一步獲取詳細資訊
                if "detail_url" in first_result:
                    detail_result = await self.safe_scrape(first_result["detail_url"])

                    # 合併搜尋結果和詳情
                    detail_result.update(
                        {"video_code": video_code, "search_url": search_url}
                    )

                    # 驗證內容品質
                    if detail_result.get("title"):
                        content_quality = validate_japanese_content(
                            detail_result["title"]
                        )
                        detail_result["content_quality"] = content_quality

                    return detail_result
                else:
                    # 直接返回搜尋結果
                    first_result.update(
                        {"video_code": video_code, "search_url": search_url}
                    )
                    return first_result

            # 沒有找到結果
            return {
                "video_code": video_code,
                "search_url": search_url,
                "actresses": [],
                "message": f"未找到番號 {video_code} 的資訊",
            }

        except Exception as e:
            logger.error(f"搜尋 JAVDB 影片 {video_code} 失敗: {e}")
            raise ScrapingException(
                f"搜尋失敗: {e}", ErrorType.UNKNOWN_ERROR, search_url
            ) from e

    async def get_actress_info(self, actress_name: str) -> dict[str, Any]:
        """獲取女優資訊"""
        search_url = f"{self.search_url}?q={quote(actress_name)}&f=actor"

        try:
            result = await self.safe_scrape(search_url)

            # 整理女優作品資訊
            if "search_results" in result:
                works = result["search_results"]

                # 統計片商分佈
                studio_count = {}
                for work in works:
                    studio = work.get("studio")
                    if studio:
                        studio_count[studio] = studio_count.get(studio, 0) + 1

                return {
                    "actress_name": actress_name,
                    "total_works": len(works),
                    "works": works,
                    "studio_distribution": studio_count,
                    "search_url": search_url,
                }

            return {
                "actress_name": actress_name,
                "total_works": 0,
                "works": [],
                "studio_distribution": {},
                "search_url": search_url,
            }

        except Exception as e:
            logger.error(f"獲取 JAVDB 女優資訊 {actress_name} 失敗: {e}")
            raise ScrapingException(
                f"獲取女優資訊失敗: {e}", ErrorType.UNKNOWN_ERROR, search_url
            ) from e
