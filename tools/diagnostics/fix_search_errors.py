"""修正資料庫中的錯誤搜尋結果"""

import json
import sys
from datetime import datetime
from pathlib import Path

# 添加專案根目錄到 Python 路徑
sys.path.insert(0, str(Path(__file__).parent / "src"))


def is_likely_wrong_actress_data(actresses: list[str]) -> bool:
    """判斷女優列表是否可能是錯誤資料"""

    if not actresses:
        return False

    # 超過 10 位女優很可能是錯誤
    if len(actresses) > 10:
        return True

    # 檢查是否包含明顯的非女優關鍵詞
    wrong_keywords = [
        "シロウト",
        "しろうと",
        "パコパコ",
        "ナンパ",
        "ハメ撮り",
        "ギャラリー",
        "チャンネル",
        "ドリームチケット",
        "レーベル",
        "プロジェクト",
        "グループ",
        "クラブ",
        "サークル",
        "素人",
        "企画",
        "配信",
        "限定",
        "レズれ",
        "ミラー号",
        "れいんぎが",
        "ぎが",
        "かぐや",
        "ちゃん",
        "さん",
    ]

    # 如果超過一半的"女優"包含錯誤關鍵詞
    wrong_count = sum(
        1
        for actress in actresses
        if any(keyword in actress for keyword in wrong_keywords)
    )

    return wrong_count > len(actresses) * 0.3


def fix_database(db_path: str, backup: bool = True):
    """修正資料庫中的錯誤資料"""

    db_file = Path(db_path)
    if not db_file.exists():
        print(f"❌ 資料庫檔案不存在: {db_path}")
        return

    # 備份
    if backup:
        backup_path = (
            db_file.parent
            / f"data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        print(f"📦 建立備份: {backup_path}")
        with open(db_file, encoding="utf-8") as f:
            backup_data = f.read()
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(backup_data)

    # 載入資料
    print(f"📖 讀取資料庫: {db_path}")
    with open(db_file, encoding="utf-8") as f:
        data = json.load(f)

    videos = data.get("videos", {})
    total = len(videos)

    print(f"📊 資料庫中共有 {total} 筆影片記錄\n")

    # 分析並修正
    fixed_count = 0
    suspicious_count = 0
    no_actress_count = 0

    suspicious_videos = []

    for code, info in videos.items():
        actresses = info.get("actresses", [])

        # 空的女優列表
        if not actresses:
            no_actress_count += 1
            if "search_status" not in info:
                info["search_status"] = "no_actress_found"
                fixed_count += 1
            continue

        # 檢查是否為錯誤資料
        if is_likely_wrong_actress_data(actresses):
            suspicious_videos.append(
                {
                    "code": code,
                    "actress_count": len(actresses),
                    "actresses": actresses[:10],  # 只顯示前 10 個
                    "file_path": info.get("file_path", "N/A"),
                }
            )

            # 標記為錯誤
            info["search_status"] = "search_error"
            info["search_error_reason"] = "too_many_suspicious_results"
            info["original_actress_count"] = len(actresses)
            # 清空女優列表
            info["actresses"] = []

            fixed_count += 1
            suspicious_count += 1

    # 顯示報告
    print("=" * 80)
    print("📋 修正報告")
    print("=" * 80)
    print(f"✅ 正常記錄: {total - fixed_count} 筆")
    print(f"❌ 錯誤記錄（已修正）: {suspicious_count} 筆")
    print(f"⚠️  無女優記錄: {no_actress_count} 筆")
    print(f"📝 總修正數: {fixed_count} 筆\n")

    # 顯示可疑記錄
    if suspicious_videos:
        print("=" * 80)
        print(f"🔍 發現 {len(suspicious_videos)} 筆可疑記錄（已清空女優列表）")
        print("=" * 80)

        for i, video in enumerate(suspicious_videos[:10], 1):  # 只顯示前 10 筆
            print(f"\n{i}. 番號: {video['code']}")
            print(f"   檔案: {video['file_path']}")
            print(f"   原女優數: {video['actress_count']}")
            print("   原女優列表前 10 個:")
            for actress in video["actresses"][:10]:
                print(f"     - {actress}")

        if len(suspicious_videos) > 10:
            print(f"\n   ... 還有 {len(suspicious_videos) - 10} 筆記錄")

    # 儲存修正後的資料
    print("\n" + "=" * 80)
    if fixed_count > 0:
        print("💾 儲存修正後的資料...")
        with open(db_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ 已儲存 {fixed_count} 筆修正記錄")
    else:
        print("✅ 沒有需要修正的記錄")

    print("=" * 80)

    # 返回統計資訊
    return {
        "total": total,
        "fixed": fixed_count,
        "suspicious": suspicious_count,
        "no_actress": no_actress_count,
        "suspicious_videos": suspicious_videos,
    }


def show_specific_video(db_path: str, code: str):
    """顯示特定番號的資訊"""

    with open(db_path, encoding="utf-8") as f:
        data = json.load(f)

    videos = data.get("videos", {})

    # 嘗試多種格式
    video_info = None
    for key in [
        code,
        code.upper(),
        code.replace("-", ""),
        code.upper().replace("-", ""),
    ]:
        if key in videos:
            video_info = videos[key]
            code = key
            break

    if not video_info:
        print(f"❌ 找不到番號: {code}")
        return

    print("=" * 80)
    print(f"📹 番號: {code}")
    print("=" * 80)
    print(f"檔案名稱: {video_info.get('original_filename', 'N/A')}")
    print(f"檔案路徑: {video_info.get('file_path', 'N/A')}")
    print(f"片商: {video_info.get('studio', 'N/A')}")
    print(f"搜尋方法: {video_info.get('search_method', 'N/A')}")
    print(f"搜尋狀態: {video_info.get('search_status', 'N/A')}")

    actresses = video_info.get("actresses", [])
    print(f"\n女優數量: {len(actresses)}")

    if actresses:
        print("女優列表:")
        for i, actress in enumerate(actresses, 1):
            print(f"  {i:3d}. {actress}")
    else:
        print("女優列表: (空)")

    print("=" * 80)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="修正資料庫中的錯誤搜尋結果")
    parser.add_argument("--db", default="data/json_db/data.json", help="資料庫檔案路徑")
    parser.add_argument("--show", help="顯示特定番號的資訊")
    parser.add_argument("--no-backup", action="store_true", help="不建立備份")

    args = parser.parse_args()

    if args.show:
        show_specific_video(args.db, args.show)
    else:
        fix_database(args.db, backup=not args.no_backup)
