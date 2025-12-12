#!/usr/bin/env python3
"""
批次更新 FALENO 片商名稱標準化
"""

import sys
from pathlib import Path

# 添加專案根目錄到系統路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from models.incremental_json_database import IncrementalJSONDB


def update_faleno_studios():
    """將所有 FALENO 相關片商名稱統一為 FALENO"""

    db = IncrementalJSONDB()

    # 載入所有資料
    all_videos = db.data.get("videos", {})

    print("🔍 正在掃描資料庫...")
    print(f"總共 {len(all_videos)} 個番號\n")

    # FALENO 的各種名稱變體
    faleno_variants = ["FALENO star", "ファレノ", "FALENO TUBE"]

    # 找出所有需要更新的番號
    codes_to_update = {}
    for variant in faleno_variants:
        codes_to_update[variant] = []

    for code, info in all_videos.items():
        studio = info.get("studio", "")
        if studio in faleno_variants:
            codes_to_update[studio].append(code)

    # 統計
    total_count = sum(len(codes) for codes in codes_to_update.values())

    print(f"📊 找到 {total_count} 個需要標準化的番號\n")

    for variant, codes in codes_to_update.items():
        if codes:
            print(f"  {variant}: {len(codes)} 個")
            # 顯示前 2 個
            for code in codes[:2]:
                actresses = all_videos[code].get("actresses", [])
                actresses_str = ", ".join(actresses) if actresses else "無女優資料"
                print(f"    - {code} ({actresses_str})")
            if len(codes) > 2:
                print(f"    ... 還有 {len(codes) - 2} 個")
            print()

    if total_count == 0:
        print("✅ 沒有需要更新的資料")
        return

    # 確認更新
    confirm = input(
        f"⚠️ 確定要將這 {total_count} 個番號的片商統一更新為 'FALENO' 嗎？ (y/n): "
    )

    if confirm.lower() != "y":
        print("❌ 已取消更新")
        return

    # 執行更新
    print("\n🔄 正在更新...")
    updated_count = 0

    for variant, codes in codes_to_update.items():
        for code in codes:
            video_info = all_videos[code]
            video_info["studio"] = "FALENO"
            db.add_or_update_video(code, video_info)
            updated_count += 1

    print(f"\n✅ 成功更新 {updated_count} 個番號")

    # 驗證
    print("\n🔍 驗證更新結果...")
    remaining = 0
    for code, info in db.data.get("videos", {}).items():
        studio = info.get("studio", "")
        if studio in faleno_variants:
            remaining += 1

    if remaining == 0:
        print("✅ 驗證通過：所有 FALENO 變體都已統一為 FALENO")
    else:
        print(f"⚠️ 警告：還有 {remaining} 個未更新")


if __name__ == "__main__":
    update_faleno_studios()
