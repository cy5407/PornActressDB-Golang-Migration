# -*- coding: utf-8 -*-
"""
專用資料源爬蟲模組
"""

from .javdb_scraper import JAVDBScraper
from .avwiki_scraper import AVWikiScraper  
from .chibaf_scraper import ChibaFScraper

__all__ = [
    'JAVDBScraper',
    'AVWikiScraper', 
    'ChibaFScraper'
]