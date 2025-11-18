#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
檢查資料庫中所有有超過 10 位女優的番號
用於驗證是否有解析錯誤
"""

import json
from pathlib import Path
from collections import defaultdict

def check_large_actress_videos():
    """檢查擁有超過 10 位女優的番號"""
    
    db_file = Path("data/json_db/data.json")
    
    if not db_file.exists():
        print(f"❌ 資料庫檔案不存在: {db_file}")
        return
    
    with open(db_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    videos = data.get('videos', {})
    
    # 找出女優超過 10 位的番號
    large_actress_videos = []
    
    for code, video_info in videos.items():
        actresses = video_info.get('actresses', [])
        
        if len(actresses) > 10:
            large_actress_videos.append({
                'code': code,
                'count': len(actresses),
                'actresses': actresses,
                'studio': video_info.get('studio', '未知'),
                'title': video_info.get('title', '未知')[:60],
            })
    
    # 按女優數量排序
    large_actress_videos.sort(key=lambda x: x['count'], reverse=True)
    
    print(f"📊 資料庫統計")
    print(f"{'='*70}")
    print(f"總番號數: {len(videos)}")
    print(f"女優超過 10 位的番號: {len(large_actress_videos)}")
    print()
    
    if not large_actress_videos:
        print("✅ 沒有發現女優超過 10 位的番號")
        return
    
    print(f"{'番號':<12} {'女優數':<6} {'片商':<15} {'標題':<30}")
    print(f"{'-'*70}")
    
    # 分類統計
    by_count = defaultdict(list)
    
    for item in large_actress_videos:
        count = item['count']
        by_count[count].append(item['code'])
        
        print(f"{item['code']:<12} {item['count']:<6} {item['studio']:<15} {item['title']:<30}")
    
    # 統計摘要
    print()
    print(f"{'='*70}")
    print("📈 按女優數量分類:")
    print()
    
    for count in sorted(by_count.keys(), reverse=True):
        codes = by_count[count]
        print(f"  {count:>3} 位女優的番號 ({len(codes)} 個): {', '.join(sorted(codes)[:10])}", end="")
        if len(codes) > 10:
            print(f", ... 等 {len(codes) - 10} 個", end="")
        print()
    
    # 詳細資訊
    print()
    print(f"{'='*70}")
    print("📋 詳細資訊 (前 15 個):")
    print()
    
    for i, item in enumerate(large_actress_videos[:15], 1):
        print(f"{i}. {item['code']} ({item['count']} 位女優)")
        print(f"   片商: {item['studio']}")
        print(f"   標題: {item['title']}")
        print(f"   女優: {', '.join(item['actresses'][:5])}", end="")
        if len(item['actresses']) > 5:
            print(f" ... ({len(item['actresses']) - 5} 位)", end="")
        print()
        print()
    
    if len(large_actress_videos) > 15:
        print(f"... 還有 {len(large_actress_videos) - 15} 個番號")

if __name__ == '__main__':
    check_large_actress_videos()
