#!/usr/bin/env python3
"""
批次更新 MOODYZ DIVA -> MOODYZ
"""

import sys
from pathlib import Path

# 添加專案根目錄到系統路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from models.incremental_json_database import IncrementalJSONDB


def update_moodyz_studios():
    """將所有 MOODYZ DIVA 更新為 MOODYZ"""

    db = IncrementalJSONDB()

    # 載入所有資料
    all_videos = db.data.get("videos", {})

    print("🔍 正在掃描資料庫...")
    print(f"總共 {len(all_videos)} 個番號\n")

    # 找出所有 MOODYZ DIVA 的番號
    moodyz_diva_codes = []
    for code, info in all_videos.items():
        studio = info.get("studio", "")
        if studio == "MOODYZ DIVA":
            moodyz_diva_codes.append(code)

    print(f"📊 找到 {len(moodyz_diva_codes)} 個 MOODYZ DIVA 的番號")

    if not moodyz_diva_codes:
        print("\n✅ 沒有需要更新的資料")
        return

    # 顯示前 10 個
    print("\n📋 前 10 個番號:")
    for i, code in enumerate(moodyz_diva_codes[:10], 1):
        actresses = all_videos[code].get("actresses", [])
        actresses_str = ", ".join(actresses) if actresses else "無女優資料"
        print(f"  {i}. {code} - {actresses_str}")

    if len(moodyz_diva_codes) > 10:
        print(f"  ... 還有 {len(moodyz_diva_codes) - 10} 個")

    # 確認更新
    confirm = input(
        f"\n⚠️ 確定要將這 {len(moodyz_diva_codes)} 個番號的片商從 'MOODYZ DIVA' 更新為 'MOODYZ' 嗎？ (y/n): "
    )

    if confirm.lower() != "y":
        print("❌ 已取消更新")
        return

    # 執行更新
    print("\n🔄 正在更新...")
    updated_count = 0

    for code in moodyz_diva_codes:
        video_info = all_videos[code]
        video_info["studio"] = "MOODYZ"
        db.add_or_update_video(code, video_info)
        updated_count += 1

    print(f"\n✅ 成功更新 {updated_count} 個番號")

    # 驗證
    print("\n🔍 驗證更新結果...")
    remaining = 0
    for code, info in db.data.get("videos", {}).items():
        if info.get("studio") == "MOODYZ DIVA":
            remaining += 1

    if remaining == 0:
        print("✅ 驗證通過：所有 MOODYZ DIVA 都已更新為 MOODYZ")
    else:
        print(f"⚠️ 警告：還有 {remaining} 個 MOODYZ DIVA 未更新")


if __name__ == "__main__":
    update_moodyz_studios()
