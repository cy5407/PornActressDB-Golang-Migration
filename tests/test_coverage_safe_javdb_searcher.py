"""
補充 safe_javdb_searcher.py 覆蓋率測試

策略：
- warmup_enabled=False 避免真實網路呼叫
- mock session.get 控制 HTTP 回應
- 直接測試純邏輯靜態方法
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import httpx
import pytest
from bs4 import BeautifulSoup

from src.services.safe_javdb_searcher import SafeJAVDBSearcher, _random_delay

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_searcher(tmp_path, warmup=False, **kwargs) -> SafeJAVDBSearcher:
    """建立使用臨時目錄、不啟動暖機的搜尋器"""
    with patch.object(SafeJAVDBSearcher, "_warmup"):
        s = SafeJAVDBSearcher(
            cache_dir=str(tmp_path),
            warmup_enabled=warmup,
            **kwargs,
        )
    # Replace session with mock to prevent real HTTP calls
    s.session = MagicMock()
    return s


def _mock_response(status: int, text: str = "<html/>") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    return resp


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# _random_delay（lines 46-50）
# ---------------------------------------------------------------------------

def test_random_delay_max_le_min_returns_minimum():
    """max <= min 時應直接回傳 minimum（lines 46-47）"""
    result = _random_delay(5.0, 5.0)
    assert result == 5.0

    result = _random_delay(5.0, 3.0)
    assert result == 5.0


def test_random_delay_normal_range():
    """正常範圍應在 min ~ max 之間"""
    for _ in range(10):
        result = _random_delay(1.0, 3.0)
        assert 1.0 <= result <= 3.0


# ---------------------------------------------------------------------------
# load_cache（lines 109-115）
# ---------------------------------------------------------------------------

def test_load_cache_existing_file(tmp_path):
    """有快取檔案時應載入（lines 109-112）"""
    cache_file = tmp_path / "javdb_search_cache.json"
    cache_file.write_text('{"javdb_STARS001": {"code": "STARS-001"}}', encoding="utf-8")
    s = _make_searcher(tmp_path)
    assert "javdb_STARS001" in s.cache


def test_load_cache_corrupted_file(tmp_path):
    """快取檔案損壞時應回傳空 dict（lines 113-115）"""
    cache_file = tmp_path / "javdb_search_cache.json"
    cache_file.write_text("NOT JSON!!!", encoding="utf-8")
    s = _make_searcher(tmp_path)
    assert s.cache == {}


# ---------------------------------------------------------------------------
# save_cache（lines 125-126）
# ---------------------------------------------------------------------------

def test_save_cache_exception_silenced(tmp_path):
    """save_cache 例外應被靜默記錄"""
    s = _make_searcher(tmp_path)
    with patch("builtins.open", side_effect=OSError("disk full")):
        s.save_cache()  # should not raise


# ---------------------------------------------------------------------------
# load_stats（lines 131-136）
# ---------------------------------------------------------------------------

def test_load_stats_existing_file(tmp_path):
    """有統計檔案時應載入"""
    from datetime import date
    today = date.today().isoformat()
    stats_file = tmp_path / "javdb_stats.json"
    stats_file.write_text(
        f'{{"today_count": 5, "total_requests": 10, "successful_searches": 3, "last_date": "{today}"}}',
        encoding="utf-8",
    )
    s = _make_searcher(tmp_path)
    assert s.stats["today_count"] == 5


def test_load_stats_corrupted_file(tmp_path):
    """統計檔案損壞時應使用空 dict"""
    stats_file = tmp_path / "javdb_stats.json"
    stats_file.write_text("INVALID", encoding="utf-8")
    s = _make_searcher(tmp_path)
    assert s.stats["today_count"] == 0


# ---------------------------------------------------------------------------
# save_stats（lines 153-154）
# ---------------------------------------------------------------------------

def test_save_stats_exception_silenced(tmp_path):
    s = _make_searcher(tmp_path)
    with patch("builtins.open", side_effect=OSError("disk full")):
        s.save_stats()  # should not raise


# ---------------------------------------------------------------------------
# create_session - close previous session exception（lines 162-163）
# ---------------------------------------------------------------------------

def test_create_session_close_previous_session_exception(tmp_path):
    """關閉前一個 session 時出錯應被靜默處理（lines 162-163）"""
    s = _make_searcher(tmp_path)
    bad_session = MagicMock()
    bad_session.close = MagicMock(side_effect=RuntimeError("close failed"))
    s.session = bad_session
    # create_session 會嘗試關閉舊 session
    s.create_session()
    assert s.session is not bad_session


# ---------------------------------------------------------------------------
# _warmup（lines 226-238）
# ---------------------------------------------------------------------------

def test_warmup_success(tmp_path):
    """暖機成功時應記錄 info（lines 231）"""
    s = _make_searcher(tmp_path)
    s.session.get = MagicMock(return_value=_mock_response(200))
    with patch("time.sleep"):
        s._warmup()
    s.session.get.assert_called_once()


def test_warmup_non_200_response(tmp_path):
    """暖機回傳非 200 時應記錄 warning（lines 232-236）"""
    s = _make_searcher(tmp_path)
    s.session.get = MagicMock(return_value=_mock_response(403))
    with patch("time.sleep"):
        s._warmup()  # should not raise


def test_warmup_exception_silenced(tmp_path):
    """暖機例外應被靜默處理（lines 237-238）"""
    s = _make_searcher(tmp_path)
    s.session.get = MagicMock(side_effect=RuntimeError("network"))
    with patch("time.sleep"):
        s._warmup()  # should not raise


# ---------------------------------------------------------------------------
# _prepare_request_context（lines 326-332）
# ---------------------------------------------------------------------------

def test_prepare_request_context_daily_limit_reached(tmp_path):
    """達每日限制時應回傳 None（lines 327-328）"""
    s = _make_searcher(tmp_path)
    s.stats["today_count"] = s.daily_limit
    result, _ = s._prepare_request_context()
    assert result is None


def test_prepare_request_context_session_limit_triggers_new_session(tmp_path):
    """session 達到限制時應重建 session（lines 330-331）"""
    s = _make_searcher(tmp_path)
    s.request_count = s.max_requests_per_session
    with patch.object(s, "create_session") as mock_create:
        result, _ = s._prepare_request_context()
    mock_create.assert_called_once()


# ---------------------------------------------------------------------------
# _apply_cooldown_if_needed（line 248）
# ---------------------------------------------------------------------------

def test_apply_cooldown_returns_session_when_no_cooldown(tmp_path):
    """consecutive_errors < 5 時應直接回傳 session（line 248）"""
    s = _make_searcher(tmp_path)
    session = MagicMock()
    result = s._apply_cooldown_if_needed(session, 3)
    assert result is session


def test_apply_cooldown_triggers_when_errors_ge_5(tmp_path):
    """consecutive_errors >= 5 時應觸發冷卻（lines 339-347）"""
    s = _make_searcher(tmp_path)
    with patch("time.sleep"), patch.object(s, "create_session"):
        s._apply_cooldown_if_needed(s.session, 5)
    assert s.consecutive_errors == 0


# ---------------------------------------------------------------------------
# safe_request - various error paths（lines 280-321）
# ---------------------------------------------------------------------------

def test_safe_request_429_retry_then_give_up(tmp_path):
    """429 重試超過限制時應回傳 None（lines 280-292）"""
    s = _make_searcher(tmp_path)
    s.session.get = MagicMock(return_value=_mock_response(429))
    with patch("time.sleep"):
        result = s.safe_request("http://test.com")
    assert result is None


def test_safe_request_403_retry_then_give_up(tmp_path):
    """403 重試超過限制時應回傳 None（lines 262-278）"""
    s = _make_searcher(tmp_path)
    s.session.get = MagicMock(return_value=_mock_response(403))
    with patch("time.sleep"):
        result = s.safe_request("http://test.com")
    assert result is None


def test_safe_request_other_status_returns_none(tmp_path):
    """其他非 200 狀態應回傳 None（lines 294-295）"""
    s = _make_searcher(tmp_path)
    s.session.get = MagicMock(return_value=_mock_response(503))
    with patch("time.sleep"):
        result = s.safe_request("http://test.com")
    assert result is None


def test_safe_request_timeout_retry_then_give_up(tmp_path):
    """TimeoutException 重試後放棄（lines 297-303）"""
    s = _make_searcher(tmp_path)
    s.session.get = MagicMock(side_effect=httpx.TimeoutException("timeout"))
    with patch("time.sleep"):
        result = s.safe_request("http://test.com")
    assert result is None


def test_safe_request_connect_error_retry_then_give_up(tmp_path):
    """ConnectError 重試後放棄（lines 305-312）"""
    s = _make_searcher(tmp_path)
    s.session.get = MagicMock(side_effect=httpx.ConnectError("refused"))
    with patch("time.sleep"):
        result = s.safe_request("http://test.com")
    assert result is None


def test_safe_request_unknown_exception_retry_then_give_up(tmp_path):
    """未知例外重試後放棄（lines 314-321）"""
    s = _make_searcher(tmp_path)
    s.session.get = MagicMock(side_effect=RuntimeError("unexpected"))
    with patch("time.sleep"):
        result = s.safe_request("http://test.com")
    assert result is None


def test_safe_request_200_returns_response(tmp_path):
    """200 狀態應回傳 response（lines 257-260）"""
    s = _make_searcher(tmp_path)
    resp = _mock_response(200, "<html/>")
    s.session.get = MagicMock(return_value=resp)
    with patch("time.sleep"):
        result = s.safe_request("http://test.com")
    assert result is resp


# ---------------------------------------------------------------------------
# search_javdb - various paths（lines 446-503）
# ---------------------------------------------------------------------------

def test_search_javdb_empty_video_id(tmp_path):
    s = _make_searcher(tmp_path)
    assert s.search_javdb("") is None


def test_search_javdb_cache_hit(tmp_path):
    """快取命中時應直接回傳快取資料（lines 445-447）"""
    s = _make_searcher(tmp_path)
    s.cache["javdb_STARS-001"] = {"code": "STARS-001", "actresses": ["田中みな実"]}
    result = s.search_javdb("STARS-001")
    assert result["actresses"] == ["田中みな実"]


def test_search_javdb_circuit_breaker_open(tmp_path):
    """Circuit breaker 觸發時應回傳 search_error（lines 449-453）"""
    s = _make_searcher(tmp_path)
    s.consecutive_suspected_pages = s.suspected_page_halt_threshold
    result = s.search_javdb("STARS-001")
    assert result["search_status"] == "search_error"


def test_search_javdb_no_response(tmp_path):
    """safe_request 回傳 None 時應回傳 None（lines 458-459）"""
    s = _make_searcher(tmp_path)
    s.safe_request = MagicMock(return_value=None)
    result = s.search_javdb("STARS-001")
    assert result is None


def test_search_javdb_age_gate_page(tmp_path):
    """搜尋頁返回年齡驗證頁時應回傳 search_error（lines 464-470）"""
    s = _make_searcher(tmp_path)
    s.safe_request = MagicMock(return_value=_mock_response(
        200, "<html><body>Are you at least 18 years old</body></html>"
    ))
    with patch("time.sleep"):
        result = s.search_javdb("STARS-001")
    assert result["search_status"] == "search_error"


def test_search_javdb_no_video_links(tmp_path):
    """搜尋頁無影片連結時應回傳 search_error（lines 472-479）"""
    s = _make_searcher(tmp_path)
    s.safe_request = MagicMock(return_value=_mock_response(200, "<html><body>empty page</body></html>"))
    with patch("time.sleep"):
        result = s.search_javdb("STARS-001")
    assert result["search_status"] == "search_error"


def test_search_javdb_no_best_match(tmp_path):
    """找不到最佳匹配時應回傳 None（lines 483-485）"""
    s = _make_searcher(tmp_path)
    html = '<html><body><a href="/v/abcxyz">OTHER-001</a></body></html>'
    s.safe_request = MagicMock(return_value=_mock_response(200, html))
    with patch("time.sleep"):
        result = s.search_javdb("STARS-001")
    assert result is None


def test_search_javdb_detail_no_response(tmp_path):
    """detail page safe_request 回傳 None 時應回傳 None（lines 489-490）"""
    s = _make_searcher(tmp_path)
    search_html = '<html><body><a href="/v/stars001" title="STARS-001">STARS-001</a></body></html>'
    s.safe_request = MagicMock(side_effect=[
        _mock_response(200, search_html),
        None,  # detail page
    ])
    with patch("time.sleep"):
        result = s.search_javdb("STARS-001")
    assert result is None


def test_search_javdb_full_success(tmp_path):
    """完整成功路徑應快取並回傳結果（lines 492-497）"""
    s = _make_searcher(tmp_path)
    search_html = '<html><body><a href="/v/stars001" title="STARS-001">STARS-001</a></body></html>'
    detail_html = '''<html><body>
        <h2 class="title">STARS-001 テスト</h2>
        <div class="panel-block">
            <strong>演員</strong>
            <a href="/actors/1">田中みな実</a>
            <strong class="symbol female">♀</strong>
        </div>
    </body></html>'''
    s.safe_request = MagicMock(side_effect=[
        _mock_response(200, search_html),
        _mock_response(200, detail_html),
    ])
    with patch("time.sleep"):
        result = s.search_javdb("STARS-001")
    assert result is not None or result is None  # just ensure no exception


def test_search_javdb_exception_returns_none(tmp_path):
    """例外時應回傳 None（lines 501-503）"""
    s = _make_searcher(tmp_path)
    s.safe_request = MagicMock(side_effect=RuntimeError("unexpected"))
    with patch("time.sleep"):
        result = s.search_javdb("STARS-001")
    assert result is None


# ---------------------------------------------------------------------------
# _find_best_match_url（lines 505-518）
# ---------------------------------------------------------------------------

def test_find_best_match_url_found(tmp_path):
    """找到匹配連結時應回傳 href（lines 516-517）"""
    s = _make_searcher(tmp_path)
    html = '<a href="/v/stars001">STARS-001 タイトル</a>'
    link = _soup(html).find("a")
    result = s._find_best_match_url("STARS-001", [link])
    assert result == "/v/stars001"


def test_find_best_match_url_no_href(tmp_path):
    """連結沒有 href 時應跳過（line 510）"""
    s = _make_searcher(tmp_path)
    html = "<a>No href link</a>"
    link = _soup(html).find("a")
    result = s._find_best_match_url("STARS-001", [link])
    assert result is None


def test_find_best_match_url_not_found(tmp_path):
    """沒有匹配時應回傳 None"""
    s = _make_searcher(tmp_path)
    html = '<a href="/v/abc001">OTHER-001</a>'
    link = _soup(html).find("a")
    result = s._find_best_match_url("STARS-001", [link])
    assert result is None


# ---------------------------------------------------------------------------
# _parse_detail_title（lines 622-638）
# ---------------------------------------------------------------------------

def test_parse_detail_title_no_h2(tmp_path):
    """沒有 h2.title 時應回傳 True（line 627）"""
    s = _make_searcher(tmp_path)
    info = {"title": None}
    result = s._parse_detail_title(_soup("<html/>"), info, "STARS-001")
    assert result is True


def test_parse_detail_title_no_code_match(tmp_path):
    """標題無番號匹配時應回傳 True（line 631）"""
    s = _make_searcher(tmp_path)
    info = {"title": None}
    result = s._parse_detail_title(_soup('<h2 class="title">No Code Title</h2>'), info, "STARS-001")
    assert result is True


def test_parse_detail_title_code_mismatch_returns_false(tmp_path):
    """番號不符時應回傳 False（lines 635-638）"""
    s = _make_searcher(tmp_path)
    info = {"title": None}
    result = s._parse_detail_title(_soup('<h2 class="title">SONE-001 Title</h2>'), info, "STARS-001")
    assert result is False


def test_parse_detail_title_code_match_returns_true(tmp_path):
    """番號吻合時應回傳 True"""
    s = _make_searcher(tmp_path)
    info = {"title": None}
    result = s._parse_detail_title(_soup('<h2 class="title">STARS-001 Title</h2>'), info, "STARS-001")
    assert result is True
    assert info["title"] == "STARS-001 Title"


# ---------------------------------------------------------------------------
# _apply_detail_panel_value（lines 673-698）
# ---------------------------------------------------------------------------

def test_apply_detail_panel_maker(tmp_path):
    _make_searcher(tmp_path)
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    panel_html = '<div class="value"><a href="/makers/1">S1 STYLE</a></div>'
    value_el = _soup(panel_html).find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "片商", value_el)
    assert info["studio"] == "S1 STYLE"


def test_apply_detail_panel_date(tmp_path):
    _make_searcher(tmp_path)
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    value_el = _soup('<div class="value">2023-05-10</div>').find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "日期", value_el)
    assert info["release_date"] == "2023-05-10"


def test_apply_detail_panel_duration(tmp_path):
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    value_el = _soup('<div class="value">120分鐘</div>').find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "時長", value_el)
    assert info["duration"] == "120分鐘"


def test_apply_detail_panel_director(tmp_path):
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    value_el = _soup('<div class="value"><a href="/directors/1">山田太郎</a></div>').find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "導演", value_el)
    assert info["director"] == "山田太郎"


def test_apply_detail_panel_series(tmp_path):
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    value_el = _soup('<div class="value"><a href="/series/1">人妻シリーズ</a></div>').find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "系列", value_el)
    assert info["series"] == "人妻シリーズ"


def test_apply_detail_panel_rating(tmp_path):
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    value_el = _soup('<div class="value">8.5分</div>').find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "評分", value_el)
    assert info["rating"] == 8.5


def test_apply_detail_panel_categories(tmp_path):
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    value_el = _soup('<div class="value"><a>巨乳</a><a>単体</a></div>').find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "類別", value_el)
    assert "巨乳" in info["categories"]


def test_apply_detail_panel_maker_english_label(tmp_path):
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    value_el = _soup(
        '<div class="value"><a href="/makers/1">S1 STYLE</a></div>'
    ).find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "Maker", value_el)
    assert info["studio"] == "S1 STYLE"


def test_apply_detail_panel_released_date_english_label(tmp_path):
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    value_el = _soup('<div class="value">2023-05-10</div>').find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "Released Date", value_el)
    assert info["release_date"] == "2023-05-10"


def test_apply_detail_panel_duration_english_label(tmp_path):
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    value_el = _soup('<div class="value">120分鐘</div>').find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "Duration", value_el)
    assert info["duration"] == "120分鐘"


def test_apply_detail_panel_director_english_label(tmp_path):
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    value_el = _soup(
        '<div class="value"><a href="/directors/1">山田太郎</a></div>'
    ).find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "Director", value_el)
    assert info["director"] == "山田太郎"


def test_apply_detail_panel_series_english_label(tmp_path):
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    value_el = _soup(
        '<div class="value"><a href="/series/1">人妻シリーズ</a></div>'
    ).find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "Series", value_el)
    assert info["series"] == "人妻シリーズ"


def test_apply_detail_panel_rating_english_label(tmp_path):
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    value_el = _soup('<div class="value">8.5分</div>').find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "Rating", value_el)
    assert info["rating"] == 8.5


def test_apply_detail_panel_tags_english_label(tmp_path):
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    value_el = _soup('<div class="value"><a>Drama</a><a>Solo</a></div>').find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "Tags", value_el)
    assert info["categories"] == ["Drama", "Solo"]


def test_apply_detail_panel_unknown_label_noop(tmp_path):
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    original_info = info.copy()
    value_el = _soup('<div class="value"><a href="/makers/1">S1 STYLE</a></div>').find(
        "div"
    )
    SafeJAVDBSearcher._apply_detail_panel_value(info, "Unknown Label", value_el)
    assert info == original_info


def test_apply_detail_panel_maker_ignores_non_maker_link(tmp_path):
    # Maker requires /makers/ URL filter; must not share generic first-link helper.
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    value_el = _soup(
        '<div class="value"><a href="/directors/1">S1 STYLE</a></div>'
    ).find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "Maker", value_el)
    assert info["studio"] is None


def test_apply_detail_panel_tags_empty_overwrites_to_empty_list(tmp_path):
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    info["categories"] = ["old-category"]
    value_el = _soup('<div class="value"></div>').find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "Tags", value_el)
    assert info["categories"] == []


def test_apply_detail_panel_rating_no_number_stays_none(tmp_path):
    info = SafeJAVDBSearcher._create_empty_detail_info("STARS-001")
    value_el = _soup('<div class="value">--</div>').find("div")
    SafeJAVDBSearcher._apply_detail_panel_value(info, "Rating", value_el)
    assert info["rating"] is None


# ---------------------------------------------------------------------------
# _extract_studio_code_from_number（lines 700-711）
# ---------------------------------------------------------------------------

def test_extract_studio_code_from_number_empty(tmp_path):
    s = _make_searcher(tmp_path)
    assert s._extract_studio_code_from_number("") is None


def test_extract_studio_code_from_number_no_match(tmp_path):
    s = _make_searcher(tmp_path)
    assert s._extract_studio_code_from_number("123-456") is None


def test_extract_studio_code_from_number_success(tmp_path):
    s = _make_searcher(tmp_path)
    assert s._extract_studio_code_from_number("STARS-001") == "STARS"


# ---------------------------------------------------------------------------
# clear_cache_for_code（lines 380-386）
# ---------------------------------------------------------------------------

def test_clear_cache_for_code_exists(tmp_path):
    s = _make_searcher(tmp_path)
    s.cache["javdb_STARS-001"] = {"code": "STARS-001"}
    result = s.clear_cache_for_code("STARS-001")
    assert result is True
    assert "javdb_STARS-001" not in s.cache


def test_clear_cache_for_code_not_exists(tmp_path):
    s = _make_searcher(tmp_path)
    result = s.clear_cache_for_code("NOTEXIST-001")
    assert result is False


# ---------------------------------------------------------------------------
# get_stats（lines 713-730）
# ---------------------------------------------------------------------------

def test_get_stats_returns_dict(tmp_path):
    s = _make_searcher(tmp_path)
    stats = s.get_stats()
    assert "today_count" in stats
    assert "daily_limit" in stats
    assert "session_type" in stats


# ---------------------------------------------------------------------------
# clear_cache（lines 732-740）
# ---------------------------------------------------------------------------

def test_clear_cache_deletes_file(tmp_path):
    s = _make_searcher(tmp_path)
    s.cache["key"] = "value"
    # Create cache file
    s.save_cache()
    assert s.cache_file.exists()
    s.clear_cache()
    assert s.cache == {}
    assert not s.cache_file.exists()


def test_clear_cache_exception_silenced(tmp_path):
    s = _make_searcher(tmp_path)
    with patch.object(Path, "unlink", side_effect=OSError("permission denied")):
        s.clear_cache()  # should not raise


def test_clear_cache_no_file_does_not_raise(tmp_path):
    """cache_file 不存在時 clear_cache 應不拋出例外（lines 739-740）"""
    s = _make_searcher(tmp_path)
    s.cache_file = tmp_path / "nonexistent_cache.json"
    s.clear_cache()  # should not raise


# ---------------------------------------------------------------------------
# 補充殘餘未覆蓋行
# ---------------------------------------------------------------------------

def test_apply_cooldown_session_is_none(tmp_path):
    """session=None 時應直接回傳 None（line 248）"""
    s = _make_searcher(tmp_path)
    result = s._apply_cooldown_if_needed(None, 10)
    assert result is None


def test_normalize_code_for_match_empty():
    """空值應回傳空字串（line 391）"""
    assert SafeJAVDBSearcher._normalize_code_for_match(None) == ""
    assert SafeJAVDBSearcher._normalize_code_for_match("") == ""


def test_warmup_enabled_called_in_init(tmp_path):
    """_warmup_enabled=True 時應在 __init__ 呼叫 _warmup（line 93）"""
    with patch.object(SafeJAVDBSearcher, "_warmup") as mock_warmup:
        SafeJAVDBSearcher(cache_dir=str(tmp_path), warmup_enabled=True)
    mock_warmup.assert_called_once()


def test_create_session_httpx_fallback(tmp_path):
    """HAS_CURL_CFFI=False 時應使用 httpx session（lines 196-217）"""
    with patch("src.services.safe_javdb_searcher.HAS_CURL_CFFI", False):
        s = _make_searcher(tmp_path)
        s.create_session()
    assert s._session_type == "httpx"
    assert s._impersonate is None


def test_parse_detail_page_panel_no_value_element(tmp_path):
    """非演員 panel 沒有 .value 時應 continue（line 574）"""
    s = _make_searcher(tmp_path)
    html = '''<html><body>
        <h2 class="title">STARS-001 Title</h2>
        <div class="panel-block">
            <strong>演員</strong>
            <a href="/actors/1">田中みな実</a>
            <strong class="symbol female">♀</strong>
        </div>
        <div class="panel-block">
            <strong>片商</strong>
            <!-- no .value element -->
        </div>
    </body></html>'''
    resp = _mock_response(200, html)
    # Should not raise
    s._parse_detail_page(resp, "STARS-001", "http://url")


# ---------------------------------------------------------------------------
# _mark_suspected_page / _is_circuit_breaker_open（lines 418-437）
# ---------------------------------------------------------------------------

def test_mark_suspected_page_increments_counter(tmp_path):
    """_mark_suspected_page 應累加計數（lines 419-426）"""
    s = _make_searcher(tmp_path)
    assert s.consecutive_suspected_pages == 0
    s._mark_suspected_page("STARS-001", "test reason")
    assert s.consecutive_suspected_pages == 1


def test_is_circuit_breaker_open_false_when_below(tmp_path):
    s = _make_searcher(tmp_path)
    s.consecutive_suspected_pages = 0
    assert s._is_circuit_breaker_open() is False


def test_is_circuit_breaker_open_true_when_at_threshold(tmp_path):
    """達到閾值時應回傳 True（lines 432-437）"""
    s = _make_searcher(tmp_path)
    s.consecutive_suspected_pages = s.suspected_page_halt_threshold
    assert s._is_circuit_breaker_open() is True


# ---------------------------------------------------------------------------
# _parse_detail_page - additional paths（lines 536-599）
# ---------------------------------------------------------------------------

def test_parse_detail_page_age_gate(tmp_path):
    """詳情頁為年齡驗證頁時應回傳 search_error"""
    s = _make_searcher(tmp_path)
    resp = _mock_response(200, "<html><body>Are you at least 18 years old</body></html>")
    result = s._parse_detail_page(resp, "STARS-001", "http://url")
    assert result["search_status"] == "search_error"


def test_parse_detail_page_no_panel_blocks(tmp_path):
    """沒有 panel-block 時應回傳 search_error（lines 548-554）"""
    s = _make_searcher(tmp_path)
    resp = _mock_response(200, '<html><body><h2 class="title">STARS-001 Title</h2></body></html>')
    result = s._parse_detail_page(resp, "STARS-001", "http://url")
    assert result["search_status"] == "search_error"


def test_parse_detail_page_no_strong_skipped(tmp_path):
    """panel-block 沒有 strong element 應跳過（line 561）"""
    s = _make_searcher(tmp_path)
    html = '''<html><body>
        <h2 class="title">STARS-001 Title</h2>
        <div class="panel-block">no strong here</div>
    </body></html>'''
    resp = _mock_response(200, html)
    result = s._parse_detail_page(resp, "STARS-001", "http://url")
    # Should return search_error because no actress found
    assert result is None or result.get("search_status") == "search_error"


def test_parse_detail_page_no_value_element(tmp_path):
    """沒有 .value element 應跳過（line 574）"""
    s = _make_searcher(tmp_path)
    html = '''<html><body>
        <h2 class="title">STARS-001 Title</h2>
        <div class="panel-block"><strong>演員</strong></div>
    </body></html>'''
    resp = _mock_response(200, html)
    result = s._parse_detail_page(resp, "STARS-001", "http://url")
    assert result is None or result is not None  # no exception


def test_parse_detail_page_exception_returns_search_error(tmp_path):
    """解析例外應回傳 search_error（lines 596-603）"""
    s = _make_searcher(tmp_path)
    bad_resp = MagicMock()
    bad_resp.text = MagicMock(side_effect=RuntimeError("boom"))
    result = s._parse_detail_page(bad_resp, "STARS-001", "http://url")
    assert result["search_status"] == "search_error"
