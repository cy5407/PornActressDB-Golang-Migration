#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
診斷 AVOP-004 的特殊情況
"""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
os.chdir(Path(__file__).parent)

try:
    from scrapers.sources.avwiki_scraper import AVWikiScraper
except ImportError:
    import importlib.util
    spec = importlib.util.spec_from_file_location("avwiki_scraper", 
        Path(__file__).parent / "src" / "scrapers" / "sources" / "avwiki_scraper.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    AVWikiScraper = module.AVWikiScraper

async def diagnose_avop004():
    """診斷 AVOP-004"""
    scraper = AVWikiScraper()
    
    code = 'AVOP-004'
    print(f"診斷 {code}...")
    print("=" * 60)
    
    try:
        result = await scraper.search_video(code)
        
        print(f"結果: {result}")
        print()
        print(f"女優: {result.get('actresses', [])}")
        print(f"標題: {result.get('title', 'N/A')}")
        print(f"片商: {result.get('studio', 'N/A')}")
        
    except Exception as e:
        print(f"錯誤: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(diagnose_avop004())
