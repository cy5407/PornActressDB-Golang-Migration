import asyncio

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
