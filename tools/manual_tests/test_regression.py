#!/usr/bin/env python3
"""
回歸測試：確保之前成功的番號仍然正常工作
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

# 之前成功的番號
REGRESSION_TEST_CODES = [
    "FSDSS-180",
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
]


async def test_regression():
    """回歸測試"""
    scraper = AVWikiScraper()

    print("=" * 70)
    print("回歸測試: 確保修復不會破壞既有功能")
    print("=" * 70)
    print()

    success_count = 0
    failure_count = 0
    results = []

    for i, code in enumerate(REGRESSION_TEST_CODES, 1):
        print(f"[{i:2d}/{len(REGRESSION_TEST_CODES)}] {code:12s}", end=" ")
        sys.stdout.flush()

        try:
            result = await scraper.search_video(code)
            actresses = result.get("actresses", [])

            if actresses:
                print(f"✓ {len(actresses)} 位")
                success_count += 1
                results.append((code, len(actresses), True))
            else:
                print("✗ 無女優資訊")
                failure_count += 1
                results.append((code, 0, False))
        except Exception as e:
            print(f"✗ 錯誤: {str(e)[:30]}")
            failure_count += 1
            results.append((code, -1, False))

    print()
    print("=" * 70)
    print("回歸測試結果")
    print("=" * 70)
    print(
        f"成功: {success_count}/{len(REGRESSION_TEST_CODES)} ({success_count / len(REGRESSION_TEST_CODES) * 100:.1f}%)"
    )
    print(
        f"失敗: {failure_count}/{len(REGRESSION_TEST_CODES)} ({failure_count / len(REGRESSION_TEST_CODES) * 100:.1f}%)"
    )

    if failure_count == 0:
        print("✅ 全部通過！沒有回歸問題")
    else:
        print("⚠️  警告：有回歸問題")
        print()
        print("失敗的番號:")
        for code, count, success in results:
            if not success:
                print(f"  ✗ {code}")


if __name__ == "__main__":
    asyncio.run(test_regression())
