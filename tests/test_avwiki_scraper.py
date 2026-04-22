import asyncio

from bs4 import BeautifulSoup

from src.scrapers.sources.avwiki_scraper import AVWikiScraper


def test_batch_search_concurrent_respects_max_concurrency():
    async def run_test():
        scraper = AVWikiScraper()
        in_flight = 0
        max_in_flight = 0

        async def fake_scrape_url(_url: str):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return {
                "found": True,
                "unique_actresses": ["範例女優"],
            }

        scraper.scrape_url = fake_scrape_url
        codes = [f"TEST-{index:03d}" for index in range(5)]

        await scraper.batch_search_concurrent(codes, max_concurrent=2)

        return max_in_flight

    observed = asyncio.run(run_test())

    assert observed <= 2


def test_extract_search_result_actress_elements_uses_tag_links_first():
    scraper = AVWikiScraper()
    soup = BeautifulSoup(
        """
        <html>
          <body>
            <a rel="tag" href="https://av-wiki.net/av-actress/sample-a/">女優甲</a>
            <a rel="tag" href="https://av-wiki.net/av-actress/sample-b/">女優乙</a>
            <div class="actress-name">不應進入備援</div>
          </body>
        </html>
        """,
        "html.parser",
    )

    actress_elements = scraper._extract_search_result_actress_elements(soup)

    assert actress_elements == [
        {
            "name": "女優甲",
            "href": "https://av-wiki.net/av-actress/sample-a/",
            "source": "tag_link",
        },
        {
            "name": "女優乙",
            "href": "https://av-wiki.net/av-actress/sample-b/",
            "source": "tag_link",
        },
    ]


def test_extract_search_result_actress_elements_only_uses_text_fallback_when_no_links_exist():
    scraper = AVWikiScraper()
    scraper._is_valid_actress_name = lambda _name: True
    soup = BeautifulSoup(
        """
        <html>
          <body>
            <div class="actress-name">
              <a href="https://av-wiki.net/av-actress/sample-a/">女優甲</a>
            </div>
            <div class="actress-name">不應混入的純文字女優</div>
          </body>
        </html>
        """,
        "html.parser",
    )

    actress_elements = scraper._extract_search_result_actress_elements(soup)

    assert actress_elements == [
        {
            "name": "女優甲",
            "href": "https://av-wiki.net/av-actress/sample-a/",
            "source": "actress-name-link",
        }
    ]


def test_extract_search_result_actress_elements_ignores_plain_text_without_structured_links():
    scraper = AVWikiScraper()
    scraper._is_valid_actress_name = lambda _name: True
    soup = BeautifulSoup(
        """
        <html>
          <body>
            <div class="actress-name">不應混入的純文字女優</div>
          </body>
        </html>
        """,
        "html.parser",
    )

    actress_elements = scraper._extract_search_result_actress_elements(soup)

    assert actress_elements == []


def test_extract_detail_actresses_ignores_text_fallback_without_structured_links():
    scraper = AVWikiScraper()
    scraper._is_valid_actress_name = lambda _name: True
    scraper._extract_actresses_from_text = lambda _text: ["可愛い"]
    soup = BeautifulSoup(
        """
        <html>
          <body>
            <div class="actress-name">可愛い</div>
            <p>SSIS-123 可愛い メイド 交わる体液</p>
          </body>
        </html>
        """,
        "html.parser",
    )

    assert scraper._extract_detail_actresses(soup, soup.get_text()) == []


def test_build_batch_search_result_sets_status_for_multiple_actresses():
    scraper = AVWikiScraper()

    result = scraper._build_batch_search_result(
        code="TEST-001",
        search_url="https://av-wiki.net/?s=TEST-001&post_type=product",
        raw_result={
            "found": True,
            "unique_actresses": ["女優甲", "女優乙", "女優甲", "女優丙", "女優丁"],
        },
    )

    assert result == {
        "video_code": "TEST-001",
        "actresses": ["女優甲", "女優乙", "女優丙", "女優丁"],
        "source": "AV-WIKI",
        "search_url": "https://av-wiki.net/?s=TEST-001&post_type=product",
        "search_status": "searched_multiple",
        "actress_count": 4,
    }
