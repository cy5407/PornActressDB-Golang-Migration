# -*- coding: utf-8 -*-
"""
簡單測試新失敗的番號
"""

import sys
from pathlib import Path
import asyncio

src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))

async def test():
    from src.scrapers.sources.avwiki_scraper import AVWikiScraper
    scraper = AVWikiScraper()
    
    codes = ['FSDSS-180', 'SNIS-515', 'STARS-814', 'SONE-709', 'EBWH-118']
    
    for code in codes:
        result = await scraper.search_video(code)
        actresses = result.get('actresses', [])
        status = 'OK' if actresses else 'WARN'
        count = len(actresses)
        print(f"[{status}] {code}: {count} 位女優")

asyncio.run(test())
