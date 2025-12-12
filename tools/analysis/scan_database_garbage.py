#!/usr/bin/env python3
"""
掃描資料庫中的垃圾文本
"""

import json
import re
from collections import defaultdict
from pathlib import Path


# 從 avwiki_scraper.py 複製驗證邏輯（更新後的版本）
def is_valid_actress_name(name: str) -> bool:
    """驗證女優名稱是否有效"""
    if not name or not isinstance(name, str):
        return False

    name = name.strip()

    # 女優名稱長度限制（允許 # 分隔的多人共演格式）
    if len(name) < 2 or len(name) > 50:
        return False

    # 垃圾文本模式（完整詞組，避免誤殺）
    garbage_patterns = [
        r"アナウンサー",
        r"監督",
        r"禁欲生活",
        r"同人漫画",
        r"ド変態",
        r"コスプレ",
        r"デカチン",
        r"降臨",
        r"人気の",
        r"クラスで",
        r"カ月",
        r"ヵ月",
        r"止まらない",
        r"やめて",
        r"なまなかだし",
        r"イカせて",
        r"ネット局",
        r"ネットで",
        r"見つけた",
        r"ボデ",
        r"^元ネット",
        r"細くて$",
        r"みたいな",
        r"天性の",
    ]

    for pattern in garbage_patterns:
        if re.search(pattern, name):
            return False

    # 必須包含日文字符
    if not any(
        "\u3040" <= c <= "\u309f"  # 平假名
        or "\u30a0" <= c <= "\u30ff"  # 片假名
        or "\u4e00" <= c <= "\u9fff"  # 漢字
        for c in name
    ):
        return False

    # 排除關鍵詞
    exclude_keywords = [
        "作品",
        "出演",
        "番号",
        "タイトル",
        "メーカー",
        "レーベル",
        "シリーズ",
        "発売日",
        "収録時間",
        "ジャンル",
        "出演者",
        "監督",
        "ありません",
        "ありませんでした",
        "いない",
        "ない",
        "ません",
        "です",
        "ます",
        "ました",
        "Menu",
        "star",
        "SOKMIL",
        "actress",
        "エスワン",
        "アイデアポケット",
        "プレミアム",
        "ムーディーズ",
    ]

    for keyword in exclude_keywords:
        if keyword in name:
            return False

    return True


# 讀取資料庫
db_file = Path("data/json_db/data.json")
if not db_file.exists():
    print(f"❌ 資料庫檔案不存在: {db_file}")
    exit(1)

with open(db_file, encoding="utf-8") as f:
    data = json.load(f)

print("=" * 80)
print("資料庫垃圾文本掃描")
print("=" * 80)

# 分析 actresses 字段（全域女優列表）
print("\n📋 分析全域女優列表 (actresses 字段)...")
actresses = data.get("actresses", [])
print(f"總女優數: {len(actresses)}")

invalid_actresses = []
garbage_actresses = []
merged_actresses = []

for actress in actresses:
    if not is_valid_actress_name(actress):
        invalid_actresses.append(actress)
        if "#" in actress:
            merged_actresses.append(actress)
        else:
            garbage_actresses.append(actress)

print("\n🔍 發現問題:")
print(f"  - 總無效女優: {len(invalid_actresses)}")
print(f"  - 垃圾文本: {len(garbage_actresses)}")
print(f"  - 合併名稱 (#): {len(merged_actresses)}")

if garbage_actresses:
    print("\n🗑️  垃圾文本樣本 (前 20 個):")
    for name in garbage_actresses[:20]:
        print(f"    - {name}")

if merged_actresses:
    print("\n🔗 合併名稱樣本 (前 10 個):")
    for name in merged_actresses[:10]:
        print(f"    - {name}")

# 分析影片中的女優
print("\n" + "=" * 80)
print("📀 分析影片中的女優資訊...")
videos = data.get("videos", {})
print(f"總影片數: {len(videos)}")

videos_with_garbage = []
actress_video_map = defaultdict(list)  # 記錄哪些影片包含哪些垃圾女優

for code, video in videos.items():
    video_actresses = video.get("actresses", [])

    invalid_in_video = []
    for actress in video_actresses:
        if not is_valid_actress_name(actress):
            invalid_in_video.append(actress)
            actress_video_map[actress].append(code)

    if invalid_in_video:
        videos_with_garbage.append(
            {
                "code": code,
                "title": video.get("title", ""),
                "invalid_actresses": invalid_in_video,
            }
        )

print("\n🔍 發現問題:")
print(f"  - 包含無效女優的影片: {len(videos_with_garbage)}")

if videos_with_garbage:
    print("\n📹 問題影片樣本 (前 15 個):")
    for item in videos_with_garbage[:15]:
        print(f"\n  [{item['code']}]")
        print(f"    標題: {item['title'][:50]}...")
        print(f"    無效女優: {', '.join(item['invalid_actresses'])}")

# 統計最常見的垃圾文本
print("\n" + "=" * 80)
print("📊 垃圾文本統計")
print("=" * 80)

garbage_frequency = defaultdict(int)
for actress in invalid_actresses:
    garbage_frequency[actress] += 1

# 從影片中也統計
for actress, video_codes in actress_video_map.items():
    garbage_frequency[actress] += len(video_codes)

# 排序
sorted_garbage = sorted(garbage_frequency.items(), key=lambda x: x[1], reverse=True)

print("\n🔝 出現最頻繁的垃圾文本 (前 30 個):")
for name, count in sorted_garbage[:30]:
    video_count = len(actress_video_map.get(name, []))
    in_global = "✓" if name in actresses else " "
    print(f"  [{in_global}] {name:30s} - {count:3d} 次 (影片: {video_count})")

# 總結
print("\n" + "=" * 80)
print("📈 總結")
print("=" * 80)
print("全域女優列表:")
print(f"  - 總數: {len(actresses)}")
print(f"  - 有效: {len(actresses) - len(invalid_actresses)}")
print(f"  - 垃圾文本: {len(garbage_actresses)}")
print(f"  - 合併名稱: {len(merged_actresses)}")
print("\n影片資料:")
print(f"  - 包含垃圾文本的影片: {len(videos_with_garbage)}")
print(f"  - 不同的垃圾文本: {len(sorted_garbage)}")

# 建議
print("\n" + "=" * 80)
print("💡 建議")
print("=" * 80)
if invalid_actresses:
    print(f"✅ 可以清理 {len(invalid_actresses)} 個無效女優名稱")
    print(f"   - 從 actresses 字段移除: {len(invalid_actresses)} 個")
    print(f"   - 從影片記錄移除: {len(videos_with_garbage)} 個影片需要處理")
else:
    print("✅ 資料庫乾淨，沒有垃圾文本！")
