"""
批量測試先前失敗的番號（排除網路故障）
"""

import asyncio
import sys
from pathlib import Path

src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))


async def batch_test():
    from src.scrapers.sources.avwiki_scraper import AVWikiScraper

    scraper = AVWikiScraper()

    # 測試一批先前失敗的番號（排除容易超時的）
    codes = [
        "FSDSS-180",  # ✓
        "STARS-814",  # ✓
        "SONE-709",  # ✓
        "EBWH-118",  # ✓
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
    ]

    print("\n" + "=" * 60)
    print("批量測試先前失敗的番號")
    print("=" * 60 + "\n")

    success = 0
    failed = 0

    for code in codes:
        try:
            result = await scraper.search_video(code)
            actresses = result.get("actresses", [])

            if actresses:
                status = "✓"
                success += 1
            else:
                status = "✗"
                failed += 1

            count = len(actresses)
            print(f"{status} {code}: {count:2d} 位女優")
        except Exception:
            print(f"✗ {code}: 連線失敗")
            failed += 1

    print("\n" + "=" * 60)
    print(f"成功: {success} | 失敗: {failed}")
    print(f"成功率: {success / (success + failed) * 100:.1f}%")
    print("=" * 60 + "\n")


asyncio.run(batch_test())
