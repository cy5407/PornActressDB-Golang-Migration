from bs4 import BeautifulSoup

from src.scrapers.sources.javdb_scraper import JAVDBScraper


def test_extract_detail_panel_data_parses_known_fields():
    scraper = JAVDBScraper()
    soup = BeautifulSoup(
        """
        <html>
          <body>
            <div class="panel-block">
              <strong>演員</strong>
              <a href="/actors/1">三上悠亜</a>
              <a href="/actors/2">橋本ありな</a>
            </div>
            <div class="panel-block">
              <strong>片商</strong>
              <a href="/makers/1">MOODYZ</a>
            </div>
            <div class="panel-block">
              <strong>發行日期</strong>
              2024-01-02
            </div>
            <div class="panel-block">
              <strong>時長</strong>
              120 分鐘
            </div>
            <div class="panel-block">
              <strong>導演</strong>
              <a href="/directors/1">導演甲</a>
            </div>
            <div class="panel-block">
              <strong>系列</strong>
              <a href="/series/1">系列甲</a>
            </div>
            <div class="panel-block">
              <strong>類別</strong>
              <a href="/genres/1">劇情</a>
              <a href="/genres/2">單體作品</a>
            </div>
          </body>
        </html>
        """,
        "html.parser",
    )

    detail = scraper._extract_detail_panel_data(soup.find_all("div", class_="panel-block"))

    assert detail == {
        "actresses": ["三上悠亜", "橋本ありな"],
        "studio": "MOODYZ",
        "release_date": "2024-01-02",
        "duration": "120分鐘",
        "director": "導演甲",
        "series": "系列甲",
        "categories": ["劇情", "單體作品"],
    }
