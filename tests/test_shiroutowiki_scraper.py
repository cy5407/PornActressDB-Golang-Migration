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
