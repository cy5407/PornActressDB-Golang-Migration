"""
補充 javdb_scraper.py 覆蓋率測試

策略：
- 純邏輯函式（parse_retry_after, extract_*, parse_content）直接呼叫
- async 方法用 AsyncMock 模擬 safe_scrape / scrape_url
- scrape_url 用 MagicMock 模擬 aiohttp session
"""
import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from src.scrapers.base_scraper import ErrorType, ScrapingException
from src.scrapers.sources.javdb_scraper import (
    JAVDBScraper,
    _parse_retry_after_value,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scraper() -> JAVDBScraper:
    with patch("src.scrapers.sources.javdb_scraper.ActressNameFilter"):
        s = JAVDBScraper()
    return s


def _run(coro):
    return asyncio.run(coro)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# _parse_retry_after_value（lines 27-35）
# ---------------------------------------------------------------------------

class TestParseRetryAfter:
    def test_none_returns_none(self):
        assert _parse_retry_after_value(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_retry_after_value("") is None

    def test_valid_int_returns_int(self):
        assert _parse_retry_after_value("60") == 60

    def test_zero_returns_none(self):
        assert _parse_retry_after_value("0") is None

    def test_negative_returns_none(self):
        assert _parse_retry_after_value("-5") is None

    def test_non_numeric_returns_none(self):
        assert _parse_retry_after_value("Wed, 21 Oct 2023") is None

    def test_whitespace_stripped(self):
        assert _parse_retry_after_value("  30  ") == 30


# ---------------------------------------------------------------------------
# parse_content（lines 112-123）
# ---------------------------------------------------------------------------

class TestParseContent:
    def test_search_url_calls_parse_search_results(self):
        s = _make_scraper()
        html = '<div class="item"><a href="/v/abc"><div class="video-title">TEST-001</div></a></div>'
        result = s.parse_content(html, "https://javdb.com/search?q=TEST-001")
        assert "search_results" in result

    def test_detail_url_calls_parse_detail_page(self):
        s = _make_scraper()
        html = '<h2 class="title">STARS-001 Test Title</h2>'
        result = s.parse_content(html, "https://javdb.com/v/abc123")
        assert "title" in result

    def test_parse_exception_raises_scraping_exception(self):
        s = _make_scraper()
        s._parse_search_results = MagicMock(side_effect=ValueError("parse error"))
        with pytest.raises(ScrapingException):
            s.parse_content("<html/>", "https://javdb.com/search?q=x")


# ---------------------------------------------------------------------------
# _parse_search_result_item（lines 126-143）
# ---------------------------------------------------------------------------

class TestParseSearchResultItem:
    def test_no_link_element_returns_none(self):
        s = _make_scraper()
        item = _soup("<div></div>").find("div")
        assert s._parse_search_result_item(item) is None

    def test_item_with_actress_and_title(self):
        s = _make_scraper()
        s._is_valid_actress_name = lambda name: True
        html = '''
        <div>
            <a href="/v/abc123"><div class="video-title">STARS-001 Test</div></a>
            <a href="/actors/1234">田中みな実</a>
            <a href="/makers/999">S1</a>
            <div class="meta">2023-01-15 120min</div>
        </div>'''
        item = _soup(html).find("div")
        result = s._parse_search_result_item(item)
        assert result is not None
        assert result["title"] == "STARS-001 Test"
        assert "田中みな実" in result["actresses"]
        assert result["studio"] == "S1"
        assert result["release_date"] == "2023-01-15"

    def test_item_without_title_and_actress_returns_none(self):
        s = _make_scraper()
        s._is_valid_actress_name = lambda name: False
        html = '<div><a href="/v/abc"></a></div>'
        item = _soup(html).find("div")
        result = s._parse_search_result_item(item)
        assert result is None

    def test_item_no_date_match(self):
        s = _make_scraper()
        s._is_valid_actress_name = lambda name: True
        html = '''
        <div>
            <a href="/v/abc"><div class="video-title">T-001</div></a>
            <a href="/actors/1">女優A</a>
            <div class="meta">no-date-here</div>
        </div>'''
        item = _soup(html).find("div")
        result = s._parse_search_result_item(item)
        assert result["release_date"] is None


# ---------------------------------------------------------------------------
# _parse_search_results（lines 147-155）
# ---------------------------------------------------------------------------

class TestParseSearchResults:
    def test_empty_soup_returns_empty_results(self):
        s = _make_scraper()
        result = s._parse_search_results(_soup("<div/>"))
        assert result["search_results"] == []
        assert result["total_results"] == 0

    def test_item_parse_exception_is_skipped(self):
        s = _make_scraper()
        s._parse_search_result_item = MagicMock(side_effect=ValueError("boom"))
        html = '<div class="item"><a href="/v/abc">Title</a></div>'
        result = s._parse_search_results(_soup(html))
        assert result["total_results"] == 0


# ---------------------------------------------------------------------------
# _build_detail_page_result（lines 168-190）
# ---------------------------------------------------------------------------

class TestBuildDetailPageResult:
    def test_title_and_cover_extracted(self):
        s = _make_scraper()
        html = '''
        <html>
            <h2 class="title">STARS-001 Test Title</h2>
            <img class="video-cover" src="https://example.com/cover.jpg"/>
        </html>'''
        result = s._build_detail_page_result(_soup(html))
        assert result["title"] == "STARS-001 Test Title"
        assert result["cover_url"] == "https://example.com/cover.jpg"

    def test_no_title_no_cover(self):
        s = _make_scraper()
        result = s._build_detail_page_result(_soup("<html/>"))
        assert result["title"] is None
        assert result["cover_url"] is None


# ---------------------------------------------------------------------------
# _extract_studio_code_from_title（lines 194-198）
# ---------------------------------------------------------------------------

class TestExtractStudioCode:
    def test_extracts_code_from_title(self):
        assert JAVDBScraper._extract_studio_code_from_title("STARS-001 Title") == "STARS"

    def test_none_title_returns_none(self):
        assert JAVDBScraper._extract_studio_code_from_title(None) is None

    def test_no_code_returns_none(self):
        assert JAVDBScraper._extract_studio_code_from_title("No Code Here") is None


# ---------------------------------------------------------------------------
# _extract_detail_panel_data / _apply_detail_panel（lines 200-244）
# ---------------------------------------------------------------------------

class TestExtractDetailPanelData:
    def _make_panel(self, label: str, content: str) -> BeautifulSoup:
        html = f'<div class="panel-block"><strong>{label}</strong>{content}</div>'
        return _soup(html).find("div")

    def test_actress_panel(self):
        s = _make_scraper()
        s._is_valid_actress_name = lambda name: True
        panel = self._make_panel("演員", '<a href="/actors/1">田中みな実</a>')
        result = s._extract_detail_panel_data([panel])
        assert "田中みな実" in result["actresses"]

    def test_studio_panel(self):
        s = _make_scraper()
        panel = self._make_panel("片商", '<a href="/makers/1">S1</a>')
        result = s._extract_detail_panel_data([panel])
        assert result["studio"] == "S1"

    def test_date_panel(self):
        s = _make_scraper()
        panel = self._make_panel("發行日期", "2023-05-10")
        result = s._extract_detail_panel_data([panel])
        assert result["release_date"] == "2023-05-10"

    def test_duration_panel(self):
        s = _make_scraper()
        panel = self._make_panel("時長", "120分鐘")
        result = s._extract_detail_panel_data([panel])
        assert result["duration"] == "120分鐘"

    def test_director_panel(self):
        s = _make_scraper()
        panel = self._make_panel("導演", '<a href="/directors/1">山田太郎</a>')
        result = s._extract_detail_panel_data([panel])
        assert result["director"] == "山田太郎"

    def test_series_panel(self):
        s = _make_scraper()
        panel = self._make_panel("系列", '<a href="/series/1">人妻シリーズ</a>')
        result = s._extract_detail_panel_data([panel])
        assert result["series"] == "人妻シリーズ"

    def test_categories_panel(self):
        s = _make_scraper()
        panel = self._make_panel(
            "類別", '<a href="/genres/1">巨乳</a><a href="/genres/2">単体</a>'
        )
        result = s._extract_detail_panel_data([panel])
        assert "巨乳" in result["categories"]

    def test_panel_without_label_skipped(self):
        """沒有 strong label 的 panel 應被跳過（line 217）"""
        s = _make_scraper()
        panel = _soup('<div class="panel-block">no label</div>').find("div")
        result = s._extract_detail_panel_data([panel])
        assert result["actresses"] == []

    def test_panel_exception_is_silenced(self):
        """panel 解析例外應被靜默處理（lines 221-222）"""
        s = _make_scraper()
        s._apply_detail_panel = MagicMock(side_effect=RuntimeError("boom"))
        panel = self._make_panel("演員", '<a href="/actors/1">Test</a>')
        # should not raise
        result = s._extract_detail_panel_data([panel])
        assert result["actresses"] == []


# ---------------------------------------------------------------------------
# _extract_rating（lines 287-298）
# ---------------------------------------------------------------------------

class TestExtractRating:
    def test_none_element_returns_none(self):
        assert JAVDBScraper._extract_rating(None) is None

    def test_valid_rating_extracted(self):
        elem = _soup('<span class="score">8.5分</span>').find("span")
        assert JAVDBScraper._extract_rating(elem) == 8.5

    def test_no_numeric_returns_none(self):
        elem = _soup('<span class="score">N/A</span>').find("span")
        assert JAVDBScraper._extract_rating(elem) is None


# ---------------------------------------------------------------------------
# _extract_panel_date / _extract_panel_duration / _extract_panel_categories
# ---------------------------------------------------------------------------

class TestStaticPanelExtractors:
    def test_extract_panel_date_found(self):
        assert JAVDBScraper._extract_panel_date("發行日期: 2023-05-10") == "2023-05-10"

    def test_extract_panel_date_not_found(self):
        assert JAVDBScraper._extract_panel_date("no date") is None

    def test_extract_panel_duration_found(self):
        assert JAVDBScraper._extract_panel_duration("120") == "120分鐘"

    def test_extract_panel_duration_not_found(self):
        assert JAVDBScraper._extract_panel_duration("") is None

    def test_extract_panel_categories(self):
        panel = _soup(
            '<div><a href="/genres/1">巨乳</a><a href="/genres/2">単体</a></div>'
        ).find("div")
        cats = JAVDBScraper._extract_panel_categories(panel, r"/genres/")
        assert cats == ["巨乳", "単体"]

    def test_extract_first_link_text_with_pattern(self):
        panel = _soup('<div><a href="/makers/1">S1</a></div>').find("div")
        assert JAVDBScraper._extract_first_link_text(panel, r"/makers/") == "S1"

    def test_extract_first_link_text_no_pattern(self):
        panel = _soup('<div><a href="/any">Link</a></div>').find("div")
        assert JAVDBScraper._extract_first_link_text(panel) == "Link"

    def test_extract_first_link_text_no_link_returns_none(self):
        panel = _soup("<div>no link</div>").find("div")
        assert JAVDBScraper._extract_first_link_text(panel) is None


# ---------------------------------------------------------------------------
# _build_empty_search_video_result（line 344）
# ---------------------------------------------------------------------------

class TestBuildEmptySearchVideoResult:
    def test_builds_correct_structure(self):
        result = JAVDBScraper._build_empty_search_video_result("STARS-001", "http://url")
        assert result["video_code"] == "STARS-001"
        assert result["actresses"] == []
        assert "未找到" in result["message"]


# ---------------------------------------------------------------------------
# search_video（lines 306-322）
# ---------------------------------------------------------------------------

class TestSearchVideo:
    def test_search_video_found_with_detail_url(self):
        s = _make_scraper()
        s.safe_scrape = AsyncMock(side_effect=[
            {"search_results": [{"detail_url": "http://javdb.com/v/abc", "title": "STARS-001"}]},
            {"title": "STARS-001 Title", "actresses": ["田中みな実"]},
        ])
        result = _run(s.search_video("STARS-001"))
        assert "video_code" in result
        assert result["video_code"] == "STARS-001"

    def test_search_video_no_results(self):
        s = _make_scraper()
        s.safe_scrape = AsyncMock(return_value={"search_results": []})
        result = _run(s.search_video("NOTFOUND-999"))
        assert result["video_code"] == "NOTFOUND-999"
        assert result["actresses"] == []

    def test_search_video_exception_raises_scraping_exception(self):
        s = _make_scraper()
        s.safe_scrape = AsyncMock(side_effect=RuntimeError("network"))
        with pytest.raises(ScrapingException):
            _run(s.search_video("STARS-001"))

    def test_finalize_result_without_detail_url(self):
        """search_result 沒有 detail_url 時應直接回傳 first_result（line 339）"""
        s = _make_scraper()
        first_result = {"title": "STARS-001", "actresses": ["女優A"]}
        s.safe_scrape = AsyncMock(return_value={"search_results": [first_result]})
        result = _run(s.search_video("STARS-001"))
        assert result["video_code"] == "STARS-001"

    def test_finalize_result_with_title_validates_content(self):
        """detail_result 有 title 時應進行內容品質驗證（lines 333-336）"""
        s = _make_scraper()
        s.safe_scrape = AsyncMock(side_effect=[
            {"search_results": [{"detail_url": "http://javdb.com/v/x"}]},
            {"title": "STARS-001 タイトル", "actresses": []},
        ])
        with patch("src.scrapers.sources.javdb_scraper.validate_japanese_content", return_value=0.9) as mock_validate:
            result = _run(s.search_video("STARS-001"))
        mock_validate.assert_called_once()
        assert result.get("content_quality") == 0.9


# ---------------------------------------------------------------------------
# get_actress_info（lines 353-387）
# ---------------------------------------------------------------------------

class TestGetActressInfo:
    def test_with_search_results(self):
        s = _make_scraper()
        s.safe_scrape = AsyncMock(return_value={
            "search_results": [
                {"title": "V1", "studio": "S1"},
                {"title": "V2", "studio": "S1"},
                {"title": "V3", "studio": None},
            ]
        })
        result = _run(s.get_actress_info("田中みな実"))
        assert result["total_works"] == 3
        assert result["studio_distribution"]["S1"] == 2

    def test_without_search_results_key(self):
        s = _make_scraper()
        s.safe_scrape = AsyncMock(return_value={})
        result = _run(s.get_actress_info("Unknown"))
        assert result["total_works"] == 0
        assert result["works"] == []

    def test_exception_raises_scraping_exception(self):
        s = _make_scraper()
        s.safe_scrape = AsyncMock(side_effect=RuntimeError("error"))
        with pytest.raises(ScrapingException):
            _run(s.get_actress_info("田中みな実"))


# ---------------------------------------------------------------------------
# scrape_url（lines 62-108）
# ---------------------------------------------------------------------------

def _make_mock_response(status: int, content: bytes = b"<html><h2 class='title'>T</h2></html>", headers: dict = None):
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
        session = _make_mock_session(resp)
        with patch("aiohttp.ClientSession", return_value=session):
            with pytest.raises(ScrapingException) as exc_info:
                _run(s.scrape_url("http://javdb.com/v/missing"))
        assert exc_info.value.error_type == ErrorType.CLIENT_ERROR

    def test_500_raises_server_error(self):
        s = _make_scraper()
        resp = _make_mock_response(500)
        session = _make_mock_session(resp)
        with patch("aiohttp.ClientSession", return_value=session):
            with pytest.raises(ScrapingException) as exc_info:
                _run(s.scrape_url("http://javdb.com/v/broken"))
        assert exc_info.value.error_type == ErrorType.SERVER_ERROR

    def test_429_raises_rate_limit_error(self):
        s = _make_scraper()
        resp = _make_mock_response(429, headers={"Retry-After": "30"})
        session = _make_mock_session(resp)
        with patch("aiohttp.ClientSession", return_value=session):
            with pytest.raises(ScrapingException) as exc_info:
                _run(s.scrape_url("http://javdb.com/v/ratelimited"))
        assert exc_info.value.error_type == ErrorType.RATE_LIMIT_ERROR

    def test_200_returns_parsed_data(self):
        s = _make_scraper()
        resp = _make_mock_response(200, content=b"<html><h2 class='title'>STARS-001</h2></html>")
        session = _make_mock_session(resp)
        with patch("aiohttp.ClientSession", return_value=session):
            result = _run(s.scrape_url("http://javdb.com/v/ok"))
        assert result["source"] == "JAVDB"

    def test_client_error_raises_network_error(self):
        import aiohttp as aiohttp_mod
        s = _make_scraper()
        session = MagicMock()
        session.get = MagicMock(side_effect=aiohttp_mod.ClientError("conn"))
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            with pytest.raises(ScrapingException) as exc_info:
                _run(s.scrape_url("http://javdb.com/v/broken"))
        assert exc_info.value.error_type == ErrorType.NETWORK_ERROR

    def test_unknown_exception_raises_unknown_error(self):
        s = _make_scraper()
        session = MagicMock()
        session.get = MagicMock(side_effect=ValueError("unexpected"))
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            with pytest.raises(ScrapingException) as exc_info:
                _run(s.scrape_url("http://javdb.com/v/crash"))
        assert exc_info.value.error_type == ErrorType.UNKNOWN_ERROR
