"""
專用資料源爬蟲模組
"""

from .avwiki_scraper import AVWikiScraper
from .javdb_scraper import JAVDBScraper

__all__ = ["JAVDBScraper", "AVWikiScraper"]
