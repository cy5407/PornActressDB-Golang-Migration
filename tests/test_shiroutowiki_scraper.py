import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bs4 import BeautifulSoup

from src.scrapers.sources.shiroutowiki_scraper import ShiroutoWikiScraper


SEARCH_HTML = """
<html>
  <body>
    <table>
      <tbody>
        <tr>
          <td><a href="/fanza-video/midv00567/"><img src="cover.jpg" /></a></td>
          <td><a href="https://example.com/fanza">作品標題</a></td>
          <td><a href="/actress/sample/">三崎なな</a></td>
          <td>midv00567</td>
          <td>MOODYZ</td>
          <td>系列</td>
          <td>2026/04/04</td>
        </tr>
      </tbody>
    </table>
  </body>
</html>
"""


DETAIL_HTML = """
<html>
  <body>
    <h1>〖midv00567〗作品標題</h1>
    <dl>
      <dt>女優名</dt>
      <dd><a href="/actress/sample/">三崎なな</a></dd>
      <dt>タイトル</dt>
      <dd><a href="https://example.com/fanza">作品標題</a></dd>
      <dt>商品品番</dt>
      <dd>MIDV-567</dd>
      <dt>配信品番</dt>
      <dd>midv00567</dd>
    </dl>
  </body>
</html>
"""


DETAIL_HTML_H1_ONLY = """
<html>
  <body>
    <h1>從 H1 取得的標題</h1>
    <dl>
      <dt>女優名</dt>
      <dd>三崎なな、吉岡美穂</dd>
      <dt>商品品番</dt>
      <dd>MIDV-567</dd>
      <dt>配信品番</dt>
      <dd>midv00567</dd>
    </dl>
  </body>
</html>
"""


DETAIL_HTML_MISSING_DD = """
<html>
  <body>
    <dl>
      <dt>正常欄位</dt>
      <dd>值</dd>
      <dt>另一個欄位</dt>
      <dd>另一個值</dd>
      <dt>孤立欄位</dt>
    </dl>
  </body>
</html>
"""


class DummySafeSearcher:
    def safe_request(self, fn, url, headers=None):
        return fn(url, headers)


class FailingSafeSearcher:
    def safe_request(self, fn, url, headers=None):
        raise RuntimeError("mock error")


def test_build_search_candidates_for_shiroutowiki():
    assert ShiroutoWikiScraper.build_search_candidates("SNOS-045") == [
        "SNOS-045",
        "SNOS045",
        "snos00045",
    ]
    assert ShiroutoWikiScraper.build_search_candidates("MIDV-00567") == [
        "MIDV-00567",
        "MIDV00567",
        "midv00567",
    ]
    assert ShiroutoWikiScraper.build_search_candidates("MBDD-2094") == [
        "MBDD-2094",
        "MBDD2094",
    ]
    assert ShiroutoWikiScraper.build_search_candidates("   ") == []


def test_derive_delivery_code_handles_supported_and_unsupported_lengths():
    assert ShiroutoWikiScraper._derive_delivery_code("SNOS-045") == "snos00045"
    assert ShiroutoWikiScraper._derive_delivery_code("MIDV-00567") == "midv00567"
    assert ShiroutoWikiScraper._derive_delivery_code("ABCD-1234") is None
    assert ShiroutoWikiScraper._derive_delivery_code("ABC-12") is None


def test_parse_search_rows_extracts_detail_url_actress_and_code():
    scraper = ShiroutoWikiScraper.__new__(ShiroutoWikiScraper)
    scraper.BASE_URL = "https://shiroutowiki.work"

    rows = scraper._parse_search_rows(BeautifulSoup(SEARCH_HTML, "html.parser"))

    assert len(rows) == 1
    assert rows[0]["detail_url"] == "https://shiroutowiki.work/fanza-video/midv00567/"
    assert rows[0]["actresses"] == ["三崎なな"]
    assert rows[0]["row_code"] == "midv00567"
    assert rows[0]["title"] == "作品標題"


def test_parse_detail_page_extracts_actress_and_codes():
    scraper = ShiroutoWikiScraper.__new__(ShiroutoWikiScraper)

    detail = scraper._parse_detail_page(
        BeautifulSoup(DETAIL_HTML, "html.parser"),
        "https://shiroutowiki.work/fanza-video/midv00567/",
    )

    assert detail["actresses"] == ["三崎なな"]
    assert detail["product_code"] == "MIDV-567"
    assert detail["delivery_code"] == "midv00567"
    assert detail["title"] == "作品標題"


def test_parse_detail_page_falls_back_to_plain_text_actress_and_h1_title():
    scraper = ShiroutoWikiScraper.__new__(ShiroutoWikiScraper)

    detail = scraper._parse_detail_page(
        BeautifulSoup(DETAIL_HTML_H1_ONLY, "html.parser"),
        "https://shiroutowiki.work/fanza-video/midv00567/",
    )

    assert detail["actresses"] == ["三崎なな、吉岡美穂"]
    assert detail["title"] == "從 H1 取得的標題"
    assert detail["product_code"] == "MIDV-567"
    assert detail["delivery_code"] == "midv00567"


def test_normalize_detail_map_skips_dt_without_dd():
    fields = ShiroutoWikiScraper._normalize_detail_map(
        BeautifulSoup(DETAIL_HTML_MISSING_DD, "html.parser")
    )

    assert fields == {
        "正常欄位": "值",
        "另一個欄位": "另一個值",
    }


def test_find_matching_row_result_returns_compact_code_match():
    scraper = ShiroutoWikiScraper.__new__(ShiroutoWikiScraper)

    result = scraper._find_matching_row_result(
        rows=[
            {
                "detail_url": None,
                "title": "作品標題",
                "row_code": "midv00567",
                "actresses": ["三崎なな"],
            }
        ],
        allowed_compact_codes={"midv00567"},
        search_url="https://shiroutowiki.work/?s=MIDV-00567",
        candidate="MIDV-00567",
    )

    assert result == {
        "source": "shiroutowiki",
        "actresses": ["三崎なな"],
        "title": "作品標題",
        "search_url": "https://shiroutowiki.work/?s=MIDV-00567",
        "matched_code": "midv00567",
        "delivery_code": "midv00567",
        "product_code": None,
    }


def test_search_video_keeps_per_row_priority_between_detail_and_row_code():
    scraper = ShiroutoWikiScraper.__new__(ShiroutoWikiScraper)
    scraper.BASE_URL = "https://shiroutowiki.work"
    scraper.build_search_candidates = lambda _code: ["MIDV-00567"]
    scraper._build_allowed_compact_codes = lambda _code, _candidates: {"midv00567"}
    scraper._build_direct_detail_url = lambda _candidate: None
    scraper._fetch_soup = lambda _url: object()
    scraper._parse_search_rows = lambda _soup: [
        {
            "detail_url": "https://shiroutowiki.work/fanza-video/row-1/",
            "title": "row 1 title",
            "row_code": "midv00567",
            "actresses": ["列資料女優"],
        },
        {
            "detail_url": "https://shiroutowiki.work/fanza-video/row-2/",
            "title": "row 2 title",
            "row_code": "other-code",
            "actresses": ["第二列女優"],
        },
    ]

    detail_map = {
        "https://shiroutowiki.work/fanza-video/row-1/": {
            "actresses": ["明細未命中"],
            "title": "detail 1 title",
            "product_code": "OTHER-001",
            "delivery_code": "other001",
            "search_url": "https://shiroutowiki.work/fanza-video/row-1/",
        },
        "https://shiroutowiki.work/fanza-video/row-2/": {
            "actresses": ["第二列明細命中"],
            "title": "detail 2 title",
            "product_code": "MIDV-00567",
            "delivery_code": "midv00567",
            "search_url": "https://shiroutowiki.work/fanza-video/row-2/",
        },
    }
    scraper._parse_detail_page = lambda _soup, detail_url: detail_map[detail_url]

    result = scraper.search_video("MIDV-00567")

    assert result == {
        "source": "shiroutowiki",
        "actresses": ["列資料女優"],
        "title": "row 1 title",
        "search_url": "https://shiroutowiki.work/fanza-video/row-1/",
        "matched_code": "midv00567",
        "delivery_code": "midv00567",
        "product_code": None,
    }


def test_build_direct_detail_url_accepts_only_delivery_code_format():
    scraper = ShiroutoWikiScraper.__new__(ShiroutoWikiScraper)
    scraper.BASE_URL = "https://shiroutowiki.work"

    assert (
        scraper._build_direct_detail_url("midv00567")
        == "https://shiroutowiki.work/fanza-video/midv00567/"
    )
    assert scraper._build_direct_detail_url("MIDV00567") is None
    assert scraper._build_direct_detail_url("midv567") is None


def test_fetch_soup_returns_none_when_safe_searcher_raises():
    scraper = ShiroutoWikiScraper(
        safe_searcher=FailingSafeSearcher(),
        headers={"User-Agent": "pytest"},
        timeout=5,
    )

    assert scraper._fetch_soup("https://example.com") is None


def test_fetch_soup_parses_html_via_safe_searcher(monkeypatch):
    scraper = ShiroutoWikiScraper(
        safe_searcher=DummySafeSearcher(),
        headers={"User-Agent": "pytest"},
        timeout=5,
    )

    class DummyResponse:
        text = "<html><body><h1>測試頁</h1></body></html>"

        @staticmethod
        def raise_for_status():
            return None

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, target_url, headers=None):
            return DummyResponse()

    monkeypatch.setattr("src.scrapers.sources.shiroutowiki_scraper.httpx.Client", DummyClient)

    soup = scraper._fetch_soup("https://example.com")

    assert soup is not None
    assert soup.find("h1").get_text(strip=True) == "測試頁"


def test_search_video_uses_direct_detail_url_when_search_results_do_not_match():
    scraper = ShiroutoWikiScraper.__new__(ShiroutoWikiScraper)
    scraper.BASE_URL = "https://shiroutowiki.work"
    scraper.build_search_candidates = lambda _code: ["midv00567"]
    scraper._build_allowed_compact_codes = lambda _code, _candidates: {"midv00567"}
    scraper._parse_search_rows = lambda _soup: []

    def fake_fetch_soup(url):
        if "?s=" in url:
            return BeautifulSoup("<html><body></body></html>", "html.parser")
        return BeautifulSoup(DETAIL_HTML, "html.parser")

    scraper._fetch_soup = fake_fetch_soup

    result = scraper.search_video("MIDV-00567")

    assert result == {
        "source": "shiroutowiki",
        "actresses": ["三崎なな"],
        "title": "作品標題",
        "search_url": "https://shiroutowiki.work/fanza-video/midv00567/",
        "matched_code": "MIDV-567",
        "delivery_code": "midv00567",
        "product_code": "MIDV-567",
    }
