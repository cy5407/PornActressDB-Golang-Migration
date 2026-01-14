#!/usr/bin/env python3
"""
批次更新 S1 片商名稱標準化
"""

import sys
from pathlib import Path

# 設定專案路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from models.incremental_json_database import IncrementalJSONDB


def update_s1_studios():
    """將所有 S1 相關片商名稱統一為 S1"""

    db = IncrementalJSONDB()

    # 載入所有資料
    all_videos = db.data.get("videos", {})

    print("🔍 正在掃描資料庫...")
    print(f"總共 {len(all_videos)} 個番號\n")

    # S1 的各種名稱變體
    s1_variants = ["エスワン", "S1 NO.1 STYLE", "s1", "S1 no.1 style"]

    # 找出所有需要更新的番號
    codes_to_update = {}
    for variant in s1_variants:
        codes_to_update[variant] = []

    for code, info in all_videos.items():
        studio = info.get("studio", "")
        if studio in s1_variants:
            codes_to_update[studio].append(code)

    # 統計
    total_count = sum(len(codes) for codes in codes_to_update.values())

    print(f"📊 找到 {total_count} 個需要標準化的番號\n")

    for variant, codes in codes_to_update.items():
        if codes:
            print(f"  {variant}: {len(codes)} 個")
            # 顯示前 3 個
            for code in codes[:3]:
                actresses = all_videos[code].get("actresses", [])
                actresses_str = ", ".join(actresses) if actresses else "無女優資料"
                print(f"    - {code} ({actresses_str})")
            if len(codes) > 3:
                print(f"    ... 還有 {len(codes) - 3} 個")
            print()

    if total_count == 0:
        print("✅ 沒有需要更新的資料")
        return

    # 確認更新
    confirm = input(
        f"⚠️ 確定要將這 {total_count} 個番號的片商統一更新為 'S1' 嗎？ (y/n): "
    )

    if confirm.lower() != "y":
        print("❌ 已取消更新")
        return

    # 執行更新
    print("\n🔄 正在更新...")
    updated_count = 0

    for _, codes in codes_to_update.items():
        for code in codes:
            video_info = all_videos[code]
            video_info["studio"] = "S1"
            db.add_or_update_video(code, video_info)
            updated_count += 1

    print(f"\n✅ 成功更新 {updated_count} 個番號")

    # 驗證
    print("\n🔍 驗證更新結果...")
    remaining = {}
    for variant in s1_variants:
        remaining[variant] = 0

    for _, info in db.data.get("videos", {}).items():
        studio = info.get("studio", "")
        if studio in s1_variants:
            remaining[studio] += 1

    total_remaining = sum(remaining.values())

    if total_remaining == 0:
        print("✅ 驗證通過：所有 S1 變體都已統一為 S1")
    else:
        print(f"⚠️ 警告：還有 {total_remaining} 個未更新")
        for variant, count in remaining.items():
            if count > 0:
                print(f"  {variant}: {count} 個")


if __name__ == "__main__":
    update_s1_studios()
