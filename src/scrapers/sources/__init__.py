"""
專用資料源爬蟲模組
"""

from .avwiki_scraper import AVWikiScraper
from .javdb_scraper import JAVDBScraper
from .shiroutowiki_scraper import ShiroutoWikiScraper

__all__ = ["JAVDBScraper", "AVWikiScraper", "ShiroutoWikiScraper"]
