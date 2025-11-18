#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
測試多個之前失敗的番號
"""

import asyncio
from src.scrapers.sources.avwiki_scraper import AVWikiScraper

async def test_failed_codes():
    """測試之前失敗的番號"""
    
    scraper = AVWikiScraper()
    
    # 測試一些之前失敗的番號
    test_codes = [
        'SSIS-815',   # 失敗
        'MIDV-777',   # 失敗
        'MIDV-222',   # 失敗
        'SKMJ-581',   # 成功
        'SNIS-539',   # 失敗
        'SONE-033',   # 失敗
    ]
    
    print("[*] 測試先前失敗的番號")
    print("=" * 70)
    print()
    
    for code in test_codes:
        try:
            result = await scraper.search_video(code)
            actresses = result.get('actresses', [])
            
            status = "[OK]" if actresses else "[WARN]"
            print(f"{status} {code}: {len(actresses)} 位女優", end="")
            
            if actresses:
                print(f" - {', '.join(actresses[:3])}", end="")
                if len(actresses) > 3:
                    print(f", ... (+{len(actresses) - 3})", end="")
            
            print()
            
        except Exception as e:
            print(f"[FAIL] {code}: {str(e)[:50]}")

if __name__ == '__main__':
    asyncio.run(test_failed_codes())
