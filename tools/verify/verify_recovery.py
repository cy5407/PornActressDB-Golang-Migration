"""
驗證先前失敗番號的修復結果
測試 50 個先前無法找到女優的番號
"""

import asyncio
import logging
import sys
from pathlib import Path

# 設定日誌
logging.basicConfig(
    level=logging.WARNING, format="%(levelname)s - %(name)s - %(message)s"
)

src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(Path(__file__).parent))


async def test_failed_codes_recovery():
    """測試先前失敗的番號是否現已恢復"""
    from src.scrapers.sources.avwiki_scraper import AVWikiScraper

    print("\n" + "=" * 80)
    print("🧪 驗證先前失敗番號的修復結果")
    print("=" * 80 + "\n")

    scraper = AVWikiScraper()

    # 從用戶提供的警告日誌中提取的失敗番號
    failed_codes = [
        "FSDSS-180",
        "SNIS-515",
        "STARS-814",
        "SONE-709",
        "EBWH-118",
        "SSIS-592",
        "ABP-698",
        "MIDV-905",
        "MDTM-793",
        "EBWH-111",
        "SSIS-625",
        "SSIS-820",
        "ABP-835",
        "CAWD-437",
        "START-193",
        "SNIS-589",
        "SSIS-324",
        "SSIS-808",
        "STARS-818",
        "MVSD-615",
        "STARS-918",
        "STARS-859",
        "CAWD-773",
        "FSDSS-931",
        "MIDV-676",
        "START-018",
        "ABF-137",
        "SONE-324",
        "SONE-982",
        "MIDV-742",
        "ABF-133",
        "MIDV-743",
        "SSIS-535",
        "SSIS-617",
        "SONE-040",
        "MIDA-348",
        "SQTE-416",
        "EBWH-138",
        "SONE-238",
        "MIDV-747",
        "SNIS-939",
        "SONE-114",
        "ABP-592",
        "SONE-065",
        "ADN-593",
        "FSDSS-855",
        "STARS-727",
        "STARS-734",
        "SONE-544",
        "SNIS-731",
    ]

    print(f"📋 將測試 {len(failed_codes)} 個先前失敗的番號\n")

    success_count = 0
    failed_count = 0
    results = {"success": [], "failed": []}

    for i, code in enumerate(failed_codes, 1):
        try:
            result = await scraper.search_video(code)
            actresses = result.get("actresses", [])

            if actresses:
                success_count += 1
                results["success"].append((code, len(actresses), actresses[:2]))
                print(
                    f"✅ [{i:2d}] {code}: {len(actresses):2d} 位女優 - {actresses[0]}",
                    end="",
                )
                if len(actresses) > 1:
                    print(f", {actresses[1]}", end="")
                print()
            else:
                failed_count += 1
                results["failed"].append(code)
                print(f"❌ [{i:2d}] {code}: 0 位女優")
        except Exception:
            failed_count += 1
            results["failed"].append(code)
            print(f"❌ [{i:2d}] {code}: 搜尋失敗")

    # 統計和總結
    print("\n" + "=" * 80)
    print("📊 測試結果統計")
    print("=" * 80)
    print(f"\n總測試: {len(failed_codes)} 個番號")
    print(
        f"✅ 成功恢復: {success_count} 個 ({success_count / len(failed_codes) * 100:.1f}%)"
    )
    print(
        f"❌ 仍然失敗: {failed_count} 個 ({failed_count / len(failed_codes) * 100:.1f}%)"
    )

    if success_count > 0:
        print("\n🎉 成功恢復的番號範例:")
        for code, count, actresses in results["success"][:5]:
            print(f"  • {code}: {', '.join(actresses)}")

    if failed_count > 0 and failed_count <= 10:
        print("\n⚠️ 仍然失敗的番號:")
        for code in results["failed"]:
            print(f"  • {code}")

    print("\n" + "=" * 80)
    if success_count / len(failed_codes) >= 0.95:
        print("✅ 修復成功率達 95% 以上，系統恢復正常")
    elif success_count / len(failed_codes) >= 0.80:
        print("⚠️ 修復成功率達 80% 以上，基本恢復")
    else:
        print("❌ 修復成功率不足，需要進一步調查")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(test_failed_codes_recovery())
    except Exception as e:
        print(f"\n❌ 測試出錯: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
