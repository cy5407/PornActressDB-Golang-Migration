"""
安全的 JAVDB 搜尋器 - 整合反爬蟲策略
"""

import logging
import re
import threading
import time
from datetime import date
from pathlib import Path
from secrets import choice as secure_choice
from secrets import randbelow
from typing import Any, ClassVar
from urllib.parse import quote, urljoin

# 優先使用 curl_cffi 模擬瀏覽器 TLS 指紋繞過 Cloudflare
try:
    from curl_cffi import requests as cffi_requests

    HAS_CURL_CFFI = True
except ImportError:  # pragma: no cover
    cffi_requests = None
    HAS_CURL_CFFI = False

import httpx
from bs4 import BeautifulSoup

try:
    from utils.actress_name_filter import ActressNameFilter
except ImportError:  # pragma: no cover
    from src.utils.actress_name_filter import ActressNameFilter

try:
    from utils.json_utils import dump as json_dump
    from utils.json_utils import load as json_load
except ImportError:  # pragma: no cover
    from src.utils.json_utils import dump as json_dump
    from src.utils.json_utils import load as json_load
from src.utils.log_sanitizer import sanitize_url_for_log

logger = logging.getLogger(__name__)


def _random_delay(minimum: float, maximum: float) -> float:
    """使用較難預測的隨機來源產生延遲秒數。"""
    if maximum <= minimum:
        return minimum

    precision = 1_000_000
    return minimum + (randbelow(precision) / precision) * (maximum - minimum)


class SafeJAVDBSearcher:
    """安全的 JAVDB 搜尋器類別"""

    _DETAIL_MAKER_LABELS: ClassVar[frozenset[str]] = frozenset({"片商", "Maker"})
    _DETAIL_RATING_LABELS: ClassVar[frozenset[str]] = frozenset({"評分", "Rating"})
    _DETAIL_CATEGORY_LABELS: ClassVar[frozenset[str]] = frozenset({"類別", "Tags"})
    _DETAIL_TEXT_FIELDS: ClassVar[dict[str, str]] = {
        "日期": "release_date",
        "Released Date": "release_date",
        "時長": "duration",
        "Duration": "duration",
    }
    _DETAIL_LINK_FIELDS: ClassVar[dict[str, str]] = {
        "導演": "director",
        "Director": "director",
        "系列": "series",
        "Series": "series",
    }

    def __init__(self, cache_dir: str = None, warmup_enabled: bool = True):
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
        self.max_retry_wait_seconds = 300.0  # 允許較長冷卻以通過 Cloudflare
        self.consecutive_errors = 0
        self.consecutive_suspected_pages = 0
        self.suspected_page_halt_threshold = 3
        self._session_type = "unknown"
        self._impersonate = None
        self._warmup_enabled = warmup_enabled

        # 檢查當日統計
        self._check_daily_reset()

        # safe_request 會在多執行緒下共用 session / stats，因此用鎖保護狀態更新
        self._lock = threading.RLock()

        # 初始化會話
        self.create_session()
        if self._warmup_enabled:
            self._warmup()

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
                    self.cache = json_load(f)
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
                json_dump(self.cache, f, ensure_ascii=False, indent=2)
            logger.debug(f"💾 已儲存 {len(self.cache)} 個快取項目")
        except Exception as e:
            logger.error(f"儲存快取失敗: {e}")

    def load_stats(self):
        """載入統計資料"""
        if self.stats_file.exists():
            try:
                with open(self.stats_file, encoding="utf-8") as f:
                    self.stats = json_load(f)
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
                json_dump(self.stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"儲存統計失敗: {e}")

    def create_session(self):
        """建立模擬真實瀏覽器的 session（優先使用 curl_cffi）"""
        previous_session = getattr(self, "session", None)
        if previous_session is not None and hasattr(previous_session, "close"):
            try:
                previous_session.close()
            except Exception as e:
                logger.warning(f"⚠️ 關閉舊 JAVDB session 失敗: {e}")

        browser_fingerprints = [
            "chrome124",
            "chrome120",
            "chrome119",
            "edge101",
            "safari17_0",
        ]

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en-US;q=0.7,en;q=0.6",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

        if HAS_CURL_CFFI:
            self._impersonate = secure_choice(browser_fingerprints)
            self.session = cffi_requests.Session(
                impersonate=self._impersonate,
                headers=headers,
                timeout=30.0,
            )
            self._session_type = "curl_cffi"
            logger.info(f"🛡️ 使用 curl_cffi 建立 session - 指紋: {self._impersonate}")
        else:
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
            ]
            headers["User-Agent"] = secure_choice(user_agents)

            if randbelow(2) == 1:
                headers["DNT"] = "1"
            if randbelow(2) == 1:
                headers["Referer"] = "https://www.google.com/"

            self.session = httpx.Client(
                headers=headers,
                follow_redirects=True,
                timeout=30.0,
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
                default_encoding="utf-8",
            )
            self._session_type = "httpx"
            self._impersonate = None
            logger.warning(
                "⚠️ curl_cffi 不可用，使用 httpx fallback（TLS 指紋可能被 Cloudflare 偵測）"
            )

        self.request_count = 0
        logger.debug("🔄 已建立新的 JAVDB session (%s)", self._session_type)

    def _warmup(self):
        """訪問 JAVDB 首頁取得 Cloudflare cookie。"""
        try:
            logger.info("🔥 JAVDB 首頁暖機中...")
            time.sleep(_random_delay(1.0, 2.0))
            response = self.session.get("https://javdb.com")
            if getattr(response, "status_code", None) == 200:
                logger.info("✅ JAVDB 首頁暖機成功，已取得 session cookie")
            else:
                logger.warning(
                    "⚠️ JAVDB 首頁回應 %s，暖機可能失敗",
                    getattr(response, "status_code", "unknown"),
                )
        except Exception as e:
            logger.warning(f"⚠️ JAVDB 首頁暖機失敗: {e}")

    def safe_request(self, url: str, retry_count: int = 0) -> Any | None:
        """安全的 HTTP 請求方法（支援 curl_cffi 和 httpx 雙引擎）"""
        current_retry = retry_count

        while True:
            response, next_retry = self._attempt_safe_request(url, current_retry)
            if next_retry is None:
                return response
            current_retry = next_retry

    def _attempt_safe_request(
        self, url: str, current_retry: int
    ) -> tuple[Any | None, int | None]:
        try:
            session, consecutive_errors = self._prepare_request_context()
            if session is None:
                return None, None

            session = self._apply_cooldown_if_needed(session, consecutive_errors)
            time.sleep(self._calculate_request_delay(consecutive_errors, current_retry))

            response = session.get(url)
            self._record_request_sent()
            return self._handle_attempt_response(response, current_retry)

        except httpx.TimeoutException:
            return self._retry_attempt(self._handle_timeout_error(current_retry))

        except httpx.ConnectError:
            return self._retry_attempt(self._handle_connect_error(current_retry))

        except Exception as e:
            return self._retry_attempt(self._handle_unknown_error(e, current_retry))

    def _handle_attempt_response(
        self, response: Any, current_retry: int
    ) -> tuple[Any | None, int | None]:
        status = response.status_code
        if status == 200:
            self._reset_consecutive_errors()
            logger.debug("✅ JAVDB 請求成功: %s", status)
            return response, None

        return self._retry_attempt(self._handle_error_status(status, current_retry))

    def _retry_attempt(self, next_retry: int | None) -> tuple[None, int | None]:
        return None, next_retry

    def _prepare_request_context(self) -> tuple[Any | None, int]:
        with self._lock:
            self._check_daily_reset()
            if self.stats["today_count"] >= self.daily_limit:
                logger.warning(f"⚠️ 已達每日 JAVDB 請求限制 ({self.daily_limit})")
                return None, self.consecutive_errors
            if self.request_count >= self.max_requests_per_session:
                logger.info("🔄 重新建立 JAVDB session")
                self.create_session()
            return self.session, self.consecutive_errors

    def _apply_cooldown_if_needed(
        self, session: Any | None, consecutive_errors: int
    ) -> Any | None:
        if session is None or consecutive_errors < 5:
            return session
        cooldown = 300
        logger.warning(
            f"🧊 連續 {consecutive_errors} 次失敗，冷卻 {cooldown} 秒後重建 session"
        )
        time.sleep(cooldown)
        with self._lock:
            self.create_session()
            self.consecutive_errors = 0
            return self.session

    def _calculate_request_delay(
        self, consecutive_errors: int, current_retry: int
    ) -> float:
        adaptive_multiplier = 2 ** min(consecutive_errors, 5)
        delay = _random_delay(self.min_delay, self.max_delay) * adaptive_multiplier
        if current_retry > 0:
            delay += current_retry * 2.0
        logger.debug(f"⏱️ 等待 {delay:.1f} 秒...")
        return delay

    def _record_request_sent(self) -> None:
        with self._lock:
            self.request_count += 1
            self.stats["today_count"] += 1
            self.stats["total_requests"] += 1

    def _reset_consecutive_errors(self) -> None:
        with self._lock:
            self.consecutive_errors = 0

    def _increment_consecutive_errors(self) -> int:
        with self._lock:
            self.consecutive_errors += 1
            return self.consecutive_errors

    def _recreate_session(self) -> None:
        with self._lock:
            self.create_session()

    def _handle_error_status(self, status: int, current_retry: int) -> int | None:
        if status == 403:
            return self._handle_403(current_retry)
        if status == 429:
            return self._handle_429(current_retry)
        logger.warning(f"⚠️ JAVDB 請求失敗: {status}")
        return None

    def _handle_403(self, current_retry: int) -> int | None:
        consecutive_errors = self._increment_consecutive_errors()
        logger.warning(f"⚠️ 收到 403，連續錯誤 {consecutive_errors} 次")
        if current_retry < 2:
            wait_time = 30 + _random_delay(15, 45)
            if wait_time <= self.max_retry_wait_seconds:
                self._recreate_session()
                logger.info(f"🔄 更換瀏覽器指紋，等待 {wait_time:.1f} 秒後重試...")
                time.sleep(wait_time)
                return current_retry + 1
        logger.error("❌ 403 重試失敗，JAVDB 可能需要更強的反爬蟲策略")
        return None

    def _handle_429(self, current_retry: int) -> int | None:
        self._increment_consecutive_errors()
        if current_retry < 3:
            wait_time = 20 + _random_delay(10, 30)
            if wait_time <= self.max_retry_wait_seconds:
                logger.warning(f"⚠️ 收到 429，等待 {wait_time:.1f} 秒後重試...")
                time.sleep(wait_time)
                return current_retry + 1
        logger.error("❌ 429 重試次數過多，放棄請求")
        return None

    def _handle_timeout_error(self, current_retry: int) -> int | None:
        logger.warning("⏰ JAVDB 請求超時")
        self._increment_consecutive_errors()
        if current_retry < 2:
            return current_retry + 1
        return None

    def _handle_connect_error(self, current_retry: int) -> int | None:
        logger.warning("🔌 JAVDB 連線失敗")
        self._increment_consecutive_errors()
        if current_retry < 2:
            time.sleep(10 + current_retry * 5)
            return current_retry + 1
        return None

    def _handle_unknown_error(self, e: Exception, current_retry: int) -> int | None:
        logger.error(f"❌ JAVDB 請求過程中出錯: {e}")
        self._increment_consecutive_errors()
        if current_retry < 1:
            time.sleep(5)
            return current_retry + 1
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

    @staticmethod
    def _normalize_code_for_match(value: str | None) -> str:
        if not value:
            return ""
        return re.sub(r"[^A-Z0-9]", "", value.upper())

    @staticmethod
    def _looks_like_age_gate_or_landing_page(page_text: str) -> bool:
        indicators = [
            "Are you at least 18 years old",
            "Please note that",
            "Misrepresenting your age",
            "contain sexually explicit content",
            "By entering the site",
        ]
        lowered = page_text.lower()
        return any(indicator.lower() in lowered for indicator in indicators)

    def _make_search_error_result(
        self, video_id: str, reason: str, url: str | None = None
    ) -> dict[str, Any]:
        return {
            "code": video_id.upper(),
            "source": "JAVDB (安全增強版)",
            "actresses": [],
            "search_status": "search_error",
            "search_error_reason": reason,
            "search_url": url,
        }

    def _mark_suspected_page(self, video_id: str, reason: str) -> None:
        with self._lock:
            self.consecutive_suspected_pages += 1
            logger.warning(
                "⚠️ JAVDB 疑似異常頁 (%s) - %s，連續異常 %s 次",
                video_id,
                reason,
                self.consecutive_suspected_pages,
            )

    def _reset_suspected_page_counter(self) -> None:
        with self._lock:
            self.consecutive_suspected_pages = 0

    def _is_circuit_breaker_open(self) -> bool:
        with self._lock:
            return (
                self.consecutive_suspected_pages
                >= self.suspected_page_halt_threshold
            )

    def search_javdb(self, video_id: str) -> dict[str, Any] | None:
        """在 JAVDB 搜尋影片資訊"""
        if not video_id:
            return None
            # 檢查快取
        cache_key = f"javdb_{video_id.upper()}"
        if cache_key in self.cache:
            logger.debug(f"📋 從快取取得 {video_id} 的 JAVDB 資料")
            return self.cache[cache_key]

        if self._is_circuit_breaker_open():
            return self._make_search_error_result(
                video_id,
                "JAVDB 連續回傳疑似異常頁，已暫停本輪後續請求",
            )

        try:
            search_url = f"https://javdb.com/search?q={quote(video_id)}&f=all"
            response = self.safe_request(search_url)
            if not response:
                return None

            soup = BeautifulSoup(response.text, "html.parser")
            page_text = soup.get_text(" ", strip=True)

            if self._looks_like_age_gate_or_landing_page(page_text):
                self._mark_suspected_page(video_id, "搜尋頁返回年齡驗證/落地頁")
                return self._make_search_error_result(
                    video_id,
                    "JAVDB 搜尋頁疑似返回年齡驗證或異常落地頁",
                    search_url,
                )

            video_links = soup.select('a[href*="/v/"]')
            if not video_links:
                self._mark_suspected_page(video_id, "搜尋頁缺少影片結果連結")
                return self._make_search_error_result(
                    video_id,
                    "JAVDB 搜尋頁未提供可解析的影片結果，疑似異常頁",
                    search_url,
                )

            logger.debug(f"🎬 找到 {len(video_links)} 個影片連結")
            best_match_url = self._find_best_match_url(video_id, video_links)
            if not best_match_url:
                logger.debug(f"🔍 JAVDB 未找到番號 {video_id} 的精確匹配結果，視為未找到")
                return None

            detail_url = urljoin("https://javdb.com", best_match_url)
            detail_response = self.safe_request(detail_url)
            if not detail_response:
                return None

            info = self._parse_detail_page(detail_response, video_id, detail_url)
            if info:
                self._reset_suspected_page_counter()
                self._cache_successful_search(cache_key, info)
                logger.info(f"✅ JAVDB 找到番號 {video_id} 的資料")
                return info

            return None

        except Exception as e:
            logger.error(f"❌ 搜尋 {video_id} 時出錯: {e}")
            return None

    def _find_best_match_url(self, video_id: str, video_links) -> str | None:
        normalized_video_id = self._normalize_code_for_match(video_id)
        for link in video_links:
            href = link.get("href")
            if not href:
                continue
            link_text = link.get_text(strip=True)
            title_attr = link.get("title", "")
            text_to_check = f"{link_text} {title_attr}".upper()
            normalized_text = self._normalize_code_for_match(text_to_check)
            if video_id.upper() in text_to_check or normalized_video_id in normalized_text:
                logger.debug(f"🎯 找到匹配的影片連結: {href} (文字: {link_text})")
                return href
        return None

    def _cache_successful_search(self, cache_key: str, info: dict[str, Any]) -> None:
        self.cache[cache_key] = info
        self.save_cache()
        self.stats["successful_searches"] += 1
        self.save_stats()

    def _parse_detail_page(
        self, response: httpx.Response, video_id: str, url: str
    ) -> dict[str, Any] | None:
        """解析 JAVDB 詳情頁面"""
        try:
            # JAVDB 使用標準 UTF-8 編碼，不需要特殊處理
            soup = BeautifulSoup(response.text, "html.parser")

            page_text = soup.get_text(" ", strip=True)
            if self._looks_like_age_gate_or_landing_page(page_text):
                self._mark_suspected_page(video_id, "詳情頁返回年齡驗證/落地頁")
                return self._make_search_error_result(
                    video_id,
                    "JAVDB 詳情頁疑似返回年齡驗證或異常落地頁",
                    url,
                )

            info = self._create_empty_detail_info(video_id)
            if not self._parse_detail_title(soup, info, video_id):
                return None
            info_panels = soup.select(".panel-block")

            if not info_panels:
                self._mark_suspected_page(video_id, "詳情頁缺少 panel-block 結構")
                return self._make_search_error_result(
                    video_id,
                    "JAVDB 詳情頁缺少預期結構，疑似異常頁",
                    url,
                )

            actor_panel_found = False

            for panel in info_panels:
                strong_element = panel.select_one("strong")
                if not strong_element:
                    continue

                label = strong_element.text.strip().rstrip(":：")

                # 對於演員資訊，直接在同一個 panel 中尋找
                if label in {"演員", "Actor(s)"}:
                    actor_panel_found = True
                    info["actresses"] = self._extract_actresses_from_panel(panel)
                    continue

                # 取得值容器（非演員欄位）
                value_element = panel.select_one(".value")
                if not value_element:
                    continue
                self._apply_detail_panel_value(info, label, value_element)

            # 嘗試從番號推測片商代碼
            if not info["studio_code"] and video_id:
                info["studio_code"] = self._extract_studio_code_from_number(video_id)

            # 確保至少有女優資訊才返回結果
            if info["actresses"]:
                return info

            if not actor_panel_found:
                self._mark_suspected_page(video_id, "詳情頁缺少演員欄位")
                return self._make_search_error_result(
                    video_id,
                    "JAVDB 詳情頁缺少演員欄位，疑似異常頁",
                    url,
                )

            logger.warning(f"⚠️ JAVDB 頁面中未找到 {video_id} 的女優資訊")
            return None

        except Exception as e:
            logger.error(f"❌ 解析 JAVDB 詳情頁面時出錯: {e}")
            self._mark_suspected_page(video_id, f"詳情頁解析例外: {e}")
            return self._make_search_error_result(
                video_id,
                f"JAVDB 詳情頁解析失敗: {e}",
                url,
            )

    @staticmethod
    def _create_empty_detail_info(video_id: str) -> dict[str, Any]:
        return {
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

    def _parse_detail_title(
        self, soup: BeautifulSoup, info: dict[str, Any], video_id: str
    ) -> bool:
        title_element = soup.select_one("h2.title")
        if not title_element:
            return True
        info["title"] = title_element.text.strip()
        title_code_match = re.match(r"^([A-Z0-9]+-\d+)", info["title"], re.IGNORECASE)
        if not title_code_match:
            return True
        page_code = title_code_match.group(1).upper()
        if page_code == video_id.upper():
            return True
        logger.warning(
            f"⚠️ JAVDB 詳情頁番號不符: 搜尋 {video_id}，頁面顯示 {page_code}，視為未找到"
        )
        return False

    @staticmethod
    def _extract_actresses_from_panel(panel) -> list[str]:
        actresses: list[str] = []
        for link in panel.select('a[href*="/actors/"]'):
            next_element = link.find_next_sibling()
            if not SafeJAVDBSearcher._is_female_actor_marker(next_element):
                continue
            actress_name = link.text.strip()
            if actress_name and ActressNameFilter.is_valid_actress_name(
                actress_name, allow_single_latin_name=True
            ):
                actresses.append(actress_name)
        return actresses

    @staticmethod
    def _is_female_actor_marker(next_element) -> bool:
        return bool(
            (
                next_element
                and next_element.name == "strong"
                and next_element.get("class")
                and "symbol" in next_element.get("class")
                and "female" in next_element.get("class")
            )
            or (
                next_element
                and next_element.name == "strong"
                and "♀" in next_element.text
            )
        )

    @staticmethod
    def _apply_detail_panel_value(info: dict[str, Any], label: str, value_element) -> None:
        if label in SafeJAVDBSearcher._DETAIL_MAKER_LABELS:
            SafeJAVDBSearcher._apply_detail_maker(info, value_element)
            return

        text_field = SafeJAVDBSearcher._DETAIL_TEXT_FIELDS.get(label)
        if text_field is not None:
            SafeJAVDBSearcher._apply_detail_text_field(info, value_element, text_field)
            return

        link_field = SafeJAVDBSearcher._DETAIL_LINK_FIELDS.get(label)
        if link_field is not None:
            SafeJAVDBSearcher._apply_detail_link_field(info, value_element, link_field)
            return

        if label in SafeJAVDBSearcher._DETAIL_RATING_LABELS:
            SafeJAVDBSearcher._apply_detail_rating(info, value_element)
            return

        if label in SafeJAVDBSearcher._DETAIL_CATEGORY_LABELS:
            SafeJAVDBSearcher._apply_detail_categories(info, value_element)

    @staticmethod
    def _apply_detail_maker(info: dict[str, Any], value_element) -> None:
        maker_link = value_element.select_one('a[href*="/makers/"]')
        if maker_link:
            info["studio"] = maker_link.text.strip()

    @staticmethod
    def _apply_detail_text_field(
        info: dict[str, Any], value_element, field_name: str
    ) -> None:
        text_value = value_element.text.strip()
        if text_value:
            info[field_name] = text_value

    @staticmethod
    def _apply_detail_link_field(
        info: dict[str, Any], value_element, field_name: str
    ) -> None:
        link_value = value_element.select_one("a")
        if link_value:
            info[field_name] = link_value.text.strip()

    @staticmethod
    def _apply_detail_rating(info: dict[str, Any], value_element) -> None:
        rating_match = re.search(r"(\d+\.?\d*)", value_element.text.strip())
        if rating_match:
            info["rating"] = float(rating_match.group(1))

    @staticmethod
    def _apply_detail_categories(info: dict[str, Any], value_element) -> None:
        info["categories"] = [link.text.strip() for link in value_element.select("a")]

    def _extract_studio_code_from_number(self, code: str) -> str | None:
        """從番號中提取片商代碼"""
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
            "session_type": self._session_type,
            "impersonate": self._impersonate,
            "consecutive_errors": self.consecutive_errors,
            "consecutive_suspected_pages": self.consecutive_suspected_pages,
            "suspected_page_halt_threshold": self.suspected_page_halt_threshold,
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
        except Exception as e:  # noqa: BLE001
            logger.debug("忽略 SafeJAVDBSearcher 析構清理錯誤: %s", e)
