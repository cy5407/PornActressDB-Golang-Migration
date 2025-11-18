#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整測試所有日誌中失敗的番號
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

# 日誌中所有失敗的番號（共 50 個）
BATCH_TEST_CODES = [
    'STARS-767', 'JUQ-863', 'UMD-844', 'ABP-601', 'ABP-863',
    'MKMP-487', 'DLDSS-332', 'MIDV-764', 'IPZZ-266', 'BABD-018',
    'SONE-209', 'ORECO-939', 'ABF-152', 'EBWH-227', 'STAR-573',
    'PPPE-078', 'SNIS-493', 'HMN-635', 'START-205', 'ABP-793',
    'SONE-730', 'MVSD-492', 'SSIS-841', 'SSIS-845', 'MIDE-840',
    'STARS-866', 'SSIS-808', 'MIDV-574', 'SSIS-895', 'GNI-005',
    'SONE-159', 'FSDSS-930', 'SSIS-563', 'SONE-025', 'SNIS-985',
    'MIUM-211', 'SONE-747', 'SNIS-640', 'SNIS-731', 'SSIS-400',
    'IPZZ-365', 'PPPE-043', 'MIDV-204', 'MIDV-866', 'STARS-924',
    'MIDV-633', 'FSDSS-198', 'ABP-582', 'SSIS-610',
]

async def test_all_failed():
    """測試所有失敗的番號"""
    scraper = AVWikiScraper()
    
    print("=" * 70)
    print(f"完整批次搜尋測試 ({len(BATCH_TEST_CODES)} 個番號)")
    print("=" * 70)
    print()
    
    # 執行批次搜尋
    results = await scraper.search_batch_concurrent(
        BATCH_TEST_CODES,
        max_concurrent=15,  # 使用原始的 15 併發
    )
    
    print()
    print("=" * 70)
    print("結果統計")
    print("=" * 70)
    
    success_count = 0
    failure_count = 0
    failed_codes = []
    
    for code in BATCH_TEST_CODES:
        if code in results:
            result = results[code]
            actresses = result.get('actresses', [])
            
            if actresses:
                success_count += 1
            else:
                failure_count += 1
                failed_codes.append(code)
        else:
            failure_count += 1
            failed_codes.append(code)
    
    print(f"成功: {success_count}/{len(BATCH_TEST_CODES)} ({success_count/len(BATCH_TEST_CODES)*100:.1f}%)")
    print(f"失敗: {failure_count}/{len(BATCH_TEST_CODES)} ({failure_count/len(BATCH_TEST_CODES)*100:.1f}%)")
    
    if failed_codes:
        print()
        print("失敗的番號:")
        for code in failed_codes:
            print(f"  ✗ {code}")

if __name__ == "__main__":
    asyncio.run(test_all_failed())
