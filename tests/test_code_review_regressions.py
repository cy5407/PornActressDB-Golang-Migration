import asyncio
import sys
import threading
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.services import classifier_core as classifier_core_module
from src.services.web_searcher import WebSearcher
from src.scrapers.async_scraper import AsyncWebScraper, ScrapingConfig
from src.scrapers.base_scraper import BaseScraper, ErrorType, ScrapingException
from src.scrapers.enhanced.encoding_handler import RateLimitedRequester
from src.scrapers.cache_manager import get_global_cache_manager
from src.scrapers.rate_limiter import RateLimiter


class _DummyConfig:
    def get(self, _section, _option, fallback=None):
        return fallback


class _DummyFactory:
    @staticmethod
    def from_config(_config):
        return object()


def test_classifier_core_falls_back_to_json_db(monkeypatch):
    class DummyJSONDBManager:
        def __init__(self, data_dir):
            self.data_dir = data_dir

    def raise_incremental_error(_data_dir):
        raise RuntimeError("journal init failed")

    monkeypatch.setattr(
        classifier_core_module, "IncrementalJSONDB", raise_incremental_error
    )
    monkeypatch.setattr(
        classifier_core_module, "JSONDBManager", DummyJSONDBManager
    )
    monkeypatch.setattr(classifier_core_module, "UnifiedCodeExtractor", lambda: object())
    monkeypatch.setattr(classifier_core_module, "UnifiedFileScanner", _DummyFactory)
    monkeypatch.setattr(classifier_core_module, "FileMover", _DummyFactory)
    monkeypatch.setattr(classifier_core_module, "StudioIdentifier", lambda: object())
    monkeypatch.setattr(
        classifier_core_module, "WebSearcher", lambda _config: object()
    )

    core = classifier_core_module.UnifiedClassifierCore(_DummyConfig())

    assert isinstance(core.db_manager, DummyJSONDBManager)
    assert core.db_manager.data_dir == "data/json_db"


def test_classifier_core_researches_record_when_last_search_date_is_invalid(caplog):
    core = classifier_core_module.UnifiedClassifierCore.__new__(
        classifier_core_module.UnifiedClassifierCore
    )
    searched_codes = []

    class DummyScanner:
        def scan_directory(self, _folder_path):
            return [Path("ABCD-123.mp4")]

    class DummyExtractor:
        @staticmethod
        def extract_code(_filename):
            return "ABCD-123"

    class DummyDB:
        @staticmethod
        def get_all_videos():
            return [
                {
                    "code": "ABCD-123",
                    "search_status": "searched_found",
                    "last_search_date": "not-a-date",
                    "actresses": ["Aoi"],
                }
            ]

    class DummySearcher:
        @staticmethod
        def search_javdb_only(_code, _stop_event):
            return None

        @staticmethod
        def batch_search(codes, _search_func, _stop_event, _progress_callback, result_callback=None):
            searched_codes.extend(codes)
            if result_callback:
                for code in codes:
                    result_callback(code, None, None)
            return {code: None for code in codes}

    core.file_scanner = DummyScanner()
    core.code_extractor = DummyExtractor()
    core.db_manager = DummyDB()
    core.web_searcher = DummySearcher()
    core._persist_code_result = lambda *args, **kwargs: None
    core.logger = classifier_core_module.logger

    stop_event = threading.Event()

    with caplog.at_level("WARNING"):
        result = core.process_and_search_javdb("unused", stop_event)

    assert result["status"] == "success"
    assert searched_codes == ["ABCD-123"]
    assert "last_search_date 無法解析" in caplog.text


def test_search_japanese_sites_only_delegates_to_unified_method():
    searcher = WebSearcher.__new__(WebSearcher)
    captured = {}

    def fake_search(code, stop_event):
        captured["args"] = (code, stop_event)
        return {"actresses": ["Aoi"]}

    searcher.search_japanese_sites = fake_search
    stop_event = object()

    result = searcher.search_japanese_sites_only("ABCD-123", stop_event)

    assert result == {"actresses": ["Aoi"]}
    assert captured["args"] == ("ABCD-123", stop_event)


class _RateLimitOnlyScraper(BaseScraper):
    async def scrape_url(self, url: str) -> dict:
        raise ScrapingException(
            "請求過於頻繁",
            ErrorType.RATE_LIMIT_ERROR,
            url,
            429,
            retry_after=7,
        )

    def parse_content(self, content: str, url: str) -> dict:
        return {}


def test_safe_scrape_records_retry_after_on_rate_limit():
    rate_limiter = RateLimiter()
    scraper = _RateLimitOnlyScraper(rate_limiter=rate_limiter)
    url = "https://javdb.com/search?q=ABCD-123&f=all"

    try:
        asyncio.run(scraper.safe_scrape(url))
        raise AssertionError("預期 safe_scrape 應拋出 ScrapingException")
    except ScrapingException as exc:
        exc_info = exc

    domain_stats = rate_limiter.get_domain_stats("javdb.com")

    assert exc_info.retry_after == 7
    assert domain_stats is not None
    assert domain_stats["failed_requests"] == 1
    assert domain_stats["is_retry_after_active"] is True
    assert 0 < domain_stats["retry_after_remaining"] <= 7


class _DummyResponse:
    def __init__(self, status: int, body: bytes = b"not found"):
        self.status = status
        self._body = body

    async def read(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DummySession:
    def __init__(self, statuses: list[int]):
        self.statuses = list(statuses)
        self.calls = 0

    def get(self, *_args, **_kwargs):
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        return _DummyResponse(status)


def test_async_web_scraper_treats_404_as_failure_without_retry():
    scraper = AsyncWebScraper(ScrapingConfig(max_retries=3, enable_cache=False))
    session = _DummySession([404, 200])

    result = asyncio.run(
        scraper._make_request_with_retry(session, "https://example.com/missing")
    )

    assert result.success is False
    assert result.status_code == 404
    assert session.calls == 1
    assert scraper.stats["failed_requests"] == 1
    assert scraper.stats["successful_requests"] == 0


class _NoOpScraper(BaseScraper):
    async def scrape_url(self, url: str) -> dict:
        return {"url": url}

    def parse_content(self, content: str, url: str) -> dict:
        return {"content": content, "url": url}


def test_scrapers_share_global_cache_and_health_resources():
    async_scraper_a = AsyncWebScraper()
    async_scraper_b = AsyncWebScraper()
    base_scraper_a = _NoOpScraper()
    base_scraper_b = _NoOpScraper()

    assert async_scraper_a.cache_manager is async_scraper_b.cache_manager
    assert async_scraper_a.cache_manager is get_global_cache_manager()
    assert base_scraper_a.cache_manager is base_scraper_b.cache_manager
    assert base_scraper_a.health_checker is base_scraper_b.health_checker


def test_rate_limited_requester_closes_session(monkeypatch):
    requester = RateLimitedRequester()
    requester._wait_if_needed = lambda: None
    events = {"closed": False, "requested": False}

    class DummyResponse:
        status_code = 200
        content = b"ok"
        headers = {}

        @staticmethod
        def raise_for_status():
            return None

    class DummySession:
        def __init__(self):
            self.headers = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            events["closed"] = True
            return False

        def get(self, url, timeout):
            events["requested"] = (url, timeout)
            return DummyResponse()

    monkeypatch.setattr(
        "src.scrapers.enhanced.encoding_handler.requests.Session",
        DummySession,
    )

    response = requester.get("https://example.com", {"User-Agent": "UA"}, timeout=9)

    assert response.status_code == 200
    assert events["requested"] == ("https://example.com", 9)
    assert events["closed"] is True
