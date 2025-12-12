"""
安全的 JAVDB 搜尋器 - 整合反爬蟲策略
"""

import json
import logging
import random
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class SafeJAVDBSearcher:
    """安全的 JAVDB 搜尋器類別"""

    def __init__(self, cache_dir: str = None):
        self.cache_dir = (
            Path(cache_dir)
            if cache_dir
            else Path(__file__).parent.parent.parent / "data"
        )
        self.cache_file = self.cache_dir / "javdb_search_cache.json"
        self.stats_file = self.cache_dir / "javdb_stats.json"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 載入快取和統計資料
        self.load_cache()
        self.load_stats()

        # 安全參數設定
        self.request_count = 0
        self.max_requests_per_session = 25  # 降低session請求數限制
        self.daily_limit = 80  # 降低每日限制更安全
        self.min_delay = 3.0  # 增加最小延遲
        self.max_delay = 7.0  # 增加最大延遲

        # 檢查當日統計
        self._check_daily_reset()

        # 線程鎖保護共享資源
        self._lock = threading.Lock()

        # 初始化會話
        self.create_session()

        logger.info(f"🛡️ JAVDB 安全搜尋器已初始化 - 每日限制: {self.daily_limit}")

    def _check_daily_reset(self):
        """檢查是否需要重置每日計數"""
        current_date = date.today().isoformat()
        if self.stats.get("last_date") != current_date:
            self.stats["last_date"] = current_date
            self.stats["today_count"] = 0
            self.save_stats()
            logger.info(f"📅 每日統計已重置 - {current_date}")

    def load_cache(self):
        """載入快取資料"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.debug(f"📦 已載入 {len(self.cache)} 個快取項目")
            except Exception as e:
                logger.warning(f"載入快取失敗: {e}")
                self.cache = {}
        else:
            self.cache = {}

    def save_cache(self):
        """儲存快取資料"""
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
            logger.debug(f"💾 已儲存 {len(self.cache)} 個快取項目")
        except Exception as e:
            logger.error(f"儲存快取失敗: {e}")

    def load_stats(self):
        """載入統計資料"""
        if self.stats_file.exists():
            try:
                with open(self.stats_file, encoding="utf-8") as f:
                    self.stats = json.load(f)
            except Exception as e:
                logger.warning(f"載入統計失敗: {e}")
                self.stats = {}
        else:
            self.stats = {}

        # 確保必要的統計欄位存在
        if "today_count" not in self.stats:
            self.stats["today_count"] = 0
        if "total_requests" not in self.stats:
            self.stats["total_requests"] = 0
        if "successful_searches" not in self.stats:
            self.stats["successful_searches"] = 0

    def save_stats(self):
        """儲存統計資料"""
        try:
            with open(self.stats_file, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"儲存統計失敗: {e}")

    def create_session(self):
        """建立模擬真實瀏覽器的 session"""
        user_agents = [
            # Chrome on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            # Chrome on macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            # Safari on macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            # Firefox on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
            # Edge on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        ]

        headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en-US;q=0.7,en;q=0.6",
            # 暫時移除 br 壓縮以避免解碼問題
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        # 隨機添加一些可選標頭
        if random.choice([True, False]):
            headers["DNT"] = "1"

        if random.choice([True, False]):
            headers["Referer"] = "https://www.google.com/"

        self.session = httpx.Client(
            headers=headers,
            follow_redirects=True,
            timeout=30.0,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            # 確保正確處理壓縮回應
            default_encoding="utf-8",
        )

        self.request_count = 0
        logger.debug(f"🔄 已建立新的會話 - User-Agent: {headers['User-Agent'][:50]}...")

    def safe_request(self, url: str, retry_count: int = 0) -> httpx.Response | None:
        """安全的 HTTP 請求方法"""
        with self._lock:
            # 檢查每日限制
            self._check_daily_reset()
            if self.stats["today_count"] >= self.daily_limit:
                logger.warning(f"⚠️ 已達每日 JAVDB 請求限制 ({self.daily_limit})")
                return None

            # 檢查 session 請求次數
            if self.request_count >= self.max_requests_per_session:
                logger.info("🔄 重新建立 JAVDB session")
                self.create_session()

            try:
                # 智能隨機延遲
                base_delay = random.uniform(self.min_delay, self.max_delay)
                # 如果是重試，增加額外延遲
                if retry_count > 0:
                    base_delay += retry_count * 2.0

                logger.debug(f"⏱️ 等待 {base_delay:.1f} 秒...")
                time.sleep(base_delay)

                # 執行請求
                response = self.session.get(url)
                self.request_count += 1
                self.stats["today_count"] += 1
                self.stats["total_requests"] += 1

                # 處理不同的 HTTP 狀態碼
                if response.status_code == 429:  # Too Many Requests
                    if retry_count < 3:
                        wait_time = 60 + random.uniform(30, 90)  # 1-2.5分鐘
                        logger.warning(
                            f"⚠️ 收到 429 錯誤，等待 {wait_time:.1f} 秒後重試..."
                        )
                        time.sleep(wait_time)
                        return self.safe_request(url, retry_count + 1)
                    else:
                        logger.error("❌ 重試次數過多，放棄請求")
                        return None

                elif response.status_code == 403:  # Forbidden
                    logger.warning("⚠️ 收到 403 錯誤，可能被暫時封鎖")
                    if retry_count < 2:
                        # 重新建立 session 並等待更長時間
                        self.create_session()
                        wait_time = 120 + random.uniform(60, 180)  # 2-5分鐘
                        logger.info(f"⏳ 等待 {wait_time:.1f} 秒後重試...")
                        time.sleep(wait_time)
                        return self.safe_request(url, retry_count + 1)
                    return None

                elif response.status_code != 200:
                    logger.warning(f"⚠️ JAVDB 請求失敗: {response.status_code}")
                    return None

                logger.debug(f"✅ JAVDB 請求成功: {response.status_code}")
                return response

            except httpx.TimeoutException:
                logger.warning("⏰ JAVDB 請求超時")
                if retry_count < 2:
                    return self.safe_request(url, retry_count + 1)
                return None

            except httpx.ConnectError:
                logger.warning("🔌 JAVDB 連線失敗")
                if retry_count < 2:
                    time.sleep(10 + retry_count * 5)
                    return self.safe_request(url, retry_count + 1)
                return None

            except Exception as e:
                logger.error(f"❌ JAVDB 請求過程中出錯: {e}")
                if retry_count < 1:
                    time.sleep(5)
                    return self.safe_request(url, retry_count + 1)
                return None

    def clear_cache_for_code(self, video_id: str) -> bool:
        """清除特定番號的快取 - 用於二次搜尋"""
        cache_key = f"javdb_{video_id.upper()}"
        if cache_key in self.cache:
            del self.cache[cache_key]
            self.save_cache()
            logger.info(f"🧹 已清除 {video_id} 的 JAVDB 快取")
            return True
        return False

    def search_javdb(self, video_id: str) -> dict[str, Any] | None:
        """在 JAVDB 搜尋影片資訊"""
        if not video_id:
            return None
            # 檢查快取
        cache_key = f"javdb_{video_id.upper()}"
        if cache_key in self.cache:
            logger.debug(f"📋 從快取取得 {video_id} 的 JAVDB 資料")
            return self.cache[cache_key]

        try:
            # 構建搜尋 URL
            search_url = f"https://javdb.com/search?q={quote(video_id)}&f=all"
            # 執行搜尋
            response = self.safe_request(search_url)
            if not response:
                return None

            # JAVDB 使用標準 UTF-8 編碼，不需要特殊處理
            soup = BeautifulSoup(response.text, "html.parser")

            # 尋找影片連結 - 使用實際的JAVDB結構
            video_links = soup.select('a[href*="/v/"]')

            if not video_links:
                logger.info(f"🔍 JAVDB 未找到番號 {video_id} 的結果")
                return None

            logger.debug(f"🎬 找到 {len(video_links)} 個影片連結")

            # 尋找最匹配的結果
            best_match_url = None

            # 檢查每個連結對應的影片，看是否匹配番號
            for link in video_links:
                href = link.get("href")
                if not href:
                    continue

                # 檢查連結周圍的文字或標題是否包含番號
                link_text = link.get_text(strip=True)
                title_attr = link.get("title", "")

                # 檢查是否匹配
                text_to_check = f"{link_text} {title_attr}".upper()
                if video_id.upper() in text_to_check:
                    best_match_url = href
                    logger.debug(f"🎯 找到匹配的影片連結: {href} (文字: {link_text})")
                    break
            # 如果沒有找到完全匹配的，使用第一個結果
            if not best_match_url:
                best_match_url = video_links[0].get("href")
                logger.debug(f"🎲 使用第一個搜尋結果: {best_match_url}")

            if not best_match_url:
                logger.warning(f"⚠️ 無法獲取 {video_id} 的詳情頁面連結")
                return None

            detail_url = urljoin("https://javdb.com", best_match_url)

            # 訪問詳情頁面
            detail_response = self.safe_request(detail_url)
            if not detail_response:
                return None

            # 解析詳情頁面 - 使用編碼增強器
            info = self._parse_detail_page(detail_response, video_id, detail_url)

            if info:
                # 儲存到快取
                self.cache[cache_key] = info
                self.save_cache()
                self.stats["successful_searches"] += 1
                self.save_stats()

                logger.info(f"✅ JAVDB 找到番號 {video_id} 的資料")
                return info

            return None

        except Exception as e:
            logger.error(f"❌ 搜尋 {video_id} 時出錯: {e}")
            return None

    def _parse_detail_page(
        self, response: httpx.Response, video_id: str, url: str
    ) -> dict[str, Any] | None:
        """解析 JAVDB 詳情頁面"""
        try:
            # JAVDB 使用標準 UTF-8 編碼，不需要特殊處理
            soup = BeautifulSoup(response.text, "html.parser")

            if soup is None:
                logger.warning(f"無法解析 JAVDB 詳情頁面: {url}")
                return None

            info = {
                "code": video_id.upper(),
                "source": "JAVDB (安全增強版)",
                "actresses": [],
                "studio": None,
                "studio_code": None,
                "release_date": None,
                "title": None,
                "duration": None,
                "director": None,
                "series": None,
                "rating": None,
                "categories": [],
            }

            # 提取標題
            title_element = soup.select_one("h2.title")
            if title_element:
                info["title"] = title_element.text.strip()
            # 提取詳細資訊 - 適配新的 HTML 結構
            info_panels = soup.select(".panel-block")

            for panel in info_panels:
                strong_element = panel.select_one("strong")
                if not strong_element:
                    continue

                label = strong_element.text.strip().rstrip(":：")

                # 對於演員資訊，直接在同一個 panel 中尋找
                if label == "演員":
                    # 提取女優名稱（只取女性演員）
                    actresses = []
                    # 尋找演員連結和性別符號
                    actress_links = panel.select('a[href*="/actors/"]')
                    for link in actress_links:
                        # 檢查緊跟著的性別符號
                        next_element = link.find_next_sibling()
                        if (
                            next_element
                            and next_element.name == "strong"
                            and next_element.get("class")
                            and "symbol" in next_element.get("class")
                            and "female" in next_element.get("class")
                        ) or (
                            next_element
                            and next_element.name == "strong"
                            and "♀" in next_element.text
                        ):
                            actress_name = link.text.strip()
                            if actress_name:
                                actresses.append(actress_name)
                    info["actresses"] = actresses
                    continue

                # 取得值容器（非演員欄位）
                value_element = panel.select_one(".value")
                if not value_element:
                    continue

                elif label == "片商":
                    # 提取片商
                    maker_link = value_element.select_one('a[href*="/makers/"]')
                    if maker_link:
                        info["studio"] = maker_link.text.strip()

                elif label == "日期":
                    # 提取發行日期
                    date_text = value_element.text.strip()
                    if date_text:
                        info["release_date"] = date_text

                elif label == "時長":
                    # 提取時長
                    duration_text = value_element.text.strip()
                    if duration_text:
                        info["duration"] = duration_text

                elif label == "導演":
                    # 提取導演
                    director_link = value_element.select_one("a")
                    if director_link:
                        info["director"] = director_link.text.strip()

                elif label == "系列":
                    # 提取系列
                    series_link = value_element.select_one("a")
                    if series_link:
                        info["series"] = series_link.text.strip()

                elif label == "評分":
                    # 提取評分
                    rating_text = value_element.text.strip()
                    # 提取數字評分 (如 "4.26分, 由564人評價")
                    import re

                    rating_match = re.search(r"(\d+\.?\d*)分", rating_text)
                    if rating_match:
                        info["rating"] = float(rating_match.group(1))

                elif label == "類別":
                    # 提取類別
                    category_links = value_element.select("a")
                    info["categories"] = [link.text.strip() for link in category_links]

            # 嘗試從番號推測片商代碼
            if not info["studio_code"] and video_id:
                info["studio_code"] = self._extract_studio_code_from_number(video_id)

            # 確保至少有女優資訊才返回結果
            if info["actresses"]:
                return info
            else:
                logger.warning(f"⚠️ JAVDB 頁面中未找到 {video_id} 的女優資訊")
                return None

        except Exception as e:
            logger.error(f"❌ 解析 JAVDB 詳情頁面時出錯: {e}")
            return None

    def _extract_studio_code_from_number(self, code: str) -> str | None:
        """從番號中提取片商代碼"""
        import re

        if not code:
            return None

        # 提取字母部分作為片商代碼
        match = re.match(r"^([A-Z]+)", code.upper())
        if match:
            return match.group(1)
        return None

    def get_stats(self) -> dict[str, Any]:
        """獲取搜尋統計資訊"""
        self._check_daily_reset()
        return {
            "today_count": self.stats.get("today_count", 0),
            "daily_limit": self.daily_limit,
            "total_requests": self.stats.get("total_requests", 0),
            "successful_searches": self.stats.get("successful_searches", 0),
            "cache_entries": len(self.cache),
            "session_requests": self.request_count,
            "session_limit": self.max_requests_per_session,
            "last_date": self.stats.get("last_date"),
        }

    def clear_cache(self):
        """清空快取"""
        self.cache.clear()
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
            logger.info("🧹 已清空 JAVDB 快取")
        except Exception as e:
            logger.warning(f"清空 JAVDB 快取失敗: {e}")

    def __del__(self):
        """析構函數 - 清理資源"""
        try:
            if hasattr(self, "session"):
                self.session.close()
            if hasattr(self, "cache"):
                self.save_cache()
            if hasattr(self, "stats"):
                self.save_stats()
        except Exception:  # noqa: BLE001
            pass
