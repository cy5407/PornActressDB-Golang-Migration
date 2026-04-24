"""
web_searcher.py 覆蓋率補測
目標：覆蓋純邏輯方法與可 mock 的協作路徑，提升 Quality Gate 覆蓋率。
"""
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

# web_searcher.py 使用非 src. 前綴的 import，需要 src/ 在 sys.path 上
_SRC_DIR = str(Path(__file__).resolve().parents[1] / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from src.models.config import ConfigManager  # noqa: E402
from src.services import web_searcher as web_searcher_module  # noqa: E402
from src.services.safe_javdb_searcher import SafeJAVDBSearcher  # noqa: E402
from src.services.safe_searcher import SafeSearcher  # noqa: E402
from src.services.web_searcher import WebSearcher  # noqa: E402

# ---------- helpers ----------

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "web_searcher"


def _load_fixture_html(name: str) -> str:
    return (_FIXTURE_DIR / name).read_text(encoding="utf-8")

def _make_searcher(**attrs) -> WebSearcher:
    """Bypass __init__，手動設定屬性。"""
    searcher = object.__new__(WebSearcher)
    defaults = {
        "search_cache": {},
        "batch_size": 2,
        "thread_count": 2,
        "batch_delay": 0.0,
        "timeout": 5,
        "japanese_headers": {},
        "safe_searcher": SimpleNamespace(safe_request=lambda fn, url: None),
        "javdb_searcher": SimpleNamespace(search_javdb=lambda code: None),
        "studio_identifier": SimpleNamespace(
            normalize_studio_name=lambda studio, code: studio
        ),
    }
    defaults.update(attrs)
    for k, v in defaults.items():
        setattr(searcher, k, v)
    return searcher


def test_web_searcher_init_wires_real_dependencies(tmp_path):
    config_path = tmp_path / "config.ini"
    javdb_cache_dir = tmp_path / "javdb-cache"
    config_path.write_text(
        f"""
[search]
enable_cache = false
cache_dir = {javdb_cache_dir.as_posix()}
batch_size = 3
thread_count = 2
request_timeout = 7
avwiki_concurrent_enabled = false
avwiki_max_concurrent = 4
""",
        encoding="utf-8",
    )

    searcher = WebSearcher(ConfigManager(str(config_path)))

    assert isinstance(searcher.safe_searcher, SafeSearcher)
    assert isinstance(searcher.japanese_searcher, SafeSearcher)
    assert isinstance(searcher.javdb_searcher, SafeJAVDBSearcher)
    assert searcher.safe_searcher.config.enable_cache is False
    assert searcher.japanese_searcher.config.enable_cache is False
    assert searcher.batch_size == 3
    assert searcher.thread_count == 2
    assert searcher.timeout == 7
    assert searcher.avwiki_concurrent_enabled is False
    assert searcher.avwiki_max_concurrent == 4
    assert searcher.headers
    assert searcher.search_cache == {}


# ============================================================
# _build_code_candidates
# ============================================================

def test_build_code_candidates_no_alias_for_normal_code():
    s = _make_searcher()
    assert s._build_code_candidates("STARS-707") == ["STARS-707"]


def test_build_code_candidates_adds_alias_for_double_zero():
    s = _make_searcher()
    result = s._build_code_candidates("ABC-00123")
    assert result == ["ABC-00123", "ABC-123"]


# ============================================================
# _attach_alias_metadata
# ============================================================

def test_attach_alias_metadata_same_code():
    result = WebSearcher._attach_alias_metadata({"actresses": ["A"]}, "X-001", "X-001")
    assert result["searched_code"] == "X-001"
    assert "matched_code" not in result
    assert "search_alias_used" not in result


def test_attach_alias_metadata_different_code():
    result = WebSearcher._attach_alias_metadata({"actresses": ["A"]}, "X-00001", "X-001")
    assert result["searched_code"] == "X-00001"
    assert result["matched_code"] == "X-001"
    assert result["search_alias_used"] is True


def test_attach_alias_metadata_none_result():
    assert WebSearcher._attach_alias_metadata(None, "X-001", "X-001") is None


# ============================================================
# _has_usable_javdb_result
# ============================================================

def test_has_usable_javdb_result_with_actresses():
    assert WebSearcher._has_usable_javdb_result({"actresses": ["A"]}) is True


def test_has_usable_javdb_result_search_error():
    assert WebSearcher._has_usable_javdb_result({"search_status": "search_error"}) is True


def test_has_usable_javdb_result_none():
    assert WebSearcher._has_usable_javdb_result(None) is False


def test_has_usable_javdb_result_empty():
    assert WebSearcher._has_usable_javdb_result({}) is False


def test_has_usable_javdb_result_empty_actresses():
    assert WebSearcher._has_usable_javdb_result({"actresses": []}) is False


# ============================================================
# _build_search_error_result
# ============================================================

def test_build_search_error_result():
    result = WebSearcher._build_search_error_result("AV-WIKI (安全增強版)", "timeout")
    assert result["source"] == "AV-WIKI (安全增強版)"
    assert result["actresses"] == []
    assert result["search_status"] == "search_error"
    assert result["search_error_reason"] == "timeout"


# ============================================================
# _build_javdb_search_result
# ============================================================

def test_build_javdb_search_result_with_aliases():
    s = _make_searcher()
    s.studio_identifier = SimpleNamespace(
        normalize_studio_name=lambda studio, code: f"normalized-{studio}"
    )
    javdb_result = {
        "source": "JAVDB",
        "actresses": ["ActressA"],
        "studio": "S1",
        "studio_code": "SSIS",
        "release_date": "2024-01-01",
        "title": "Test Title",
        "duration": 120,
        "director": None,
        "series": None,
        "rating": "4.5",
        "categories": ["Drama", "Romance", "Action"],
        "search_status": None,
        "search_error_reason": None,
        "search_url": "https://javdb.com/v/abc",
    }
    result = s._build_javdb_search_result("SSIS-00001", "SSIS-001", javdb_result)
    assert result["studio"] == "normalized-S1"
    assert result["actresses"] == ["ActressA"]
    assert result["searched_code"] == "SSIS-00001"
    assert result["matched_code"] == "SSIS-001"


# ============================================================
# _log_javdb_result
# ============================================================

def test_log_javdb_result_with_actresses(caplog):
    import logging
    s = _make_searcher()
    result = {
        "actresses": ["ActressA"],
        "source": "JAVDB",
        "studio": "S1",
        "rating": "4.2",
        "categories": ["A", "B", "C", "D"],
    }
    with caplog.at_level(logging.INFO):
        s._log_javdb_result("SSIS-123", result)
    assert "ActressA" in caplog.text


def test_log_javdb_result_no_actresses(caplog):
    import logging
    s = _make_searcher()
    result = {"actresses": [], "search_error_reason": "timeout"}
    with caplog.at_level(logging.WARNING):
        s._log_javdb_result("SSIS-123", result)
    assert "暫時性異常" in caplog.text


def test_log_javdb_result_no_rating_no_categories(caplog):
    import logging
    s = _make_searcher()
    result = {"actresses": ["A"], "source": "JAVDB", "studio": None, "rating": None, "categories": []}
    with caplog.at_level(logging.INFO):
        s._log_javdb_result("SSIS-123", result)
    assert "A" in caplog.text


# ============================================================
# _is_actress_name
# ============================================================

def test_is_actress_name_valid_japanese():
    s = _make_searcher()
    assert s._is_actress_name("葵つかさ") is True


def test_is_actress_name_too_short():
    s = _make_searcher()
    assert s._is_actress_name("あ") is False


def test_is_actress_name_too_long():
    s = _make_searcher()
    assert s._is_actress_name("あ" * 21) is False


def test_is_actress_name_excluded_keyword():
    s = _make_searcher()
    assert s._is_actress_name("STARS123") is False


def test_is_actress_name_all_digits():
    s = _make_searcher()
    assert s._is_actress_name("123456") is False


def test_is_actress_name_no_cjk():
    s = _make_searcher()
    assert s._is_actress_name("HelloWorld") is False


def test_is_actress_name_empty():
    s = _make_searcher()
    assert s._is_actress_name("") is False


def test_is_actress_name_続きを読む():
    s = _make_searcher()
    assert s._is_actress_name("続きを読む") is False


# ============================================================
# _is_likely_compressed
# ============================================================

def test_is_likely_compressed_gzip():
    s = _make_searcher()
    assert s._is_likely_compressed(b"\x1f\x8b" + b"\x00" * 10) is True


def test_is_likely_compressed_deflate():
    s = _make_searcher()
    assert s._is_likely_compressed(b"\x78\x9c" + b"\x00" * 10) is True


def test_is_likely_compressed_plain_text():
    s = _make_searcher()
    assert s._is_likely_compressed(b"Hello World") is False


def test_is_likely_compressed_short_data():
    s = _make_searcher()
    assert s._is_likely_compressed(b"\x1f\x8b") is False


def test_is_likely_compressed_high_entropy():
    s = _make_searcher()
    high_entropy = bytes(range(128, 138))  # 10 bytes all > 127
    assert s._is_likely_compressed(high_entropy) is True


# ============================================================
# _is_valid_decoded_text
# ============================================================

def test_is_valid_decoded_text_valid_html():
    s = _make_searcher()
    text = "<html><body><div>日本語テスト</div></body></html>"
    assert s._is_valid_decoded_text(text) is True


def test_is_valid_decoded_text_too_short():
    s = _make_searcher()
    assert s._is_valid_decoded_text("短い") is False


def test_is_valid_decoded_text_empty():
    s = _make_searcher()
    assert s._is_valid_decoded_text("") is False


def test_is_valid_decoded_text_high_replacement_ratio():
    s = _make_searcher()
    # >10% replacement chars, no HTML tags → should be invalid
    normal = "AAAAAAAAAA"  # 10 chars
    replacement = "\ufffd" * 2  # 2 replacement chars → 2/12 ≈ 16.7% > 10%
    text = normal + replacement
    assert s._is_valid_decoded_text(text) is False


def test_is_valid_decoded_text_no_html_no_japanese():
    s = _make_searcher()
    text = "abcdefghijklmnopqrstuvwxyz" * 3
    assert s._is_valid_decoded_text(text) is False


# ============================================================
# _extract_avwiki_detail_url
# ============================================================

def test_extract_avwiki_detail_url_finds_readmore_link():
    s = _make_searcher()
    html = '''
    <html><body>
      <a href="https://av-wiki.net/ssis-123/" >続きを読む</a>
    </body></html>
    '''
    soup = BeautifulSoup(html, "html.parser")
    url = s._extract_avwiki_detail_url(soup, "SSIS-123")
    assert url == "https://av-wiki.net/ssis-123/"


def test_extract_avwiki_detail_url_no_match_returns_first():
    s = _make_searcher()
    html = '''
    <html><body>
      <a href="https://av-wiki.net/other-page/">続きを読む</a>
    </body></html>
    '''
    soup = BeautifulSoup(html, "html.parser")
    url = s._extract_avwiki_detail_url(soup, "STARS-999")
    assert url == "https://av-wiki.net/other-page/"


def test_extract_avwiki_detail_url_no_links():
    s = _make_searcher()
    soup = BeautifulSoup("<html><body>nothing</body></html>", "html.parser")
    assert s._extract_avwiki_detail_url(soup, "STARS-999") is None


def test_extract_avwiki_detail_url_relative_href():
    s = _make_searcher()
    html = '<a href="/ssis-123/">続きを読む</a>'
    soup = BeautifulSoup(html, "html.parser")
    url = s._extract_avwiki_detail_url(soup, "SSIS-123")
    assert url == "https://av-wiki.net/ssis-123/"


def test_fetch_avwiki_detail_studio_info_merges_detail_page_fields():
    s = _make_searcher()
    search_soup = _make_soup('<a href="/ssis-123/">続きを読む</a>')
    detail_soup = _make_soup("detail")
    calls = []

    def extract_studio_info(soup, _code):
        calls.append(soup)
        if soup is detail_soup:
            return {
                "studio": "S1",
                "studio_code": "SSIS",
                "release_date": "2026-04-24",
            }
        return {"studio": None, "studio_code": None, "release_date": None}

    s._extract_studio_info = extract_studio_info
    s.safe_searcher = SimpleNamespace(safe_request=lambda _fn, _url: detail_soup)

    result = s._fetch_avwiki_detail_studio_info(search_soup, "SSIS-123")

    assert calls == [search_soup, detail_soup]
    assert result == {
        "studio": "S1",
        "studio_code": "SSIS",
        "release_date": "2026-04-24",
    }


def test_fetch_avwiki_detail_studio_info_keeps_search_page_studio():
    s = _make_searcher()
    soup = _make_soup("<html><body>search page</body></html>")
    s._extract_studio_info = lambda _soup, _code: {
        "studio": "S1",
        "studio_code": "SSIS",
        "release_date": None,
    }
    s._extract_avwiki_detail_url = lambda *_args: (_ for _ in ()).throw(
        AssertionError("detail page should not be fetched")
    )

    result = s._fetch_avwiki_detail_studio_info(soup, "SSIS-123")

    assert result["studio"] == "S1"
    assert result["studio_code"] == "SSIS"


def test_scan_avwiki_text_for_actresses_near_code():
    s = _make_searcher()
    s._is_valid_actress_name = lambda name: name == "葵つかさ"
    soup = _make_soup(
        """
        <html><body>
        <p>葵つかさ</p>
        <p>SSIS-123</p>
        </body></html>
        """
    )

    assert s._scan_avwiki_text_for_actresses(soup, "SSIS-123") == ["葵つかさ"]


def test_finalize_avwiki_search_result_normalizes_studio():
    s = _make_searcher(
        studio_identifier=SimpleNamespace(
            normalize_studio_name=lambda studio, code: f"{studio}:{code}"
        )
    )

    result = s._finalize_avwiki_search_result(
        "SSIS-123",
        ["葵つかさ"],
        {"studio": "S1", "studio_code": "SSIS", "release_date": "2026-04-24"},
    )

    assert result == {
        "source": "AV-WIKI (安全增強版)",
        "actresses": ["葵つかさ"],
        "studio": "S1:SSIS-123",
        "studio_code": "SSIS",
        "release_date": "2026-04-24",
    }


# ============================================================
# _extract_studio_code_from_number
# ============================================================

def test_extract_studio_code_valid():
    s = _make_searcher()
    assert s._extract_studio_code_from_number("SSIS-123") == "SSIS"


def test_extract_studio_code_empty():
    s = _make_searcher()
    assert s._extract_studio_code_from_number("") is None


def test_extract_studio_code_starts_with_digit():
    s = _make_searcher()
    assert s._extract_studio_code_from_number("123ABC") is None


# ============================================================
# search_info
# ============================================================

def test_search_info_stop_event_set():
    s = _make_searcher()
    stop = threading.Event()
    stop.set()
    assert s.search_info("SSIS-123", stop) is None


def test_search_info_cache_hit():
    s = _make_searcher()
    cached = {"actresses": ["A"], "source": "AV-WIKI"}
    s.search_cache["SSIS-123"] = cached
    result = s.search_info("SSIS-123", threading.Event())
    assert result is cached


def test_search_info_avwiki_found():
    s = _make_avwiki_searcher_with_fixture("avwiki_hit.html")
    result = s.search_info("SSIS-123", threading.Event())
    assert result["actresses"] == ["葵つかさ"]
    assert result["source"] == "AV-WIKI (安全增強版)"
    assert s.search_cache["SSIS-123"]["actresses"] == ["葵つかさ"]


def test_search_info_javdb_found():
    s = _make_avwiki_searcher_with_fixture(
        "avwiki_empty.html",
        javdb_result={"actresses": ["ActressB"], "source": "JAVDB", "studio": "S1"},
    )
    result = s.search_info("SSIS-123", threading.Event())
    assert result["actresses"] == ["ActressB"]
    assert result["source"] == "JAVDB"
    assert s.search_cache["SSIS-123"]["actresses"] == ["ActressB"]


def test_search_info_not_found():
    s = _make_avwiki_searcher_with_fixture("avwiki_empty.html", javdb_result=None)
    result = s.search_info("SSIS-123", threading.Event())
    assert result is None


def test_search_info_exception_returns_none():
    s = _make_searcher()
    s._search_candidates_in_av_wiki = lambda *_: (_ for _ in ()).throw(RuntimeError("boom"))
    result = s.search_info("SSIS-123", threading.Event())
    assert result is None


# ============================================================
# _search_candidates_in_av_wiki
# ============================================================

def test_search_candidates_in_av_wiki_found():
    def conditional_fixture(url: str) -> str:
        if "SSIS-001" in url:
            return _load_fixture_html("avwiki_hit.html")
        return _load_fixture_html("avwiki_empty.html")

    s = _make_avwiki_searcher_with_fixture(
        "avwiki_empty.html", conditional_fixture=conditional_fixture
    )
    result = s._search_candidates_in_av_wiki(
        "SSIS-00001", ["SSIS-00001", "SSIS-001"], threading.Event()
    )
    assert result is not None
    assert result["matched_code"] == "SSIS-001"
    assert result["search_alias_used"] is True
    assert s.search_cache["SSIS-00001"]["matched_code"] == "SSIS-001"


def test_search_candidates_in_av_wiki_no_actresses():
    s = _make_avwiki_searcher_with_fixture("avwiki_empty.html")
    result = s._search_candidates_in_av_wiki("SSIS-123", ["SSIS-123"], threading.Event())
    assert result is None


def test_search_candidates_in_av_wiki_none_result():
    s = _make_searcher()
    s._search_av_wiki = lambda candidate, stop: None
    result = s._search_candidates_in_av_wiki("SSIS-123", ["SSIS-123"], threading.Event())
    assert result is None


# ============================================================
# _search_candidates_in_javdb
# ============================================================

def test_search_candidates_in_javdb_stop_event():
    s = _make_searcher()
    stop = threading.Event()
    stop.set()
    result = s._search_candidates_in_javdb("SSIS-123", ["SSIS-123"], stop)
    assert result is None


def test_search_candidates_in_javdb_found():
    def search_javdb(candidate):
        if candidate == "SSIS-001":
            return {"actresses": ["ActressC"], "source": "JAVDB", "studio": "S1"}
        return None

    s = _make_searcher(
        javdb_searcher=SimpleNamespace(search_javdb=search_javdb),
        studio_identifier=SimpleNamespace(
            normalize_studio_name=lambda studio, code: studio
        ),
    )
    result = s._search_candidates_in_javdb(
        "SSIS-00001", ["SSIS-00001", "SSIS-001"], threading.Event()
    )
    assert result is not None
    assert result["actresses"] == ["ActressC"]
    assert result["matched_code"] == "SSIS-001"
    assert s.search_cache["SSIS-00001"]["matched_code"] == "SSIS-001"


def test_search_candidates_in_javdb_not_found():
    s = _make_searcher()
    s.javdb_searcher = SimpleNamespace(search_javdb=lambda c: None)
    result = s._search_candidates_in_javdb("SSIS-123", ["SSIS-123"], threading.Event())
    assert result is None


# ============================================================
# search_javdb_only
# ============================================================

def test_search_javdb_only_stop_event():
    s = _make_searcher()
    stop = threading.Event()
    stop.set()
    assert s.search_javdb_only("SSIS-123", stop) is None


def test_search_javdb_only_cache_hit():
    s = _make_searcher()
    cached = {"actresses": ["A"]}
    s.search_cache["SSIS-123"] = cached
    assert s.search_javdb_only("SSIS-123", threading.Event()) is cached


def test_search_javdb_only_exception_returns_error():
    s = _make_searcher()
    s._build_code_candidates = lambda c: (_ for _ in ()).throw(RuntimeError("boom"))
    result = s.search_javdb_only("SSIS-123", threading.Event())
    assert result["search_status"] == "search_error"


# ============================================================
# search_japanese_sites (search_avwiki_only 委派)
# ============================================================

def test_search_japanese_sites_stop_event():
    s = _make_searcher()
    stop = threading.Event()
    stop.set()
    assert s.search_japanese_sites("SSIS-123", stop) is None


def test_search_japanese_sites_cache_hit():
    s = _make_searcher()
    cached = {"actresses": ["B"]}
    s.search_cache["SSIS-123"] = cached
    assert s.search_japanese_sites("SSIS-123", threading.Event()) is cached


def test_search_japanese_sites_found():
    s = _make_avwiki_searcher_with_fixture("avwiki_hit.html")
    result = s.search_japanese_sites("SSIS-123", threading.Event())
    assert result["actresses"] == ["葵つかさ"]
    assert result["studio"] == "S1 NO.1 STYLE"


def test_search_japanese_sites_search_error_propagated():
    s = _make_searcher(
        safe_searcher=SimpleNamespace(safe_request=lambda fn, url: None),
        studio_identifier=SimpleNamespace(
            normalize_studio_name=lambda studio, code: studio
        ),
    )
    result = s.search_japanese_sites("SSIS-123", threading.Event())
    assert result["search_status"] == "search_error"
    assert result["searched_code"] == "SSIS-123"


def test_search_japanese_sites_not_found():
    s = _make_avwiki_searcher_with_fixture("avwiki_empty.html")
    result = s.search_japanese_sites("SSIS-123", threading.Event())
    assert result is None


def test_search_japanese_sites_exception():
    s = _make_searcher()
    s._search_av_wiki = lambda *_: (_ for _ in ()).throw(RuntimeError("boom"))
    result = s.search_japanese_sites("SSIS-123", threading.Event())
    assert result["search_status"] == "search_error"


# ============================================================
# simple getter/clearer methods
# ============================================================

def test_get_safe_searcher_stats():
    s = _make_searcher()
    s.safe_searcher = SimpleNamespace(get_stats=lambda: {"calls": 3})
    assert s.get_safe_searcher_stats() == {"calls": 3}


def test_clear_cache():
    s = _make_searcher()
    s.search_cache["SSIS-123"] = {}
    s.safe_searcher = SimpleNamespace(clear_cache=lambda: None)
    s.clear_cache()
    assert s.search_cache == {}


def test_get_javdb_stats():
    s = _make_searcher()
    s.javdb_searcher = SimpleNamespace(get_stats=lambda: {"javdb_calls": 1})
    assert s.get_javdb_stats() == {"javdb_calls": 1}


def test_get_all_search_stats():
    s = _make_searcher()
    s.search_cache["SSIS-123"] = {}
    s.safe_searcher = SimpleNamespace(get_stats=lambda: {})
    s.javdb_searcher = SimpleNamespace(get_stats=lambda: {})
    stats = s.get_all_search_stats()
    assert stats["local_cache_entries"] == 1


def test_split_cached_avwiki_codes_preserves_input_order():
    s = _make_searcher()
    cached = {"actresses": ["A"]}
    s.search_cache["A-001"] = cached

    uncached, cached_results = s._split_cached_avwiki_codes(
        ["A-001", "B-002", "C-003"]
    )

    assert uncached == ["B-002", "C-003"]
    assert cached_results == {"A-001": cached}


def test_build_avwiki_progress_callback_deduplicates_codes():
    messages = []
    callback = WebSearcher._build_avwiki_progress_callback(messages.append, 2)

    callback(1, 2, "A-001")
    callback(1, 2, "A-001")
    callback(2, 2, "B-002")

    assert messages == ["[1/2] 搜尋 A-001\n", "[2/2] 搜尋 B-002\n"]


def test_build_avwiki_progress_callback_none():
    assert WebSearcher._build_avwiki_progress_callback(None, 2) is None


def test_cache_avwiki_batch_results_only_caches_successes():
    s = _make_searcher()

    s._cache_avwiki_batch_results(
        {
            "A-001": {"actresses": ["A"]},
            "B-002": {"actresses": []},
            "C-003": None,
        }
    )

    assert list(s.search_cache) == ["A-001"]


def test_batch_search_avwiki_concurrent_empty_codes():
    s = _make_searcher()

    assert s.batch_search_avwiki_concurrent([], threading.Event()) == {}


def test_batch_search_avwiki_concurrent_returns_cached_results_only():
    s = _make_searcher()
    s.search_cache["A-001"] = {"actresses": ["A"]}
    messages = []

    result = s.batch_search_avwiki_concurrent(
        ["A-001"], threading.Event(), progress_callback=messages.append
    )

    assert result == {"A-001": {"actresses": ["A"]}}
    assert messages == ["📦 使用快取: 1 個番號\n"]


def test_batch_search_avwiki_concurrent_success(monkeypatch):
    s = _make_searcher(avwiki_max_concurrent=3)
    messages = []

    async def fake_batch_search(codes, _stop_event, _progress_callback):
        return {
            codes[0]: {"actresses": ["A"]},
            codes[1]: {"actresses": []},
        }

    s._run_avwiki_batch_search = fake_batch_search

    result = s.batch_search_avwiki_concurrent(
        ["A-001", "B-002"], threading.Event(), progress_callback=messages.append
    )

    assert result["A-001"]["actresses"] == ["A"]
    assert result["B-002"]["actresses"] == []
    assert s.search_cache["A-001"]["actresses"] == ["A"]
    assert any("開始 AV-WIKI" in message for message in messages)
    assert any("1/2" in message for message in messages)


def test_batch_search_avwiki_concurrent_returns_cached_on_error():
    s = _make_searcher()
    cached = {"actresses": ["A"]}
    s.search_cache["A-001"] = cached

    async def fake_batch_search(*_args):
        raise RuntimeError("batch down")

    s._run_avwiki_batch_search = fake_batch_search
    messages = []

    result = s.batch_search_avwiki_concurrent(
        ["A-001", "B-002"], threading.Event(), progress_callback=messages.append
    )

    assert result == {"A-001": cached}
    assert any("批次搜尋失敗" in message for message in messages)


def test_clear_all_cache():
    s = _make_searcher()
    s.search_cache["SSIS-123"] = {}
    s.safe_searcher = SimpleNamespace(clear_cache=lambda: None)
    s.javdb_searcher = SimpleNamespace(clear_cache=lambda: None)
    s.clear_all_cache()
    assert s.search_cache == {}


def test_configure_safe_searcher():
    s = _make_searcher()
    configured = {}
    s.safe_searcher = SimpleNamespace(
        configure=lambda **kw: configured.update(kw),
        get_headers=lambda: {"User-Agent": "Test"},
    )
    s.configure_safe_searcher(min_interval=0.5)
    assert configured["min_interval"] == 0.5
    assert s.headers == {"User-Agent": "Test"}


# ============================================================
# batch_search
# ============================================================

def test_batch_search_basic():
    s = _make_searcher()
    s.batch_size = 5
    s.thread_count = 2
    s.batch_delay = 0.0

    def task(item, stop):
        return {"actresses": ["A"], "source": "test"}

    results = s.batch_search(
        ["SSIS-001", "SSIS-002"],
        task,
        threading.Event(),
    )
    assert len(results) == 2
    assert results["SSIS-001"]["actresses"] == ["A"]


def test_batch_search_stop_event_set():
    s = _make_searcher()
    stop = threading.Event()
    stop.set()

    def task(item, stop_ev):
        return {"actresses": ["A"]}

    results = s.batch_search(["SSIS-001"], task, stop)
    assert results == {}


def test_batch_search_task_raises():
    s = _make_searcher()

    def task(item, stop):
        raise RuntimeError("task boom")

    results = s.batch_search(["SSIS-001"], task, threading.Event())
    assert results["SSIS-001"] is None


def test_batch_search_with_progress_and_result_callbacks():
    s = _make_searcher()
    progress_msgs = []
    result_calls = []

    def task(item, stop):
        if item == "SSIS-001":
            return {"actresses": ["A"], "source": "test"}
        return {"actresses": [], "search_status": "search_error", "search_error_reason": "暫時異常"}

    def progress(msg):
        progress_msgs.append(msg)

    def on_result(item, result, err):
        result_calls.append((item, err))

    s.batch_search(
        ["SSIS-001", "SSIS-002"],
        task,
        threading.Event(),
        progress_callback=progress,
        result_callback=on_result,
    )

    assert any("✅" in m for m in progress_msgs)
    assert any("⚠️" in m for m in progress_msgs)


def test_batch_search_progress_for_not_found_and_batch_delay(monkeypatch):
    s = _make_searcher()
    s.batch_size = 1
    s.thread_count = 1
    s.batch_delay = 0.25
    progress_msgs = []
    sleeps = []
    monkeypatch.setattr(web_searcher_module.time, "sleep", sleeps.append)

    result = s.batch_search(
        ["A-001", "B-002"],
        lambda _item, _stop: {"actresses": []},
        threading.Event(),
        progress_callback=progress_msgs.append,
    )

    assert set(result) == {"A-001", "B-002"}
    assert any("❌" in message for message in progress_msgs)
    assert sleeps == [0.25]


def test_search_shiroutowiki_only_stop_event():
    s = _make_searcher()
    stop = threading.Event()
    stop.set()

    assert s.search_shiroutowiki_only("SSIS-123", stop) is None


def test_search_shiroutowiki_only_cache_hit():
    s = _make_searcher()
    cached = {"actresses": ["A"]}
    s.search_cache["SSIS-123"] = cached

    assert s.search_shiroutowiki_only("SSIS-123", threading.Event()) is cached


def test_search_shiroutowiki_only_returns_error_on_exception():
    s = _make_searcher()
    s._build_shiroutowiki_candidates = lambda _code: (_ for _ in ()).throw(
        RuntimeError("shirouto down")
    )

    result = s.search_shiroutowiki_only("SSIS-123", threading.Event())

    assert result["source"] == "shiroutowiki"
    assert result["search_status"] == "search_error"


# ============================================================
# _search_av_wiki
# ============================================================

def _make_soup(html: str):
    return BeautifulSoup(html, "html.parser")


def _make_avwiki_searcher_with_fixture(
    fixture_name: str,
    *,
    javdb_result=None,
    conditional_fixture=None,
) -> WebSearcher:
    def safe_request(_fn, url):
        if conditional_fixture is not None:
            return _make_soup(conditional_fixture(url))
        return _make_soup(_load_fixture_html(fixture_name))

    return _make_searcher(
        safe_searcher=SimpleNamespace(safe_request=safe_request),
        javdb_searcher=SimpleNamespace(search_javdb=lambda code: javdb_result),
        studio_identifier=SimpleNamespace(
            normalize_studio_name=lambda studio, code: studio
        ),
    )


def test_search_av_wiki_stop_event_set():
    s = _make_searcher()
    stop = threading.Event()
    stop.set()
    result = s._search_av_wiki("SSIS-123", stop)
    assert result is None


def test_search_av_wiki_safe_request_returns_none():
    s = _make_searcher()
    s.japanese_headers = {}
    s.timeout = 5
    s.safe_searcher = SimpleNamespace(safe_request=lambda fn, url: None)
    result = s._search_av_wiki("SSIS-123", threading.Event())
    assert result is not None
    assert result["search_status"] == "search_error"


def test_search_av_wiki_no_actresses_found():
    s = _make_searcher()
    s.japanese_headers = {}
    s.timeout = 5
    soup = _make_soup("<html><body><p>No results here</p></body></html>")
    s.safe_searcher = SimpleNamespace(safe_request=lambda fn, url: soup)
    s._extract_studio_info = lambda soup, code: {}
    s._extract_avwiki_detail_url = lambda soup, code: None
    result = s._search_av_wiki("SSIS-123", threading.Event())
    assert result is None


def test_search_av_wiki_actresses_found():
    s = _make_searcher()
    s.japanese_headers = {}
    s.timeout = 5
    html = """
    <html><body>
      <a rel="tag" href="https://av-wiki.net/av-actress/suzuki-ai/">鈴木あい</a>
    </body></html>
    """
    soup = _make_soup(html)
    s.safe_searcher = SimpleNamespace(safe_request=lambda fn, url: soup)
    s._extract_studio_info = lambda soup, code: {"studio": "S1", "studio_code": "s1"}
    s.studio_identifier = SimpleNamespace(normalize_studio_name=lambda s, c: s)
    result = s._search_av_wiki("SSIS-123", threading.Event())
    assert result is not None
    assert "鈴木あい" in result["actresses"]


def test_extract_avwiki_actresses_uses_actress_name_links_when_tag_links_missing():
    s = _make_searcher()
    soup = _make_soup(
        """
        <html><body>
          <div class="actress-name">
            <a href="https://av-wiki.net/av-actress/tanaka-minami/">田中みな実</a>
          </div>
        </body></html>
        """
    )

    assert s._extract_avwiki_actresses(soup) == ["田中みな実"]


def test_extract_avwiki_actresses_merges_tag_and_actress_name_links():
    s = _make_searcher()
    soup = _make_soup(
        """
        <html><body>
          <a rel="tag" href="https://av-wiki.net/av-actress/suzuki-ai/">鈴木あい</a>
          <div class="actress-name">
            <a href="https://av-wiki.net/av-actress/tanaka-minami/">田中みな実</a>
          </div>
        </body></html>
        """
    )

    assert s._extract_avwiki_actresses(soup) == ["鈴木あい", "田中みな実"]


def test_search_av_wiki_does_not_use_text_scan_when_structured_links_missing():
    s = _make_searcher()
    s.japanese_headers = {}
    s.timeout = 5
    soup = _make_soup(
        """
        <html><body>
          <div class="column-flex">SSIS-123 可愛い メイド 交わる体液</div>
        </body></html>
        """
    )
    s.safe_searcher = SimpleNamespace(safe_request=lambda fn, url: soup)
    s._extract_studio_info = lambda soup, code: {}
    s._extract_avwiki_detail_url = lambda soup, code: None

    scan_called = False

    def _unexpected_text_scan(_soup, _code):
        nonlocal scan_called
        scan_called = True
        return ["可愛い"]

    s._scan_avwiki_text_for_actresses = _unexpected_text_scan

    result = s._search_av_wiki("SSIS-123", threading.Event())

    assert result is None
    assert scan_called is False


def test_search_av_wiki_exception_returns_error():
    s = _make_searcher()
    s.japanese_headers = {}
    s.timeout = 5

    def _raise(fn, url):
        raise RuntimeError("network error")

    s.safe_searcher = SimpleNamespace(safe_request=_raise)
    result = s._search_av_wiki("SSIS-123", threading.Event())
    assert result is not None
    assert result["search_status"] == "search_error"


def test_search_av_wiki_too_many_actresses():
    s = _make_searcher()
    s.japanese_headers = {}
    s.timeout = 5
    tags = "".join(
        f'<a rel="tag" href="https://av-wiki.net/av-actress/a{i}/">女優{i}</a>'
        for i in range(11)
    )
    html = f"<html><body>{tags}</body></html>"
    soup = _make_soup(html)
    s.safe_searcher = SimpleNamespace(safe_request=lambda fn, url: soup)
    s._extract_studio_info = lambda soup, code: {}
    s._extract_avwiki_detail_url = lambda soup, code: None
    result = s._search_av_wiki("SSIS-123", threading.Event())
    assert result is None


# ============================================================
# _detect_and_decode_content / _handle_compression / _force_decompress
# ============================================================

def _make_response(content: bytes, encoding: str = None, headers: dict = None):
    """建立簡易 fake httpx.Response。"""
    return SimpleNamespace(
        content=content,
        encoding=encoding,
        headers=SimpleNamespace(get=lambda k, default="": (headers or {}).get(k, default)),
    )


def test_detect_and_decode_utf8(tmp_path):
    s = _make_searcher()
    s._handle_compression = lambda resp, b: b
    s._is_likely_compressed = lambda b: False
    text = "<html><body>Hello</body></html>"
    resp = _make_response(text.encode("utf-8"))
    result = s._detect_and_decode_content(resp)
    assert "Hello" in result


def test_detect_and_decode_fallback_replace(tmp_path):
    s = _make_searcher()
    s._handle_compression = lambda resp, b: b
    s._is_likely_compressed = lambda b: False
    # Use bytes that fail all common encodings (just latin-1 high bytes)
    # Override encoding_attempts by making everything fail
    original = s._is_valid_decoded_text
    s._is_valid_decoded_text = lambda t: False
    resp = _make_response(b"<html>\xff\xfe</html>")
    result = s._detect_and_decode_content(resp)
    s._is_valid_decoded_text = original
    # fallback should return some string
    assert isinstance(result, str)


def test_handle_compression_gzip():
    s = _make_searcher()
    import gzip as _gzip
    original = b"Hello compressed"
    compressed = _gzip.compress(original)
    resp = _make_response(compressed, headers={"content-encoding": "gzip"})
    result = s._handle_compression(resp, compressed)
    assert result == original


def test_handle_compression_deflate():
    s = _make_searcher()
    import zlib
    original = b"Hello deflated"
    compressed = zlib.compress(original)
    resp = _make_response(compressed, headers={"content-encoding": "deflate"})
    result = s._handle_compression(resp, compressed)
    assert result == original


def test_handle_compression_no_encoding():
    s = _make_searcher()
    data = b"plain bytes"
    resp = _make_response(data)
    result = s._handle_compression(resp, data)
    assert result == data


def test_handle_compression_exception():
    s = _make_searcher()
    bad_data = b"not compressed"
    resp = _make_response(bad_data, headers={"content-encoding": "gzip"})
    # Should not raise; returns original bytes
    result = s._handle_compression(resp, bad_data)
    assert isinstance(result, bytes)


def test_force_decompress_gzip():
    s = _make_searcher()
    import gzip as _gzip
    original = b"Hello"
    compressed = _gzip.compress(original)
    result = s._force_decompress(compressed)
    assert result == original


def test_force_decompress_all_fail():
    s = _make_searcher()
    bad_data = b"definitely not compressed data"
    result = s._force_decompress(bad_data)
    assert isinstance(result, bytes)


def test_extract_studio_info_from_icon_link_with_code_and_date():
    s = _make_searcher()
    soup = _make_soup(
        """
        <html><body>
          <li><i class="fa-clone"></i><a>S1 NO.1 STYLE - SSIS</a></li>
          <p>發售日: 2026-04-24</p>
        </body></html>
        """
    )

    result = s._extract_studio_info(soup, "SSIS-123")

    assert result == {
        "studio": "S1 NO.1 STYLE",
        "studio_code": "SSIS",
        "release_date": "2026-04-24",
    }


def test_extract_studio_info_from_text_pattern_and_dot_date():
    s = _make_searcher()
    soup = _make_soup("<html><body>メーカー: MOODYZ<br>2026.04.24</body></html>")

    result = s._extract_studio_info(soup, "MIDV-123")

    assert result["studio"] == "MOODYZ"
    assert result["studio_code"] == "MOODYZ"
    assert result["release_date"] == "2026.04.24"


def test_extract_studio_info_falls_back_to_code_mapping():
    s = _make_searcher(_studio_code_mapping={"SSIS": "S1"})
    soup = _make_soup("<html><body>2026-04-24</body></html>")

    result = s._extract_studio_info(soup, "SSIS-123")

    assert result["studio"] == "S1"
    assert result["studio_code"] == "SSIS"
    assert result["release_date"] == "2026-04-24"


def test_get_studio_name_by_code_falls_back_to_code():
    s = _make_searcher(_studio_code_mapping={"SSIS": "S1"})

    assert s._get_studio_name_by_code("ssis") == "S1"
    assert s._get_studio_name_by_code("ABCD") == "ABCD"


def test_cascade_search_single_cache_hit():
    s = _make_searcher()
    s.search_cache["SSIS-123"] = {"actresses": ["A"], "source": "AV-WIKI"}

    result = s.cascade_search_single("SSIS-123", threading.Event())

    assert result["tried_sources"] == ["cache"]
    assert result["final_source"] == "cache"


def test_cascade_search_single_success_caches_result():
    s = _make_searcher()
    s._search_av_wiki = lambda _code, _stop: {
        "actresses": ["A"],
        "source": "AV-WIKI",
    }

    result = s.cascade_search_single("SSIS-123", threading.Event())

    assert result["tried_sources"] == ["avwiki"]
    assert result["final_source"] == "avwiki"
    assert s.search_cache["SSIS-123"]["actresses"] == ["A"]


def test_cascade_search_single_returns_not_found_after_exception():
    s = _make_searcher()
    s._search_av_wiki = lambda *_args: (_ for _ in ()).throw(RuntimeError("boom"))

    result = s.cascade_search_single("SSIS-123", threading.Event())

    assert result["status"] == "not_found"
    assert result["tried_sources"] == ["avwiki"]


def test_cascade_search_single_stops_before_source():
    s = _make_searcher()
    stop = threading.Event()
    stop.set()

    result = s.cascade_search_single("SSIS-123", stop)

    assert result["status"] == "not_found"
    assert result["tried_sources"] == []
