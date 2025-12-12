"""
診斷 AV-WIKI 爬蟲問題 - 測試具體番號
"""

import asyncio
import sys
from pathlib import Path

src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(Path(__file__).parent))


async def test_avwiki_search():
    """測試 AV-WIKI 搜尋"""
    from src.scrapers.sources.avwiki_scraper import AVWIKIScraper

    print("\n" + "=" * 80)
    print("🔍 診斷 AV-WIKI 爬蟲問題")
    print("=" * 80 + "\n")

    scraper = AVWIKIScraper()

    # 測試近期失敗的番號
    test_codes = [
        "FSDSS-180",  # 失敗
        "SNIS-515",  # 失敗
        "STARS-814",  # 失敗
        "MIDV-222",  # 之前成功，現在失敗
    ]

    for code in test_codes:
        print(f"📝 測試番號: {code}")
        try:
            result = await scraper.search_video(code)
            actresses = result.get("actresses", [])
            print(f"  ✅ 找到 {len(actresses)} 位女優")
            if actresses:
                for actress in actresses[:3]:
                    print(f"     - {actress}")
                if len(actresses) > 3:
                    print(f"     ... 及其他 {len(actresses) - 3} 位")
            print()
        except Exception as e:
            print(f"  ❌ 搜尋失敗: {e}\n")


if __name__ == "__main__":
    try:
        asyncio.run(test_avwiki_search())
    except Exception as e:
        print(f"❌ 測試出錯: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
