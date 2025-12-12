#!/usr/bin/env python3
"""
查詢白上咲花和紫堂るい的資料
"""

import sys
from pathlib import Path

# 添加專案根目錄到系統路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from models.incremental_json_database import IncrementalJSONDB


def search_actresses():
    """查詢白上咲花和紫堂るい的資料"""

    db = IncrementalJSONDB()
    all_videos = db.data.get("videos", {})

    target_actresses = ["白上咲花", "紫堂るい"]
    results = {}

    for code, info in all_videos.items():
        actresses = info.get("actresses", [])
        for target in target_actresses:
            if target in actresses:
                if target not in results:
                    results[target] = []
                results[target].append(
                    {
                        "code": code,
                        "actresses": actresses,
                        "studio": info.get("studio", "未知"),
                        "search_status": info.get("search_status", "未知"),
                        "search_method": info.get("search_method", "未知"),
                    }
                )

    print("=" * 60)
    print("🔍 白上咲花 和 紫堂るい 的資料庫資訊")
    print("=" * 60)

    for actress in target_actresses:
        print(f"\n👩 {actress}")
        print("-" * 60)

        if actress in results:
            videos = results[actress]
            print(f"找到 {len(videos)} 個番號\n")

            # 統計片商
            studios = {}
            for v in videos:
                studio = v["studio"]
                studios[studio] = studios.get(studio, 0) + 1

            print("📊 片商分佈:")
            for studio, count in sorted(
                studios.items(), key=lambda x: x[1], reverse=True
            ):
                print(f"  {studio}: {count} 個")

            # 顯示前 5 個番號
            print("\n📋 前 5 個番號:")
            for i, v in enumerate(videos[:5], 1):
                actresses_str = ", ".join(v["actresses"])
                print(f"  {i}. {v['code']}")
                print(f"     女優: {actresses_str}")
                print(f"     片商: {v['studio']}")
                print(f"     狀態: {v['search_status']}")
                print()

            if len(videos) > 5:
                print(f"  ... 還有 {len(videos) - 5} 個\n")
        else:
            print("❌ 資料庫中沒有此女優的資料\n")


if __name__ == "__main__":
    search_actresses()
