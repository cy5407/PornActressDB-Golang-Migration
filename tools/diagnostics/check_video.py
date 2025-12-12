#!/usr/bin/env python3
"""
檢查特定番號的資料
"""

import json


def check_video(code):
    """檢查番號資料"""

    with open("data/json_db/data.json", encoding="utf-8") as f:
        data = json.load(f)

    videos = data.get("videos", {})

    if code not in videos:
        print(f"❌ 番號 {code} 不在資料庫中")
        return

    video = videos[code]

    print(f"📝 番號: {code}")
    print(f"{'=' * 60}")
    print(f"女優 ({len(video.get('actresses', []))} 位):")
    for i, actress in enumerate(video.get("actresses", []), 1):
        print(f"  {i}. {actress}")

    print()
    print(f"片商: {video.get('studio', '（無）')}")
    print(f"標題: {video.get('title', '（無）')}")
    print()
    print(f"所有欄位: {list(video.keys())}")


if __name__ == "__main__":
    check_video("SAVR-00410")
