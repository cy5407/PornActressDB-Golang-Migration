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
from src.scrapers.enhanced import encoding_handler as encoding_handler_module
from src.scrapers.enhanced.encoding_handler import RateLimitedRequester
from src.services.safe_javdb_searcher import SafeJAVDBSearcher
from src.services.web_searcher import WebSearcher
from src.scrapers.sources.shiroutowiki_scraper import ShiroutoWikiScraper
from src.scrapers.async_scraper import AsyncWebScraper, ScrapingConfig
from src.scrapers.base_scraper import BaseScraper, ErrorType, ScrapingException
from src.scrapers.cache_manager import get_global_cache_manager
from src.scrapers.rate_limiter import RateLimiter
from src.utils.actress_name_filter import ActressNameFilter


class _DummyConfig:
    def get(self, _section, _option, fallback=None):
        return fallback


class _DummyFactory:
    @staticmethod
    def from_config(_config):
        return object()


class _TextResponse:
    def __init__(self, text: str):
        self.text = text


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


def test_classifier_core_researches_when_last_search_date_is_invalid():
    assert (
        classifier_core_module._should_research_stale_record(
            "ABCD-123", "not-a-real-date"
        )
        is True
    )


def test_classifier_core_build_video_info_preserves_search_error_status():
    class _DummyStudioIdentifier:
        def identify_studio(self, _code):
            return "S1"

    core = classifier_core_module.UnifiedClassifierCore.__new__(
        classifier_core_module.UnifiedClassifierCore
    )
    core.studio_identifier = _DummyStudioIdentifier()

    info = core._build_video_info(
        "SNOS-053",
        Path("SNOS-053.mp4"),
        {
            "source": "JAVDB (安全增強版)",
            "actresses": [],
            "search_status": "search_error",
            "search_error_reason": "JAVDB 搜尋頁疑似返回年齡驗證或異常落地頁",
        },
        "JAVDB",
        "2026-04-04T01:30:00",
    )

    assert info["search_status"] == "search_error"
    assert "年齡驗證" in info["search_error_reason"]


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


def test_web_searcher_builds_zero_prefixed_alias_candidates():
    searcher = WebSearcher.__new__(WebSearcher)

    assert searcher._build_code_candidates("MIDV-00567") == [
        "MIDV-00567",
        "MIDV-567",
    ]
    assert searcher._build_code_candidates("MBDD-2094") == ["MBDD-2094"]
    assert searcher._build_code_candidates("MIDV-0567") == ["MIDV-0567"]


def test_batch_cascade_search_retries_zero_prefixed_alias():
    searcher = WebSearcher.__new__(WebSearcher)
    searcher.search_cache = {}
    batch_calls = []

    def fake_batch_search(codes, _stop_event, _progress_callback=None):
        batch_calls.append(list(codes))
        results = {}
        for code in codes:
            if code == "MIDV-567":
                results[code] = {
                    "source": "AV-WIKI",
                    "actresses": ["範例女優"],
                }
            else:
                results[code] = None
        return results

    searcher.batch_search_avwiki_concurrent = fake_batch_search
    stop_event = threading.Event()

    results = searcher.batch_cascade_search(["MIDV-00567"], stop_event)

    assert batch_calls == [["MIDV-00567"], ["MIDV-567"]]
    assert results["MIDV-00567"]["actresses"] == ["範例女優"]
    assert results["MIDV-00567"]["matched_code"] == "MIDV-567"
    assert results["MIDV-00567"]["search_alias_used"] is True
    assert results["MIDV-00567"]["final_source"] == "AV-WIKI"


def test_search_shiroutowiki_only_expands_candidates_and_preserves_alias_metadata():
    class _FakeShiroutoWikiScraper:
        def __init__(self):
            self.captured = None

        def build_search_candidates(self, code: str) -> list[str]:
            return ShiroutoWikiScraper.build_search_candidates(code)

        def search_video(self, code: str, candidates: list[str]):
            self.captured = (code, candidates)
            return {
                "source": "shiroutowiki",
                "actresses": ["三崎なな"],
                "matched_code": "MIDV-567",
                "delivery_code": "midv00567",
                "product_code": "MIDV-567",
            }

    searcher = WebSearcher.__new__(WebSearcher)
    searcher.search_cache = {}
    searcher.shiroutowiki_scraper = _FakeShiroutoWikiScraper()

    result = searcher.search_shiroutowiki_only("MIDV-00567", threading.Event())

    assert searcher.shiroutowiki_scraper.captured == (
        "MIDV-00567",
        ["MIDV-00567", "MIDV00567", "midv00567", "MIDV-567", "MIDV567"],
    )
    assert result["matched_code"] == "MIDV-567"
    assert result["search_alias_used"] is True
    assert result["searched_code"] == "MIDV-00567"
    assert searcher.search_cache["shiroutowiki::MIDV-00567"]["source"] == "shiroutowiki"


def test_actress_name_filter_allows_single_latin_name_when_requested():
    assert ActressNameFilter.is_valid_actress_name("Soa") is False
    assert ActressNameFilter.is_valid_actress_name(
        "Soa", allow_single_latin_name=True
    )


def test_safe_javdb_detail_page_extracts_single_latin_actress_name():
    html = """
    <html><body>
      <h2 class="title">SNOS-053 Demo</h2>
      <div class="panel-block">
        <strong>演員:</strong>
        <span class="value">
          <a href="/actors/abc">Soa</a><strong class="symbol female">♀</strong>
          <a href="/actors/def">吉村卓</a><strong class="symbol male">♂</strong>
        </span>
      </div>
      <div class="panel-block"><strong>片商:</strong><span class="value"><a href="/makers/7R">S1 NO.1 STYLE</a></span></div>
      <div class="panel-block"><strong>日期:</strong><span class="value">2025-12-24</span></div>
    </body></html>
    """

    searcher = SafeJAVDBSearcher.__new__(SafeJAVDBSearcher)
    searcher._lock = threading.RLock()
    searcher.consecutive_suspected_pages = 0
    searcher.suspected_page_halt_threshold = 3

    result = searcher._parse_detail_page(
        _TextResponse(html), "SNOS-053", "https://javdb.com/v/demo"
    )

    assert result["actresses"] == ["Soa"]
    assert result["studio"] == "S1 NO.1 STYLE"


def test_safe_javdb_search_marks_age_gate_page_as_search_error():
    age_gate_html = """
    <html><body>
      <p>Please note that javdb.com contain sexually explicit content.</p>
      <p>Are you at least 18 years old?</p>
    </body></html>
    """

    searcher = SafeJAVDBSearcher.__new__(SafeJAVDBSearcher)
    searcher.cache = {}
    searcher.stats = {"successful_searches": 0}
    searcher._lock = threading.RLock()
    searcher.consecutive_suspected_pages = 0
    searcher.suspected_page_halt_threshold = 3
    searcher.save_cache = lambda: None
    searcher.save_stats = lambda: None
    searcher.safe_request = lambda _url: _TextResponse(age_gate_html)

    result = searcher.search_javdb("ABCD-123")

    assert result["search_status"] == "search_error"
    assert "年齡驗證" in result["search_error_reason"]
    assert searcher.consecutive_suspected_pages == 1


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


class _ClosableResponse:
    status_code = 200
    content = b"ok"
    headers = {}

    def raise_for_status(self):
        return None


class _ClosableSession:
    def __init__(self):
        self.headers = {}
        self.closed = False
        self.requested_url = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True
        return False

    def get(self, url, timeout):
        self.requested_url = (url, timeout)
        return _ClosableResponse()


def test_rate_limited_requester_closes_session(monkeypatch):
    created_sessions = []

    def fake_session_factory():
        session = _ClosableSession()
        created_sessions.append(session)
        return session

    monkeypatch.setattr(encoding_handler_module.requests, "Session", fake_session_factory)

    requester = RateLimitedRequester(min_delay=0.0, max_delay=0.0)
    response = requester.get("https://example.com", {"User-Agent": "test"}, timeout=3)

    assert response.status_code == 200
    assert len(created_sessions) == 1
    assert created_sessions[0].requested_url == ("https://example.com", 3)
    assert created_sessions[0].closed is True
