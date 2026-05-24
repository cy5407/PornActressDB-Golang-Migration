"""
補充 avwiki_scraper.py 覆蓋率測試

策略：
- 純邏輯方法直接呼叫 BeautifulSoup fixtures
- async 方法用 AsyncMock 模擬 safe_scrape / scrape_url
- scrape_url 用 MagicMock 模擬 aiohttp session
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from bs4 import BeautifulSoup

from src.scrapers.base_scraper import ErrorType, ScrapingException
from src.scrapers.sources.avwiki_scraper import AVWikiScraper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scraper() -> AVWikiScraper:
    with patch("src.scrapers.sources.avwiki_scraper.ActressNameFilter"), \
         patch("src.scrapers.sources.avwiki_scraper.AdaptiveConcurrencyController"), \
         patch("src.scrapers.sources.avwiki_scraper.ExponentialBackoff"):
        s = AVWikiScraper()
    s._is_valid_actress_name = lambda name: True
    return s


def _run(coro):
    return asyncio.run(coro)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# scrape_url（lines 54-93）
# ---------------------------------------------------------------------------

def _make_mock_response(status: int, content: bytes = b"<html><h1>Title</h1></html>", headers=None):
    resp = MagicMock()
    resp.status = status
    resp.headers = headers or {}
    resp.read = AsyncMock(return_value=content)
    resp.raise_for_status = MagicMock()
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _make_mock_session(response):
    session = MagicMock()
    session.get = MagicMock(return_value=response)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


class TestScrapeUrl:
    def test_404_raises_client_error(self):
        s = _make_scraper()
        resp = _make_mock_response(404)
        with patch("aiohttp.ClientSession", return_value=_make_mock_session(resp)):
            with pytest.raises(ScrapingException) as exc_info:
                _run(s.scrape_url("http://av-wiki.net/missing"))
        assert exc_info.value.error_type == ErrorType.CLIENT_ERROR

    def test_500_raises_server_error(self):
        s = _make_scraper()
        resp = _make_mock_response(500)
        with patch("aiohttp.ClientSession", return_value=_make_mock_session(resp)):
            with pytest.raises(ScrapingException) as exc_info:
                _run(s.scrape_url("http://av-wiki.net/broken"))
        assert exc_info.value.error_type == ErrorType.SERVER_ERROR

    def test_429_raises_rate_limit_error(self):
        s = _make_scraper()
        resp = _make_mock_response(429)
        with patch("aiohttp.ClientSession", return_value=_make_mock_session(resp)):
            with pytest.raises(ScrapingException) as exc_info:
                _run(s.scrape_url("http://av-wiki.net/ratelimited"))
        assert exc_info.value.error_type == ErrorType.RATE_LIMIT_ERROR

    def test_200_returns_parsed_data(self):
        s = _make_scraper()
        resp = _make_mock_response(200)
        with patch("aiohttp.ClientSession", return_value=_make_mock_session(resp)):
            result = _run(s.scrape_url("http://av-wiki.net/v/ok"))
        assert result["source"] == "AV-WIKI"

    def test_client_error_raises_network_error(self):
        s = _make_scraper()
        session = MagicMock()
        session.get = MagicMock(side_effect=aiohttp.ClientError("conn"))
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            with pytest.raises(ScrapingException) as exc_info:
                _run(s.scrape_url("http://av-wiki.net/v/bad"))
        assert exc_info.value.error_type == ErrorType.NETWORK_ERROR

    def test_unknown_exception_raises_unknown_error(self):
        s = _make_scraper()
        session = MagicMock()
        session.get = MagicMock(side_effect=ValueError("unexpected"))
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            with pytest.raises(ScrapingException) as exc_info:
                _run(s.scrape_url("http://av-wiki.net/v/crash"))
        assert exc_info.value.error_type == ErrorType.UNKNOWN_ERROR


# ---------------------------------------------------------------------------
# parse_content（lines 97-108）
# ---------------------------------------------------------------------------

class TestParseContent:
    def test_search_url_calls_parse_search(self):
        s = _make_scraper()
        result = s.parse_content("<html/>", "http://av-wiki.net/?s=STARS-001")
        assert "search_results" in result

    def test_detail_url_calls_parse_detail(self):
        s = _make_scraper()
        result = s.parse_content("<html><h1>STARS-001 Title</h1></html>", "http://av-wiki.net/v/stars-001")
        assert "actresses" in result

    def test_parse_exception_raises_scraping_exception(self):
        s = _make_scraper()
        s._parse_search_results = MagicMock(side_effect=ValueError("parse error"))
        with pytest.raises(ScrapingException):
            s.parse_content("<html/>", "http://av-wiki.net/?s=X")


# ---------------------------------------------------------------------------
# _parse_search_results（lines 112-132）
# ---------------------------------------------------------------------------

class TestParseSearchResults:
    def test_no_results_page_returns_empty(self):
        """検索無結果頁面應回傳空結果（lines 113-121）"""
        s = _make_scraper()
        html = "<html><body>見つかりませんでした</body></html>"
        result = s._parse_search_results(_soup(html))
        assert result["found"] is False
        assert result["search_results"] == []

    def test_results_found_returns_actress_list(self):
        """找到結果時應回傳女優列表（lines 123-132）"""
        s = _make_scraper()
        html = '<html><body><a rel="tag" href="/av-actress/test">田中みな実</a></body></html>'
        result = s._parse_search_results(_soup(html))
        assert result["found"] is True
        assert "田中みな実" in result["unique_actresses"]


# ---------------------------------------------------------------------------
# _is_no_results_page（line 136）
# ---------------------------------------------------------------------------

class TestIsNoResultsPage:
    def test_detects_no_results(self):
        assert AVWikiScraper._is_no_results_page("見つかりませんでした") is True

    def test_detects_english_no_results(self):
        assert AVWikiScraper._is_no_results_page("No results found") is True

    def test_regular_page_returns_false(self):
        assert AVWikiScraper._is_no_results_page("Normal page content") is False


# ---------------------------------------------------------------------------
# _append_unique_actress_element（line 154）
# ---------------------------------------------------------------------------

class TestAppendUniqueActressElement:
    def test_skips_empty_name(self):
        elements = []
        seen = set()
        AVWikiScraper._append_unique_actress_element(elements, seen, None, "test")
        assert elements == []

    def test_skips_duplicate_name(self):
        elements = []
        seen = {"田中"}
        AVWikiScraper._append_unique_actress_element(elements, seen, "田中", "test")
        assert elements == []

    def test_adds_with_href(self):
        elements = []
        seen = set()
        AVWikiScraper._append_unique_actress_element(
            elements, seen, "田中みな実", "tag_link", "/av-actress/tanaka"
        )
        assert len(elements) == 1
        assert elements[0]["href"] == "/av-actress/tanaka"


# ---------------------------------------------------------------------------
# _extract_actress_name_elements（lines 203-237）
# ---------------------------------------------------------------------------

class TestExtractActressNameElements:
    def test_extracts_link_with_actress_path(self):
        s = _make_scraper()
        html = '<div class="actress-name"><a href="/av-actress/tanaka">田中みな実</a></div>'
        elements = []
        seen = set()
        s._extract_actress_name_elements(_soup(html), elements, seen)
        assert len(elements) == 1
        assert elements[0]["name"] == "田中みな実"

    def test_link_without_actress_path_skipped(self):
        """href 不含 /av-actress/ 的連結應被跳過（line 216）"""
        s = _make_scraper()
        html = '<div class="actress-name"><a href="/other/path">田中みな実</a></div>'
        elements = []
        seen = set()
        s._extract_actress_name_elements(_soup(html), elements, seen)
        assert elements == []

    def test_text_fallback_when_no_links(self):
        """沒有結構化連結時不應回退到純文字（避免污染）"""
        s = _make_scraper()
        html = '<div class="actress-name">田中みな実</div>'
        elements = []
        seen = set()
        s._extract_actress_name_elements(_soup(html), elements, seen)
        assert elements == []


# ---------------------------------------------------------------------------
# _extract_article_tag_actresses（lines 245-261）
# ---------------------------------------------------------------------------

class TestExtractArticleTagActresses:
    def test_extracts_from_article_tags(self):
        s = _make_scraper()
        html = '<article><a rel="tag" href="/av-actress/tanaka">田中みな実</a></article>'
        elements = []
        seen = set()
        s._extract_article_tag_actresses(_soup(html), elements, seen)
        assert len(elements) == 1

    def test_extracts_from_post_div_fallback(self):
        s = _make_scraper()
        html = '<div class="post"><a rel="tag" href="/av-actress/tanaka">田中みな実</a></div>'
        elements = []
        seen = set()
        s._extract_article_tag_actresses(_soup(html), elements, seen)
        assert len(elements) == 1

    def test_exception_in_article_silenced(self):
        """article 解析例外應被靜默記錄"""
        s = _make_scraper()
        html = '<article></article>'
        elements = []
        seen = set()
        # patch find_all to raise on article level
        with patch.object(
            BeautifulSoup, "find_all",
            side_effect=lambda *a, **kw: [MagicMock(find_all=MagicMock(side_effect=RuntimeError("boom")))]
            if a and a[0] == "article" else []
        ):
            s._extract_article_tag_actresses(_soup(html), elements, seen)
        assert elements == []


# ---------------------------------------------------------------------------
# _extract_text_scan_actresses（lines 269-277）
# ---------------------------------------------------------------------------

class TestExtractTextScanActresses:
    def test_extracts_from_text(self):
        s = _make_scraper()
        s._extract_actresses_from_text = MagicMock(return_value=["田中みな実", "桃乃木かな"])
        elements = []
        seen = set()
        s._extract_text_scan_actresses("some text", elements, seen)
        assert len(elements) == 2

    def test_stops_at_10_elements(self):
        s = _make_scraper()
        names = [f"女優{i:02d}" for i in range(15)]
        s._extract_actresses_from_text = MagicMock(return_value=names)
        elements = []
        seen = set()
        s._extract_text_scan_actresses("some text", elements, seen)
        assert len(elements) == 10


# ---------------------------------------------------------------------------
# _extract_detail_title（lines 280-281）
# ---------------------------------------------------------------------------

class TestExtractDetailTitle:
    def test_extracts_h1(self):
        s = _make_scraper()
        assert s._extract_detail_title(_soup("<h1>STARS-001 Title</h1>")) == "STARS-001 Title"

    def test_extracts_h2_entry_title(self):
        s = _make_scraper()
        assert s._extract_detail_title(
            _soup('<h2 class="entry-title">Title</h2>')
        ) == "Title"

    def test_extracts_title_tag(self):
        s = _make_scraper()
        assert s._extract_detail_title(
            _soup("<title>Page Title</title>")
        ) == "Page Title"

    def test_returns_none_when_not_found(self):
        s = _make_scraper()
        assert s._extract_detail_title(_soup("<div>nothing</div>")) is None


# ---------------------------------------------------------------------------
# _extract_detail_actresses（lines 284-306）
# ---------------------------------------------------------------------------

class TestExtractDetailActresses:
    def test_extracts_from_tag_links(self):
        s = _make_scraper()
        html = '<a rel="tag" href="/av-actress/tanaka">田中みな実</a>'
        result = s._extract_detail_actresses(_soup(html))
        assert "田中みな実" in result

    def test_extracts_from_actress_name_class_links(self):
        s = _make_scraper()
        html = '<div class="actress-name"><a href="/av-actress/tanaka">田中みな実</a></div>'
        result = s._extract_detail_actresses(_soup(html))
        assert "田中みな実" in result

    def test_text_fallback_when_no_links(self):
        s = _make_scraper()
        html = '<div class="actress-name">田中みな実</div>'
        s._extract_actresses_from_text = MagicMock(return_value=["田中みな実"])
        result = s._extract_detail_actresses(_soup(html))
        assert result == []


# ---------------------------------------------------------------------------
# _parse_detail_page（lines 310-325）
# ---------------------------------------------------------------------------

class TestParseDetailPage:
    def test_parses_basic_detail(self):
        s = _make_scraper()
        html = '<html><h1>STARS-001 Test Title</h1><p>2023年5月10日 田中みな実</p></html>'
        result = s._parse_detail_page(_soup(html))
        assert result["found"] is True
        assert result["title"] == "STARS-001 Test Title"

    def test_extracts_release_date(self):
        s = _make_scraper()
        html = "<html><h1>T</h1><body>2023-05-10</body></html>"
        result = s._parse_detail_page(_soup(html))
        assert result["release_date"] == "2023-05-10"


# ---------------------------------------------------------------------------
# _select_actress_scan_lines（lines 328-351）
# ---------------------------------------------------------------------------

class TestSelectActressScanLines:
    def test_finds_keyword_context_lines(self):
        s = _make_scraper()
        lines = ["nothing", "出演 女優A", "田中みな実", "more stuff", "end"]
        result = s._select_actress_scan_lines(lines)
        assert any("田中" in line for line in result)

    def test_fallback_to_top_bottom_when_no_keywords(self):
        s = _make_scraper()
        lines = [f"line{i}" for i in range(20)]
        result = s._select_actress_scan_lines(lines)
        # Should return lines[:upper] + lines[lower:]
        assert "line0" in result
        assert "line19" in result


# ---------------------------------------------------------------------------
# _extract_actress_names_from_lines（lines 356-368）
# ---------------------------------------------------------------------------

class TestExtractActressNamesFromLines:
    def test_extracts_japanese_names(self):
        s = _make_scraper()
        lines = ["田中みな実 桃乃木かな"]
        seen = set()
        actresses = []
        result = s._extract_actress_names_from_lines(lines, seen, actresses)
        assert len(result) > 0

    def test_stops_at_15_actresses(self):
        s = _make_scraper()
        # Create lines with many unique Japanese names
        lines = ["田中みな実", "桃乃木かな", "浜崎真緒", "美竹すず", "河北彩花",
                 "三上悠亜", "深田咏美", "葵つかさ", "明日花キララ", "天使もえ",
                 "宮沢ゆかり", "小倉由菜", "伊藤舞雪", "湊莉久", "松本菜奈実", "高橋しょう子"]
        seen = set()
        actresses = []
        result = s._extract_actress_names_from_lines(lines, seen, actresses)
        assert len(result) <= 15


# ---------------------------------------------------------------------------
# _extract_studio_info（lines 382-406）
# ---------------------------------------------------------------------------

class TestExtractStudioInfo:
    def test_extracts_studio_from_title_code(self):
        s = _make_scraper()
        result = s._extract_studio_info("", title="STARS-001")
        assert result["studio_code"] == "STARS"

    def test_extracts_studio_from_text(self):
        s = _make_scraper()
        result = s._extract_studio_info("片商：S1 STYLE", title="")
        assert "S1" in result["studio"]

    def test_extracts_known_studio_name(self):
        s = _make_scraper()
        result = s._extract_studio_info("MOODYZ 最新作品")
        assert result["studio"] == "MOODYZ"

    def test_no_studio_returns_none(self):
        s = _make_scraper()
        result = s._extract_studio_info("random text without studio info")
        assert result["studio"] is None

    def test_empty_title_skips_code_extraction(self):
        s = _make_scraper()
        result = s._extract_studio_info("some text", title="")
        assert result["studio_code"] is None


# ---------------------------------------------------------------------------
# search_video（lines 414-448）
# ---------------------------------------------------------------------------

class TestSearchVideo:
    def test_search_video_found(self):
        s = _make_scraper()
        s.safe_scrape = AsyncMock(return_value={
            "unique_actresses": ["田中みな実"],
            "search_results": ["田中みな実"],
        })
        result = _run(s.search_video("STARS-001"))
        assert "田中みな実" in result["actresses"]
        assert "content_quality" in result

    def test_search_video_not_found(self):
        s = _make_scraper()
        s.safe_scrape = AsyncMock(return_value={})
        result = _run(s.search_video("NOTFOUND-999"))
        assert result["actresses"] == []
        assert "message" in result

    def test_search_video_exception_raises(self):
        s = _make_scraper()
        s.safe_scrape = AsyncMock(side_effect=RuntimeError("network"))
        with pytest.raises(ScrapingException):
            _run(s.search_video("STARS-001"))


# ---------------------------------------------------------------------------
# get_actress_info（lines 454-473）
# ---------------------------------------------------------------------------

class TestGetActressInfo:
    def test_with_search_results(self):
        s = _make_scraper()
        s.safe_scrape = AsyncMock(return_value={
            "search_results": [{"title": "V1"}, {"title": "V2"}]
        })
        result = _run(s.get_actress_info("田中みな実"))
        assert result["total_works"] == 2

    def test_without_search_results(self):
        s = _make_scraper()
        s.safe_scrape = AsyncMock(return_value={})
        result = _run(s.get_actress_info("田中みな実"))
        assert result["total_works"] == 0

    def test_exception_returns_error_dict(self):
        """例外時應回傳錯誤字典而非拋出（lines 471-478）"""
        s = _make_scraper()
        s.safe_scrape = AsyncMock(side_effect=RuntimeError("fail"))
        result = _run(s.get_actress_info("田中みな実"))
        assert "error" in result
        assert result["total_works"] == 0


# ---------------------------------------------------------------------------
# _is_temporary_batch_search_error（lines 481-483）
# ---------------------------------------------------------------------------

class TestIsTemporaryBatchSearchError:
    def _make_client_response_error(self, status: int):
        req_info = MagicMock()
        req_info.real_url = "http://test.com"
        return aiohttp.ClientResponseError(req_info, (), status=status)

    def test_client_response_error_429(self):
        s = _make_scraper()
        err = self._make_client_response_error(429)
        assert s._is_temporary_batch_search_error(err) is True

    def test_client_response_error_404_not_temporary(self):
        s = _make_scraper()
        err = self._make_client_response_error(404)
        assert s._is_temporary_batch_search_error(err) is False

    def test_timeout_error_is_temporary(self):
        s = _make_scraper()
        assert s._is_temporary_batch_search_error(TimeoutError()) is True

    def test_connection_error_is_temporary(self):
        s = _make_scraper()
        assert s._is_temporary_batch_search_error(aiohttp.ClientConnectionError()) is True

    def test_other_error_not_temporary(self):
        s = _make_scraper()
        assert s._is_temporary_batch_search_error(ValueError("x")) is False


# ---------------------------------------------------------------------------
# _notify_batch_search_progress（lines 495-498）
# ---------------------------------------------------------------------------

class TestNotifyBatchSearchProgress:
    def test_calls_callback(self):
        s = _make_scraper()
        calls = []
        s._notify_batch_search_progress(lambda *a: calls.append(a), 5, 10, "STARS-001")
        assert calls == [(5, 10, "STARS-001")]

    def test_none_callback_does_nothing(self):
        s = _make_scraper()
        s._notify_batch_search_progress(None, 5, 10, "STARS-001")

    def test_callback_exception_silenced(self):
        s = _make_scraper()
        def bad_cb(*a):
            raise RuntimeError("callback failed")
        s._notify_batch_search_progress(bad_cb, 1, 5, "X-001")


# ---------------------------------------------------------------------------
# _build_batch_search_result + _determine_batch_search_status（lines 686-731）
# ---------------------------------------------------------------------------

class TestBuildBatchSearchResult:
    def test_build_result_with_actresses(self):
        s = _make_scraper()
        raw = {"unique_actresses": ["田中みな実"], "found": True}
        result = s._build_batch_search_result("STARS-001", "http://url", raw)
        assert result["actress_count"] == 1
        assert result["search_status"] == "searched_found"

    def test_status_video_not_found(self):
        """found=False 應回傳 video_not_found 狀態（lines 690-691）"""
        s = _make_scraper()
        raw = {"unique_actresses": [], "found": False}
        result = s._build_batch_search_result("STARS-001", "http://url", raw)
        assert result["search_status"] == "video_not_found"

    def test_status_no_actress_found(self):
        """找到頁面但沒有女優（lines 694-697）"""
        s = _make_scraper()
        raw = {"unique_actresses": [], "found": True}
        result = s._build_batch_search_result("STARS-001", "http://url", raw)
        assert result["search_status"] == "no_actress_found"

    def test_status_search_error_when_too_many(self):
        """超過10位女優時應回傳 search_error（lines 700-703）"""
        s = _make_scraper()
        actresses = [f"女優{i:02d}" for i in range(11)]
        raw = {"unique_actresses": actresses, "found": True}
        result = s._build_batch_search_result("STARS-001", "http://url", raw)
        assert result["search_status"] == "search_error"
        assert result["actresses"] == []

    def test_status_searched_multiple_when_4_to_10(self):
        """4-10位女優時應回傳 searched_multiple（lines 705-709）"""
        s = _make_scraper()
        actresses = [f"女優{i:02d}" for i in range(5)]
        raw = {"unique_actresses": actresses, "found": True}
        result = s._build_batch_search_result("STARS-001", "http://url", raw)
        assert result["search_status"] == "searched_multiple"


# ---------------------------------------------------------------------------
# _extract_batch_actresses（lines 678-683）
# ---------------------------------------------------------------------------

class TestExtractBatchActresses:
    def test_uses_unique_actresses(self):
        s = _make_scraper()
        result = s._extract_batch_actresses({"unique_actresses": ["田中みな実"]})
        assert result == ["田中みな実"]

    def test_falls_back_to_actresses(self):
        s = _make_scraper()
        result = s._extract_batch_actresses({"actresses": ["桃乃木かな"]})
        assert result == ["桃乃木かな"]

    def test_returns_empty_when_no_actresses(self):
        """沒有女優時應回傳空列表（lines 678-683）"""
        s = _make_scraper()
        result = s._extract_batch_actresses({})
        assert result == []


# ---------------------------------------------------------------------------
# _build_batch_error_result（line 737）
# ---------------------------------------------------------------------------

class TestBuildBatchErrorResult:
    def test_builds_error_result(self):
        result = AVWikiScraper._build_batch_error_result("STARS-001", "timeout", "TimeoutError")
        assert result["video_code"] == "STARS-001"
        assert result["actresses"] == []
        assert "error" in result
        assert result["error_type"] == "TimeoutError"


# ---------------------------------------------------------------------------
# _summarize_batch_search_results（lines 574-602）
# ---------------------------------------------------------------------------

class TestSummarizeBatchSearchResults:
    def test_counts_success_error_no_actress(self):
        s = _make_scraper()
        items = [
            ("STARS-001", {"actress_count": 1}),   # success
            ("STARS-002", {"error": "timeout", "error_type": "T"}),  # error
            ("STARS-003", {"actress_count": 0}),   # no_actress
        ]
        results, success, error, no_actress = s._summarize_batch_search_results(items)
        assert success == 1
        assert error == 1
        assert no_actress == 1

    def test_handles_exception_items(self):
        """Exception 項目應計入 error_count（lines 596-600）"""
        s = _make_scraper()
        items = [
            ("STARS-001", {"actress_count": 1}),
            RuntimeError("task failed"),
        ]
        results, success, error, no_actress = s._summarize_batch_search_results(items)
        assert error == 1


# ---------------------------------------------------------------------------
# _search_single_video_batch error paths（lines 534-572）
# ---------------------------------------------------------------------------

class TestSearchSingleVideoBatch:
    def _make_batch_components(self):
        semaphore = asyncio.Semaphore(1)
        lock = asyncio.Lock()
        controller = MagicMock()
        controller.report_success = MagicMock()
        controller.report_failure = MagicMock()
        controller.get_concurrency = MagicMock(return_value=5)
        backoff = MagicMock()
        backoff.next_delay = MagicMock(return_value=0.0)
        backoff.reset = MagicMock()
        return semaphore, lock, controller, backoff

    def test_success_path(self):
        s = _make_scraper()
        semaphore, lock, controller, backoff = self._make_batch_components()
        s.scrape_url = AsyncMock(return_value={"unique_actresses": ["田中みな実"], "found": True})
        code, result = _run(s._search_single_video_batch(
            "STARS-001", 1, semaphore, lock, None, controller, backoff, [0]
        ))
        assert code == "STARS-001"
        assert result["actress_count"] >= 1

    def test_client_response_error_temporary(self):
        """ClientResponseError 429 應觸發退避並回傳錯誤（lines 538-557）"""
        s = _make_scraper()
        semaphore, lock, controller, backoff = self._make_batch_components()
        req_info = MagicMock()
        req_info.real_url = "http://test.com"
        err = aiohttp.ClientResponseError(req_info, (), status=429)
        s.scrape_url = AsyncMock(side_effect=err)
        with patch("asyncio.sleep", new=AsyncMock()):
            code, result = _run(s._search_single_video_batch(
                "STARS-001", 1, semaphore, lock, None, controller, backoff, [0]
            ))
        assert code == "STARS-001"
        assert "error" in result
        controller.report_failure.assert_called_once()

    def test_timeout_error(self):
        """TimeoutError 應回傳錯誤結果（lines 534-557）"""
        s = _make_scraper()
        semaphore, lock, controller, backoff = self._make_batch_components()
        s.scrape_url = AsyncMock(side_effect=TimeoutError("timeout"))
        with patch("asyncio.sleep", new=AsyncMock()):
            code, result = _run(s._search_single_video_batch(
                "STARS-001", 1, semaphore, lock, None, controller, backoff, [0]
            ))
        assert "error" in result

    def test_generic_exception(self):
        """其他例外應回傳錯誤結果（lines 558-572）"""
        s = _make_scraper()
        semaphore, lock, controller, backoff = self._make_batch_components()
        s.scrape_url = AsyncMock(side_effect=ValueError("unexpected"))
        code, result = _run(s._search_single_video_batch(
            "STARS-001", 1, semaphore, lock, None, controller, backoff, [0]
        ))
        assert "error" in result
