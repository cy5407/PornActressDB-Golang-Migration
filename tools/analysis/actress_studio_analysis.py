"""
女優片商分析工具

從資料庫撈取女優資料，反查她們的番號所屬片商，
統計每位女優的片商分佈情況。
"""

import json
from collections import defaultdict
from pathlib import Path


def load_database():
    """載入資料庫"""
    db_path = Path(__file__).parent.parent.parent / "data/json_db/data.json"
    with open(db_path, "r", encoding="utf-8") as f:
        return json.load(f)


def analyze_actress_studios(data: dict) -> dict:
    """
    分析每位女優的片商分佈

    Returns:
        dict: {
            "女優名": {
                "total_videos": 總影片數,
                "studios": {"片商名": 影片數, ...},
                "studio_count": 所屬片商數量,
                "primary_studio": 主要片商,
                "primary_ratio": 主要片商占比
            }
        }
    """
    videos = data.get("videos", {})
    actress_stats = defaultdict(lambda: {"total_videos": 0, "studios": defaultdict(int)})

    # 遍歷所有影片，統計每位女優的片商
    for code, video_info in videos.items():
        actresses = video_info.get("actresses", [])
        studio = video_info.get("studio", "UNKNOWN")

        if not studio or studio == "UNKNOWN":
            # 從番號提取片商
            studio = extract_studio_from_code(code)

        for actress in actresses:
            if actress:  # 過濾空值
                actress_stats[actress]["total_videos"] += 1
                actress_stats[actress]["studios"][studio] += 1

    # 計算統計資料
    results = {}
    for actress, stats in actress_stats.items():
        studios = dict(stats["studios"])
        total = stats["total_videos"]

        # 找出主要片商
        primary_studio = max(studios, key=studios.get) if studios else "UNKNOWN"
        primary_count = studios.get(primary_studio, 0)
        primary_ratio = (primary_count / total * 100) if total > 0 else 0

        results[actress] = {
            "total_videos": total,
            "studios": studios,
            "studio_count": len(studios),
            "primary_studio": primary_studio,
            "primary_count": primary_count,
            "primary_ratio": round(primary_ratio, 1),
        }

    return results


def extract_studio_from_code(code: str) -> str:
    """從番號提取片商代碼"""
    if not code:
        return "UNKNOWN"
    # 取番號前綴（字母部分）
    prefix = ""
    for char in code:
        if char.isalpha():
            prefix += char
        elif char == "-" or char.isdigit():
            break
    return prefix.upper() if prefix else "UNKNOWN"


def print_summary(results: dict, min_videos: int = 1, sort_by: str = "studio_count"):
    """
    輸出摘要報告

    Args:
        results: 分析結果
        min_videos: 最少影片數門檻
        sort_by: 排序方式 (studio_count, total_videos, primary_ratio)
    """
    # 過濾和排序
    filtered = {k: v for k, v in results.items() if v["total_videos"] >= min_videos}

    if sort_by == "studio_count":
        sorted_items = sorted(filtered.items(), key=lambda x: (-x[1]["studio_count"], -x[1]["total_videos"]))
    elif sort_by == "total_videos":
        sorted_items = sorted(filtered.items(), key=lambda x: -x[1]["total_videos"])
    else:
        sorted_items = sorted(filtered.items(), key=lambda x: x[1]["primary_ratio"])

    print("=" * 80)
    print(f"📊 女優片商分析報告 (最少 {min_videos} 部影片)")
    print("=" * 80)
    print(f"{'女優名':<20} {'影片數':>6} {'片商數':>6} {'主要片商':<15} {'占比':>8}")
    print("-" * 80)

    for actress, stats in sorted_items[:50]:  # 只顯示前50名
        print(
            f"{actress:<20} {stats['total_videos']:>6} {stats['studio_count']:>6} "
            f"{stats['primary_studio']:<15} {stats['primary_ratio']:>7.1f}%"
        )

    print("-" * 80)
    print(f"總計: {len(filtered)} 位女優")

    # 統計片商數量分佈
    studio_count_dist = defaultdict(int)
    for stats in filtered.values():
        studio_count_dist[stats["studio_count"]] += 1

    print("\n📈 片商數量分佈:")
    for count in sorted(studio_count_dist.keys()):
        print(f"   {count} 個片商: {studio_count_dist[count]} 位女優")


def print_multi_studio_actresses(results: dict, min_studios: int = 3):
    """列出跨多片商的女優"""
    print("\n" + "=" * 80)
    print(f"🎭 跨 {min_studios}+ 片商的女優")
    print("=" * 80)

    multi = {k: v for k, v in results.items() if v["studio_count"] >= min_studios}
    sorted_items = sorted(multi.items(), key=lambda x: (-x[1]["studio_count"], -x[1]["total_videos"]))

    for actress, stats in sorted_items:
        print(f"\n👩 {actress} ({stats['total_videos']} 部影片, {stats['studio_count']} 個片商)")
        # 按影片數排序片商
        sorted_studios = sorted(stats["studios"].items(), key=lambda x: -x[1])
        for studio, count in sorted_studios:
            ratio = count / stats["total_videos"] * 100
            bar = "█" * int(ratio / 5)
            print(f"   {studio:<12}: {count:>3} 部 ({ratio:>5.1f}%) {bar}")

    print(f"\n總計: {len(multi)} 位女優跨 {min_studios}+ 片商")


def print_single_studio_actresses(results: dict, min_videos: int = 5):
    """列出專屬單一片商的女優（專屬女優）"""
    print("\n" + "=" * 80)
    print(f"🏢 專屬女優 (100% 單一片商, 至少 {min_videos} 部影片)")
    print("=" * 80)

    exclusive = {
        k: v for k, v in results.items()
        if v["studio_count"] == 1 and v["total_videos"] >= min_videos
    }
    sorted_items = sorted(exclusive.items(), key=lambda x: -x[1]["total_videos"])

    # 按片商分組
    by_studio = defaultdict(list)
    for actress, stats in sorted_items:
        by_studio[stats["primary_studio"]].append((actress, stats["total_videos"]))

    for studio, actresses in sorted(by_studio.items(), key=lambda x: -len(x[1])):
        print(f"\n🏷️ {studio} ({len(actresses)} 位專屬女優)")
        for actress, count in actresses[:10]:  # 每片商最多顯示10位
            print(f"   {actress}: {count} 部")
        if len(actresses) > 10:
            print(f"   ... 還有 {len(actresses) - 10} 位")

    print(f"\n總計: {len(exclusive)} 位專屬女優")


if __name__ == "__main__":
    print("🔄 載入資料庫...")
    data = load_database()
    print(f"✅ 載入完成: {len(data.get('videos', {}))} 部影片, {len(data.get('actresses', {}))} 位女優\n")

    print("🔍 分析女優片商分佈...")
    results = analyze_actress_studios(data)

    # 基本摘要
    print_summary(results, min_videos=3, sort_by="studio_count")

    # 跨多片商女優
    print_multi_studio_actresses(results, min_studios=3)

    # 專屬女優
    print_single_studio_actresses(results, min_videos=5)
