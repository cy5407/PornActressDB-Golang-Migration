#!/usr/bin/env python3
"""
完整測試所有之前失敗的番號
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
os.chdir(Path(__file__).parent)

try:
    from scrapers.sources.avwiki_scraper import AVWikiScraper
except ImportError:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "avwiki_scraper",
        Path(__file__).parent / "src" / "scrapers" / "sources" / "avwiki_scraper.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    AVWikiScraper = module.AVWikiScraper

# 所有之前失敗的番號
TEST_VIDEO_CODES = [
    "SSIS-688",
    "MIDE-989",
    "AVOP-004",
    "MIDV-727",
    "STARS-685",
    "ROYD-080",
    "ABP-601",
    "SSIS-964",
    "SSIS-589",
    "SSIS-337",
    "STARS-627",
    "ABP-563",
    "MIDV-873",
    "SONE-995",
    "LUXU-457",
    "STARS-818",
    "ABP-733",
    "MIAA-582",
    "ADN-616",
    "MIDV-577",
    "IPZZ-294",
    "MIDV-361",
    "SONE-040",
    "HMN-128",
    "ABF-159",
    "MIDV-116",
    "UMD-844",
    "STARS-866",
]


async def test_all_codes():
    """測試所有番號"""
    scraper = AVWikiScraper()

    success_count = 0
    failure_count = 0

    print("=" * 70)
    print("完整 AV-WIKI 女優提取測試")
    print("=" * 70)
    print()

    results = []
    for i, code in enumerate(TEST_VIDEO_CODES, 1):
        print(f"[{i:2d}/{len(TEST_VIDEO_CODES)}] {code:12s}", end=" ")
        sys.stdout.flush()

        try:
            result = await scraper.search_video(code)
            actresses = result.get("actresses", [])

            if actresses:
                print(
                    f"✓ {len(actresses)} 位 ({', '.join(actresses[:2])}{'...' if len(actresses) > 2 else ''})"
                )
                success_count += 1
                results.append((code, len(actresses), actresses, True))
            else:
                print("✗ 無女優資訊")
                failure_count += 1
                results.append((code, 0, [], False))
        except Exception as e:
            print(f"✗ 錯誤: {str(e)[:40]}")
            failure_count += 1
            results.append((code, -1, str(e), False))

    print()
    print("=" * 70)
    print("統計結果")
    print("=" * 70)
    print(f"總計: {len(TEST_VIDEO_CODES)} 個番號")
    print(
        f"成功: {success_count} 個 ({success_count / len(TEST_VIDEO_CODES) * 100:.1f}%)"
    )
    print(
        f"失敗: {failure_count} 個 ({failure_count / len(TEST_VIDEO_CODES) * 100:.1f}%)"
    )
    print()

    # 分別列出成功和失敗
    print("成功的番號:")
    for code, count, actresses, success in results:
        if success:
            print(f"  ✓ {code}: {count} 位")

    print()
    print("失敗的番號:")
    for code, count, actresses, success in results:
        if not success:
            print(f"  ✗ {code}")


if __name__ == "__main__":
    asyncio.run(test_all_codes())
