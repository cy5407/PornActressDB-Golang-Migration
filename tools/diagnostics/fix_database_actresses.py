#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修正資料庫中的女優名稱和片商資訊
"""

import json
import re
from pathlib import Path
from datetime import datetime

# 讀取資料庫
db_file = Path('data/json_db/data.json')
backup_file = Path('data/json_db/backup') / f'data_before_cleanup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'

print("=" * 80)
print("資料庫修正工具")
print("=" * 80)

# 創建備份目錄
backup_file.parent.mkdir(parents=True, exist_ok=True)

# 讀取資料
with open(db_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 備份
print(f"\n📋 創建備份: {backup_file.name}")
with open(backup_file, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("\n🔧 開始修正...")

# 統計
stats = {
    'videos_fixed': 0,
    'actresses_removed': 0,
    'actresses_added': 0,
    'studios_updated': 0,
}

# 修正規則
fixes = [
    {
        'name': '宇野みれいエスワン',
        'correct_actress': '宇野みれい',
        'studio': 'S1',
        'description': '片商名稱合併問題'
    },
    {
        'name': 'なまなかだし瀧本雫葉',
        'correct_actress': '瀧本雫葉',
        'studio': None,
        'description': '垃圾文本前綴'
    },
]

# 處理影片
videos = data.get('videos', {})
print(f"\n📀 檢查 {len(videos)} 個影片...")

for code, video in videos.items():
    actresses = video.get('actresses', [])
    modified = False
    
    for fix in fixes:
        if fix['name'] in actresses:
            print(f"\n  [{code}] 發現: {fix['name']}")
            print(f"    原因: {fix['description']}")
            
            # 移除錯誤的名稱
            actresses.remove(fix['name'])
            print(f"    ✓ 移除: {fix['name']}")
            stats['actresses_removed'] += 1
            
            # 添加正確的女優名稱
            if fix['correct_actress'] and fix['correct_actress'] not in actresses:
                actresses.append(fix['correct_actress'])
                print(f"    ✓ 添加女優: {fix['correct_actress']}")
                stats['actresses_added'] += 1
            
            # 更新片商（如果有）
            if fix['studio']:
                old_studio = video.get('studio', 'UNKNOWN')
                if old_studio == 'UNKNOWN' or not old_studio:
                    video['studio'] = fix['studio']
                    print(f"    ✓ 設定片商: {fix['studio']}")
                    stats['studios_updated'] += 1
            
            modified = True
    
    if modified:
        video['actresses'] = actresses
        video['updated_at'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        stats['videos_fixed'] += 1

# 處理全域女優列表（字典格式：{actress_id: actress_data}）
actresses_dict = data.get('actresses', {})
print(f"\n👥 檢查全域女優列表 ({len(actresses_dict)} 位)...")

# 收集需要刪除的 actress_id
ids_to_delete = []
actresses_to_add = {}

for actress_id, actress_data in actresses_dict.items():
    actress_name = actress_data.get('name', '')
    
    for fix in fixes:
        if actress_name == fix['name']:
            print(f"\n  [ID: {actress_id}] 移除錯誤名稱: {fix['name']}")
            ids_to_delete.append(actress_id)
            stats['actresses_removed'] += 1
            
            # 準備添加正確名稱
            if fix['correct_actress']:
                # 檢查是否已存在
                exists = any(
                    a.get('name') == fix['correct_actress'] 
                    for a in actresses_dict.values()
                )
                if not exists and fix['correct_actress'] not in actresses_to_add:
                    actresses_to_add[fix['correct_actress']] = fix['correct_actress']

# 移除特殊符號垃圾文本
garbage_symbols = ['＊＊＊', '(≥o≤)']
for actress_id, actress_data in list(actresses_dict.items()):
    actress_name = actress_data.get('name', '')
    if actress_name in garbage_symbols:
        print(f"\n  [ID: {actress_id}] 移除特殊符號: {actress_name}")
        ids_to_delete.append(actress_id)
        stats['actresses_removed'] += 1

# 執行刪除
for actress_id in ids_to_delete:
    del actresses_dict[actress_id]

# 添加正確的女優名稱
for actress_name in actresses_to_add.values():
    # 生成新的 actress_id
    new_id = f"actress_{len(actresses_dict) + 1}"
    actresses_dict[new_id] = {
        'id': new_id,
        'name': actress_name,
        'aliases': [],
        'video_count': 0,
        'created_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'updated_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    }
    print(f"\n  [ID: {new_id}] 添加正確名稱: {actress_name}")
    stats['actresses_added'] += 1

data['actresses'] = actresses_dict

# 更新後設資料
data['updated_at'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

# 保存修正後的資料
print(f"\n💾 保存修正後的資料...")
with open(db_file, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("\n" + "=" * 80)
print("📊 修正統計")
print("=" * 80)
print(f"影片修正: {stats['videos_fixed']} 個")
print(f"移除錯誤女優名稱: {stats['actresses_removed']} 次")
print(f"添加正確女優名稱: {stats['actresses_added']} 次")
print(f"片商更新: {stats['studios_updated']} 個")

print("\n✅ 修正完成！")
print(f"備份位置: {backup_file}")
