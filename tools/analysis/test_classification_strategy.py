#!/usr/bin/env python
"""
測試三層分類策略

驗證 analyze_actress_primary_studio 的新邏輯是否正確運作
"""

import sys
from pathlib import Path

# 加入專案根目錄到 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.models.json_database import JSONDBManager


def main():
    """測試三層分類策略"""
    print("🧪 測試三層分類策略")
    print("=" * 70)

    # 初始化資料庫
    db = JSONDBManager("data/json_db")

    # 定義大片商集合（與 studio_classifier.py 一致）
    major_studios = {
        "S1", "SOD", "MOODYZ", "PRESTIGE", "FALENO", "E-BODY",
        "MADONNA", "KAWAII", "ATTACKERS", "PREMIUM", "OPPAI",
        "FITCH", "WANZ", "IdeaPocket", "kira☆kira",
    }

    # 測試案例（根據實際資料庫數據調整）
    test_cases = [
        # (女優名, 預期分類類型, 預期推薦, 說明)
        ("山手梨愛", "exclusive", "studio_classification", "專屬 S1 女優"),
        ("石川澪", "exclusive", "studio_classification", "專屬 MOODYZ（資料庫中只有 MOODYZ）"),
        ("水卜さくら", "high_loyalty", "studio_classification", "MOODYZ 高忠誠度"),
        ("あけみみう", "multi_studio", "solo_artist", "跨多片商"),
        ("鳳みゆ", "multi_studio", "solo_artist", "跨多片商"),
        ("設楽ゆうひ", "high_loyalty", "studio_classification", "KAWAII 高忠誠度"),
        ("高橋しょう子", "high_loyalty", "studio_classification", "MOODYZ 高忠誠度"),
    ]

    passed = 0
    failed = 0

    for actress, expected_type, expected_rec, description in test_cases:
        result = db.analyze_actress_primary_studio(actress, major_studios)

        actual_type = result.get("classification_type", "unknown")
        actual_rec = result.get("recommendation", "unknown")
        studio = result.get("primary_studio", "UNKNOWN")
        confidence = result.get("confidence", 0)
        studio_count = result.get("studio_count", 0)

        # 檢查結果
        type_match = actual_type == expected_type
        rec_match = actual_rec == expected_rec

        if type_match and rec_match:
            status = "✅ PASS"
            passed += 1
        else:
            status = "❌ FAIL"
            failed += 1

        print(f"\n{status} {actress} ({description})")
        print(f"   片商: {studio} ({confidence}%), {studio_count} 個片商")
        print(f"   分類類型: {actual_type} (預期: {expected_type})")
        print(f"   推薦: {actual_rec} (預期: {expected_rec})")

    print("\n" + "=" * 70)
    print(f"📊 測試結果: {passed} 通過, {failed} 失敗")

    # 額外統計：各分類類型分佈
    print("\n" + "=" * 70)
    print("📈 全資料庫分類類型分佈統計")
    print("-" * 70)

    # 取得所有女優
    actresses = db.data.get("actresses", {})
    type_stats = {
        "exclusive": 0,
        "high_loyalty": 0,
        "multi_studio": 0,
        "standard": 0,
        "no_data": 0,
    }
    rec_stats = {
        "studio_classification": 0,
        "solo_artist": 0,
    }

    for actress_name in actresses.keys():
        result = db.analyze_actress_primary_studio(actress_name, major_studios)
        ctype = result.get("classification_type", "unknown")
        rec = result.get("recommendation", "unknown")

        if ctype in type_stats:
            type_stats[ctype] += 1
        if rec in rec_stats:
            rec_stats[rec] += 1

    total = sum(type_stats.values())
    print("\n分類類型:")
    for ctype, count in sorted(type_stats.items(), key=lambda x: -x[1]):
        pct = (count / total * 100) if total > 0 else 0
        print(f"   {ctype:15s}: {count:4d} ({pct:5.1f}%)")

    print("\n推薦分佈:")
    for rec, count in sorted(rec_stats.items(), key=lambda x: -x[1]):
        pct = (count / total * 100) if total > 0 else 0
        print(f"   {rec:20s}: {count:4d} ({pct:5.1f}%)")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
