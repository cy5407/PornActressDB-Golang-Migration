#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
資料庫品質檢查工具
檢查異常資料（女優數=0、缺少必要欄位等）
"""

import json
from pathlib import Path
from collections import defaultdict

def check_database_quality():
    """檢查資料庫品質"""
    
    db_file = Path("data/json_db/data.json")
    
    if not db_file.exists():
        print(f"❌ 資料庫檔案不存在: {db_file}")
        return
    
    with open(db_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    videos = data.get('videos', {})
    actresses_db = data.get('actresses', {})
    
    # 統計信息
    no_actress = []
    no_studio = []
    no_title = []
    by_actress_count = defaultdict(int)
    
    for code, video_info in videos.items():
        actresses = video_info.get('actresses', [])
        studio = video_info.get('studio', '')
        title = video_info.get('title', '')
        
        # 計算女優數
        actress_count = len(actresses)
        by_actress_count[actress_count] += 1
        
        if actress_count == 0:
            no_actress.append(code)
        if not studio:
            no_studio.append(code)
        if not title:
            no_title.append(code)
    
    print(f"📊 資料庫品質檢查")
    print(f"{'='*70}")
    print(f"總番號數: {len(videos)}")
    print(f"總女優數: {len(actresses_db)}")
    print()
    
    # 女優數統計
    print(f"👥 女優數統計:")
    print("-" * 50)
    
    # 按女優數分組
    actress_groups = {
        (0, 0): "0位女優",
        (1, 1): "1位女優",
        (2, 2): "2位女優",
        (3, 5): "3-5位女優",
        (6, 10): "6-10位女優",
        (11, 20): "11-20位女優",
        (21, float('inf')): "21位以上女優",
    }
    
    for (min_count, max_count), label in actress_groups.items():
        count = sum(c for ac, c in by_actress_count.items() if min_count <= ac <= max_count)
        if count > 0:
            print(f"  {label}: {count} 個")
    
    print()
    print(f"❌ 異常資料:")
    print("-" * 50)
    print(f"  無女優 (0位): {len(no_actress)} 個")
    if no_actress and len(no_actress) <= 20:
        print(f"    {', '.join(no_actress[:20])}")
    
    print(f"  缺少片商: {len(no_studio)} 個")
    if no_studio and len(no_studio) <= 20:
        print(f"    {', '.join(no_studio[:20])}")
    
    print(f"  缺少標題: {len(no_title)} 個")
    if no_title and len(no_title) <= 20:
        print(f"    {', '.join(no_title[:20])}")
    
    print()
    print(f"✅ 資料庫檢查完成")
    
    # 統計資訊
    if not no_actress and not no_studio and not no_title:
        print("   所有番號資料完整！")
    else:
        print(f"   需要修復: {len(no_actress) + len(no_studio) + len(no_title)} 個")

if __name__ == '__main__':
    check_database_quality()
