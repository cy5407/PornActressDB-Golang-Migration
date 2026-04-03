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
