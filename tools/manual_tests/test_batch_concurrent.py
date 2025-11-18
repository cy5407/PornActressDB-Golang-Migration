#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接測試 AVWikiScraper.search_batch_concurrent 方法
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

# 之前失敗的番號
BATCH_TEST_CODES = [
    'STARS-767', 'JUQ-863', 'UMD-844', 'ABP-601', 'ABP-863',
    'MKMP-487', 'DLDSS-332', 'MIDV-764', 'IPZZ-266', 'BABD-018',
    'SONE-209', 'ORECO-939', 'ABF-152', 'EBWH-227', 'STAR-573',
]

async def test_batch_concurrent():
    """測試批次併發搜尋"""
    scraper = AVWikiScraper()
    
    print("=" * 70)
    print("AVWikiScraper.search_batch_concurrent 測試")
    print("=" * 70)
    print()
    
    # 進度回調
    def progress_cb(current, total, code):
        print(f"[{current:2d}/{total}] {code}")
    
    # 執行批次搜尋
    results = await scraper.search_batch_concurrent(
        BATCH_TEST_CODES,
        max_concurrent=5,
        progress_callback=progress_cb
    )
    
    print()
    print("=" * 70)
    print("結果統計")
    print("=" * 70)
    
    success_count = 0
    failure_count = 0
    
    for code in BATCH_TEST_CODES:
        if code in results:
            result = results[code]
            actresses = result.get('actresses', [])
            
            if actresses:
                print(f"✓ {code:12s}: {len(actresses)} 位")
                success_count += 1
            else:
                print(f"✗ {code:12s}: 無女優資訊")
                failure_count += 1
        else:
            print(f"✗ {code:12s}: 未執行")
            failure_count += 1
    
    print()
    print("=" * 70)
    print(f"成功: {success_count}/{len(BATCH_TEST_CODES)} ({success_count/len(BATCH_TEST_CODES)*100:.1f}%)")
    print(f"失敗: {failure_count}/{len(BATCH_TEST_CODES)} ({failure_count/len(BATCH_TEST_CODES)*100:.1f}%)")

if __name__ == "__main__":
    asyncio.run(test_batch_concurrent())
