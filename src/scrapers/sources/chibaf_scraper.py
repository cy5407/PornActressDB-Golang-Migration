"""
CHIBA-F 專用爬蟲
針對 chiba-f.net 優化的爬蟲實作
"""

import logging
import re
from typing import Any
from urllib.parse import quote

import aiohttp
from bs4 import BeautifulSoup

from ..base_scraper import BaseScraper, ErrorType, ScrapingException
from ..encoding_utils import create_safe_soup, validate_japanese_content

logger = logging.getLogger(__name__)


class ChibaFScraper(BaseScraper):
    """CHIBA-F 專用爬蟲類"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.base_url = "https://chiba-f.net"
        self.search_url = f"{self.base_url}/search/"

        # CHIBA-F 專用配置
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8,zh;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": self.base_url,
            "Cache-Control": "no-cache",
        }

        logger.info("🌸 CHIBA-F 爬蟲已初始化")

    async def scrape_url(self, url: str) -> dict[str, Any]:
        """爬取 CHIBA-F URL"""
        try:
            timeout = aiohttp.ClientTimeout(total=30)

            async with aiohttp.ClientSession(
                headers=self.headers, timeout=timeout
            ) as session:
                async with session.get(url) as response:
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

                    logger.debug(f"✅ CHIBA-F 頁面載入成功，編碼: {encoding}")

                    # 解析內容
                    parsed_data = self.parse_content(str(soup), url)
                    parsed_data["source"] = "CHIBA-F"
                    parsed_data["encoding"] = encoding

                    return parsed_data

        except aiohttp.ClientError as e:
            raise ScrapingException(f"網路連線錯誤: {e}", ErrorType.NETWORK_ERROR, url)
        except Exception as e:
            if isinstance(e, ScrapingException):
                raise
            raise ScrapingException(f"未知錯誤: {e}", ErrorType.UNKNOWN_ERROR, url)

    def parse_content(self, content: str, url: str) -> dict[str, Any]:
        """解析 CHIBA-F 頁面內容"""
        soup = BeautifulSoup(content, "html.parser")

        try:
            # 檢查是否為搜尋結果頁面
            if "/search/" in url:
                return self._parse_search_results(soup)
            else:
                return self._parse_detail_page(soup)

        except Exception as e:
            logger.error(f"解析 CHIBA-F 內容失敗: {e}")
            raise ScrapingException(f"內容解析錯誤: {e}", ErrorType.PARSING_ERROR, url)

    def _parse_search_results(self, soup: BeautifulSoup) -> dict[str, Any]:
        """解析搜尋結果頁面"""
        results = []

        # 查找產品區塊
        product_divs = soup.find_all("div", class_="product-div")

        for product_div in product_divs:
            try:
                result = self._extract_product_info(product_div)
                if result and result.get("actresses"):
                    results.append(result)

            except Exception as e:
                logger.warning(f"解析 CHIBA-F 產品區塊失敗: {e}")
                continue

        # 如果沒有找到 product-div，嘗試其他結構
        if not results:
            # 查找其他可能的產品容器
            containers = (
                soup.find_all("div", class_="item")
                or soup.find_all("div", class_="video")
                or soup.find_all("article")
            )

            for container in containers:
                try:
                    result = self._extract_generic_info(container)
                    if result and result.get("actresses"):
                        results.append(result)

                except Exception as e:
                    logger.warning(f"解析 CHIBA-F 通用容器失敗: {e}")
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
            "series": None,
            "duration": None,
        }

        # 提取標題
        title_element = soup.find("h1") or soup.find("h2") or soup.find("title")
        if title_element:
            result["title"] = title_element.text.strip()

        # 查找詳細資訊區塊
        info_sections = soup.find_all(["div", "section", "table"])

        for section in info_sections:
            try:
                section_text = section.get_text()

                # 提取女優名稱
                actress_names = self._extract_actresses_from_section(section)
                for name in actress_names:
                    if name not in result["actresses"]:
                        result["actresses"].append(name)

                # 提取其他資訊
                if "片商" in section_text or "メーカー" in section_text:
                    studio = self._extract_studio_from_section(section)
                    if studio:
                        result["studio"] = studio

                if "發行" in section_text or "発売" in section_text:
                    date = self._extract_date_from_section(section)
                    if date:
                        result["release_date"] = date

                if "系列" in section_text or "シリーズ" in section_text:
                    series = self._extract_series_from_section(section)
                    if series:
                        result["series"] = series

            except Exception as e:
                logger.warning(f"解析 CHIBA-F 詳情區塊失敗: {e}")
                continue

        # 從標題提取片商代碼
        if result["title"]:
            code_match = re.search(r"^([A-Z]+)-?\d+", result["title"])
            if code_match:
                result["studio_code"] = code_match.group(1)

        return result

    def _extract_product_info(self, product_div) -> dict[str, Any]:
        """從產品區塊提取資訊"""
        result = {
            "actresses": [],
            "studio": None,
            "studio_code": None,
            "release_date": None,
            "title": None,
        }

        try:
            # 提取女優名稱 (通常在 fw-bold span 中)
            actress_span = product_div.find("span", class_="fw-bold")
            if actress_span:
                actress_name = actress_span.text.strip()
                if self._is_valid_actress_name(actress_name):
                    result["actresses"] = [actress_name]

            # 提取系列/片商資訊
            series_link = product_div.find("a", href=re.compile(r"../series/"))
            if series_link:
                result["studio"] = series_link.text.strip()
                # 從 href 提取片商代碼
                href = series_link.get("href", "")
                if "../series/" in href:
                    result["studio_code"] = href.replace("../series/", "").strip()

            # 提取番號
            pno_element = product_div.find("div", class_="pno")
            if pno_element:
                pno_text = pno_element.text.strip()
                result["title"] = pno_text

                # 從番號提取片商代碼
                if not result["studio_code"]:
                    code_match = re.search(r"^([A-Z]+)", pno_text)
                    if code_match:
                        result["studio_code"] = code_match.group(1)

            # 提取發行日期
            date_span = product_div.find("span", class_="start_date")
            if date_span:
                result["release_date"] = date_span.text.strip()

        except Exception as e:
            logger.warning(f"提取 CHIBA-F 產品資訊失敗: {e}")

        return result

    def _extract_generic_info(self, container) -> dict[str, Any]:
        """從通用容器提取資訊"""
        result = {"actresses": [], "studio": None, "title": None}

        try:
            container_text = container.get_text()

            # 提取女優名稱
            actresses = self._extract_actresses_from_text(container_text)
            result["actresses"] = actresses

            # 提取標題
            title_element = container.find(["h1", "h2", "h3", "h4"])
            if title_element:
                result["title"] = title_element.text.strip()

        except Exception as e:
            logger.warning(f"提取 CHIBA-F 通用資訊失敗: {e}")

        return result

    def _extract_actresses_from_section(self, section) -> list[str]:
        """從區塊中提取女優名稱"""
        actresses = []

        # 查找加粗文本（可能是女優名稱）
        bold_elements = section.find_all(
            ["b", "strong", "span"], class_=["fw-bold", "actress", "performer"]
        )

        for element in bold_elements:
            text = element.text.strip()
            if self._is_valid_actress_name(text):
                actresses.append(text)

        # 從純文本中提取
        section_text = section.get_text()
        text_actresses = self._extract_actresses_from_text(section_text)

        for actress in text_actresses:
            if actress not in actresses:
                actresses.append(actress)

        return actresses

    def _extract_actresses_from_text(self, text: str) -> list[str]:
        """從文本中提取女優名稱"""
        actresses = []

        # 日文姓名模式
        name_patterns = [
            r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{2,8}\s*[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{2,8}",  # 姓名組合
            r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{3,15}",  # 單一名稱
        ]

        for pattern in name_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                clean_name = match.strip()
                if (
                    self._is_valid_actress_name(clean_name)
                    and clean_name not in actresses
                ):
                    actresses.append(clean_name)

        return actresses

    def _extract_studio_from_section(self, section) -> str | None:
        """從區塊中提取片商名稱"""
        # 查找片商連結
        studio_link = section.find("a", href=re.compile(r"maker|studio|series"))
        if studio_link:
            return studio_link.text.strip()

        # 從文本中提取
        section_text = section.get_text()
        studio_match = re.search(r"(?:片商|メーカー)[：:]\s*([^\n\r]+)", section_text)
        if studio_match:
            return studio_match.group(1).strip()

        return None

    def _extract_date_from_section(self, section) -> str | None:
        """從區塊中提取日期"""
        section_text = section.get_text()
        date_patterns = [
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            r"(\d{4}\.\d{1,2}\.\d{1,2})",
            r"(\d{4}年\d{1,2}月\d{1,2}日)",
        ]

        for pattern in date_patterns:
            match = re.search(pattern, section_text)
            if match:
                return match.group(1)

        return None

    def _extract_series_from_section(self, section) -> str | None:
        """從區塊中提取系列名稱"""
        # 查找系列連結
        series_link = section.find("a", href=re.compile(r"series"))
        if series_link:
            return series_link.text.strip()

        # 從文本中提取
        section_text = section.get_text()
        series_match = re.search(r"(?:系列|シリーズ)[：:]\s*([^\n\r]+)", section_text)
        if series_match:
            return series_match.group(1).strip()

        return None

    def _is_valid_actress_name(self, name: str) -> bool:
        """驗證是否為有效的女優名稱"""
        if not name or len(name) < 2 or len(name) > 25:
            return False

        # 排除常見的非女優關鍵詞
        exclude_keywords = [
            "サンプル",
            "ダウンロード",
            "プレビュー",
            "レビュー",
            "動画",
            "検索",
            "件",
            "結果",
            "ページ",
            "メニュー",
            "ログイン",
            "sample",
            "download",
            "preview",
            "review",
            "video",
            "search",
            "result",
            "page",
            "menu",
            "login",
        ]

        name_lower = name.lower()
        if any(keyword in name_lower for keyword in exclude_keywords):
            return False

        # 檢查是否包含數字過多
        if len(re.findall(r"\d", name)) > len(name) // 3:
            return False

        # 必須包含日文字符
        if re.search(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]", name):
            return True

        return False

    async def search_video(self, video_code: str) -> dict[str, Any]:
        """搜尋指定番號的影片"""
        search_url = f"{self.search_url}?keyword={quote(video_code)}"

        try:
            # 執行安全爬取
            result = await self.safe_scrape(search_url)

            # 查找匹配的結果
            if "search_results" in result and result["search_results"]:
                # 尋找最匹配的結果
                best_match = None
                for item in result["search_results"]:
                    title = item.get("title", "")
                    if video_code.upper() in title.upper():
                        best_match = item
                        break

                if best_match:
                    # 驗證內容品質
                    content_quality = {}
                    for actress in best_match.get("actresses", []):
                        quality = validate_japanese_content(actress)
                        content_quality[actress] = quality

                    best_match.update(
                        {
                            "video_code": video_code,
                            "search_url": search_url,
                            "content_quality": content_quality,
                        }
                    )

                    return best_match
                else:
                    # 返回第一個結果
                    first_result = result["search_results"][0]
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
            logger.error(f"搜尋 CHIBA-F 影片 {video_code} 失敗: {e}")
            raise ScrapingException(
                f"搜尋失敗: {e}", ErrorType.UNKNOWN_ERROR, search_url
            )

    async def get_actress_info(self, actress_name: str) -> dict[str, Any]:
        """獲取女優資訊"""
        search_url = f"{self.search_url}?keyword={quote(actress_name)}"

        try:
            result = await self.safe_scrape(search_url)

            # 處理女優作品
            works = []
            if "search_results" in result:
                # 篩選包含該女優的作品
                for item in result["search_results"]:
                    actresses = item.get("actresses", [])
                    if any(actress_name in actress for actress in actresses):
                        works.append(item)

            return {
                "actress_name": actress_name,
                "total_works": len(works),
                "works": works,
                "search_url": search_url,
            }

        except Exception as e:
            logger.error(f"獲取 CHIBA-F 女優資訊 {actress_name} 失敗: {e}")
            raise ScrapingException(
                f"獲取女優資訊失敗: {e}", ErrorType.UNKNOWN_ERROR, search_url
            )
