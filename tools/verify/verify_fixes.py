#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修復驗證工具
檢查所有修復是否成功應用
"""

import json
from pathlib import Path
import asyncio
from src.scrapers.sources.avwiki_scraper import AVWikiScraper

def verify_fixes():
    """驗證所有修復"""
    
    print("[*] 系統修復驗證")
    print("=" * 70)
    print()
    
    # 1. 檢查 JSON 存取邏輯
    print("[1] 驗證 JSON 檔案存取...")
    try:
        with open('data/json_db/data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        videos_count = len(data.get('videos', {}))
        print(f"    [OK] JSON 檔案讀取成功")
        print(f"    [OK] 發現 {videos_count} 個番號")
        
        # 檢查大女優數
        max_actresses = 0
        for code, video in data['videos'].items():
            actress_count = len(video.get('actresses', []))
            if actress_count > max_actresses:
                max_actresses = actress_count
        
        if max_actresses > 20:
            print(f"    [FAIL] 仍然發現超大女優數: {max_actresses}")
        else:
            print(f"    [OK] 最大女優數: {max_actresses} (正常)")
        
    except Exception as e:
        print(f"    [FAIL] JSON 讀取失敗: {e}")
        return False
    
    print()
    
    # 2. 檢查爬蟲邏輯
    print("[2] 驗證 AV-WIKI 爬蟲修復...")
    try:
        scraper = AVWikiScraper()
        
        # 檢查 _parse_search_results 方法是否使用 tag 連結
        import inspect
        source = inspect.getsource(scraper._parse_search_results)
        
        if 'rel="tag"' in source and '/av-actress/' in source:
            print(f"    [OK] 已使用 rel='tag' 和 /av-actress/ 檢查")
        else:
            print(f"    [FAIL] 爬蟲邏輯未更新")
        
        if 'tag_links = soup.find_all' in source:
            print(f"    [OK] 已實現 tag 連結查詢")
        else:
            print(f"    [FAIL] tag 連結查詢未實現")
        
    except Exception as e:
        print(f"    [FAIL] 爬蟲檢查失敗: {e}")
    
    print()
    
    # 3. 檢查重試邏輯
    print("[3] 驗證 JSON 保存重試機制...")
    try:
        from src.models.json_database import JSONDBManager
        import inspect
        
        manager = JSONDBManager()
        source = inspect.getsource(manager._save_all_data)
        
        if 'max_retries' in source and 'PermissionError' in source:
            print(f"    [OK] 已實現重試機制")
        else:
            print(f"    [FAIL] 重試機制未實現")
        
        if 'time.sleep' in source:
            print(f"    [OK] 已實現延遲重試")
        else:
            print(f"    [FAIL] 延遲重試未實現")
        
    except Exception as e:
        print(f"    [FAIL] 保存邏輯檢查失敗: {e}")
    
    print()
    print("=" * 70)
    print("[*] 驗證完成")

async def test_scraping():
    """測試爬蟲功能"""
    
    print("[*] AV-WIKI 爬蟲功能測試")
    print("=" * 70)
    print()
    
    scraper = AVWikiScraper()
    
    # 測試一個應該有結果的番號
    test_code = 'SKMJ-581'
    
    print(f"測試番號: {test_code}")
    print("-" * 70)
    
    try:
        result = await scraper.search_video(test_code)
        actresses = result.get('actresses', [])
        
        print(f"[OK] 搜尋成功")
        print(f"     找到女優數: {len(actresses)}")
        print(f"     女優名單: {', '.join(actresses[:5])}", end="")
        if len(actresses) > 5:
            print(f" ... (+{len(actresses) - 5})")
        else:
            print()
        
        if len(actresses) > 0 and len(actresses) <= 15:
            print(f"     [OK] 女優數量正常 (1-15)")
        elif len(actresses) == 0:
            print(f"     [WARN] 無女優 (可能是搜尋無結果)")
        else:
            print(f"     [FAIL] 女優數量異常 ({len(actresses)} > 15)")
        
    except Exception as e:
        print(f"[FAIL] 搜尋失敗: {e}")
    
    print()

if __name__ == '__main__':
    verify_fixes()
    print()
    print("現在執行爬蟲功能測試...")
    print()
    asyncio.run(test_scraping())
