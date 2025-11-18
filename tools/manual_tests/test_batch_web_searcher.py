#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
測試批次搜尋修復 - 使用 web_searcher
"""

import asyncio
import sys
import os
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
os.chdir(Path(__file__).parent)

try:
    from services.web_searcher import WebSearcher
except ImportError:
    import importlib.util
    spec = importlib.util.spec_from_file_location("web_searcher", 
        Path(__file__).parent / "src" / "services" / "web_searcher.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    WebSearcher = module.WebSearcher

# 之前失敗的番號
BATCH_TEST_CODES = [
    'STARS-767', 'JUQ-863', 'UMD-844', 'ABP-601', 'ABP-863',
    'MKMP-487', 'DLDSS-332', 'MIDV-764', 'IPZZ-266', 'BABD-018',
]

def test_batch_search_avwiki():
    """測試 web_searcher 的批次搜尋"""
    searcher = WebSearcher()
    stop_event = threading.Event()
    
    print("=" * 70)
    print("Web 搜尋器批次搜尋測試 (AV-WIKI)")
    print("=" * 70)
    print()
    
    # 測試進度回調
    def progress_cb(msg):
        print(msg, end='')
    
    # 執行批次搜尋
    results = searcher.batch_search_avwiki_concurrent(
        BATCH_TEST_CODES,
        stop_event,
        progress_callback=progress_cb
    )
    
    print()
    print("=" * 70)
    print("結果")
    print("=" * 70)
    
    success_count = 0
    failure_count = 0
    
    for code in BATCH_TEST_CODES:
        if code in results:
            result = results[code]
            actresses = result.get('actresses', []) if result else []
            
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
    print("統計")
    print("=" * 70)
    print(f"成功: {success_count}/{len(BATCH_TEST_CODES)} ({success_count/len(BATCH_TEST_CODES)*100:.1f}%)")
    print(f"失敗: {failure_count}/{len(BATCH_TEST_CODES)} ({failure_count/len(BATCH_TEST_CODES)*100:.1f}%)")

if __name__ == "__main__":
    test_batch_search_avwiki()
