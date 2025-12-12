#!/usr/bin/env python3
"""
測試 AV-WIKI 女優提取功能
用於驗證最近的 HTML 提取邏輯修復
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加 src 到路徑
sys.path.insert(0, str(Path(__file__).parent / "src"))
os.chdir(Path(__file__).parent)

try:
    from scrapers.sources.avwiki_scraper import AVWikiScraper
except ImportError:
    # 備選：直接加載模組
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "avwiki_scraper",
        Path(__file__).parent / "src" / "scrapers" / "sources" / "avwiki_scraper.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    AVWikiScraper = module.AVWikiScraper

# 測試番號（這些出現了「未找到女優資訊」的警告）
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
]


async def test_actress_extraction():
    """測試女優提取"""
    scraper = AVWikiScraper()

    success_count = 0
    failure_count = 0
    results = []

    print("=" * 60)
    print("AV-WIKI 女優提取測試")
    print("=" * 60)
    print()

    for code in TEST_VIDEO_CODES:
        try:
            print(f"正在測試: {code}...", end=" ")
            result = await scraper.search_video(code)

            actresses = result.get("actresses", [])
            if actresses:
                print(f"✓ 成功找到 {len(actresses)} 位女優")
                for actress in actresses:
                    print(f"  - {actress}")
                success_count += 1
                results.append((code, len(actresses), actresses))
            else:
                print("✗ 未找到女優")
                failure_count += 1
                results.append((code, 0, []))
        except Exception as e:
            print(f"✗ 錯誤: {e}")
            failure_count += 1
            results.append((code, -1, str(e)))

        print()

    print("=" * 60)
    print("測試結果摘要")
    print("=" * 60)
    print(f"成功: {success_count}/{len(TEST_VIDEO_CODES)}")
    print(f"失敗: {failure_count}/{len(TEST_VIDEO_CODES)}")
    print(f"成功率: {success_count / len(TEST_VIDEO_CODES) * 100:.1f}%")
    print()

    # 詳細結果
    print("詳細結果:")
    for code, count, actresses in results:
        if isinstance(actresses, str):
            print(f"  {code}: 錯誤 - {actresses}")
        else:
            status = "✓" if count > 0 else "✗"
            actress_str = ", ".join(actresses) if actresses else "無"
            print(f"  {status} {code}: {count} 位 ({actress_str})")


if __name__ == "__main__":
    asyncio.run(test_actress_extraction())
