#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查詢 FALENO 片商的所有名稱變體
"""

import sys
from pathlib import Path

# 添加專案根目錄到系統路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from models.json_database import JSONDBManager

def check_faleno_studios():
    """查詢 FALENO 的所有片商名稱變體"""
    
    db = JSONDBManager()
    all_videos = db.data.get('videos', {})
    
    # 找出所有包含 FALENO 的片商名稱
    faleno_variants = {}
    
    for code, info in all_videos.items():
        studio = info.get('studio', '')
        if any(keyword in studio.upper() for keyword in ['FALENO', 'ファレノ']):
            if studio not in faleno_variants:
                faleno_variants[studio] = []
            faleno_variants[studio].append(code)
    
    print("=" * 60)
    print("🏢 FALENO 相關片商名稱分析")
    print("=" * 60)
    print(f"\n找到 {len(faleno_variants)} 種不同的片商名稱\n")
    
    # 按數量排序顯示
    for variant, codes in sorted(faleno_variants.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"📌 {variant}: {len(codes)} 個番號")
        print()
        
        # 顯示前 5 個
        for i, code in enumerate(codes[:5], 1):
            actresses = all_videos[code].get('actresses', [])
            actresses_str = ', '.join(actresses) if actresses else '(無女優資料)'
            status = all_videos[code].get('search_status', '未知')
            print(f"  {i}. {code}")
            print(f"     女優: {actresses_str}")
            print(f"     狀態: {status}")
        
        if len(codes) > 5:
            print(f"  ... 還有 {len(codes) - 5} 個\n")
        else:
            print()
    
    # 統計總數
    total = sum(len(codes) for codes in faleno_variants.values())
    print(f"📊 總計: {total} 個番號")

if __name__ == "__main__":
    check_faleno_studios()
