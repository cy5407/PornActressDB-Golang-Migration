"""
整合測試 - 女優名字過濾器與爬蟲整合
"""

import sys
from pathlib import Path

# 加入專案根目錄到 sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.scrapers.sources.javdb_scraper import JAVDBScraper
from src.scrapers.sources.avwiki_scraper import AVWikiScraper


def test_javdb_scraper_with_filter():
    """測試 JAVDB 爬蟲整合過濾器"""
    scraper = JAVDBScraper()
    
    # 測試女優名字驗證
    valid_names = ["市瀬あいり", "清宮仁愛", "桜ゆの"]
    invalid_names = ["新人", "半裸水着学園", "つい勃起しちゃ"]
    
    print("🔍 測試 JAVDB 爬蟲名字驗證：")
    for name in valid_names:
        result = scraper._is_valid_actress_name(name)
        status = "✅" if result else "❌"
        print(f"  {status} {name}: {result}")
        assert result, f"有效名字應該通過: {name}"
    
    for name in invalid_names:
        result = scraper._is_valid_actress_name(name)
        status = "✅" if not result else "❌"
        print(f"  {status} {name}: {result}")
        assert not result, f"無效名字應該被過濾: {name}"
    
    print("\n✅ JAVDB 爬蟲整合測試通過！")


def test_avwiki_scraper_with_filter():
    """測試 AV-WIKI 爬蟲整合過濾器"""
    scraper = AVWikiScraper()
    
    # 測試女優名字驗證
    valid_names = ["神木麗", "青葉香奈", "宮下玲奈"]
    invalid_names = ["スポーツ学校を中退した青葉香", "新型媚薬でキメセク洗脳美脚ガ"]
    
    print("🔍 測試 AV-WIKI 爬蟲名字驗證：")
    for name in valid_names:
        result = scraper._is_valid_actress_name(name)
        status = "✅" if result else "❌"
        print(f"  {status} {name}: {result}")
        assert result, f"有效名字應該通過: {name}"
    
    for name in invalid_names:
        result = scraper._is_valid_actress_name(name)
        status = "✅" if not result else "❌"
        print(f"  {status} {name}: {result}")
        assert not result, f"無效名字應該被過濾: {name}"
    
    print("\n✅ AV-WIKI 爬蟲整合測試通過！")


def main():
    """執行所有整合測試"""
    print("=" * 60)
    print("女優名字過濾器整合測試")
    print("=" * 60)
    print()
    
    test_javdb_scraper_with_filter()
    print()
    test_avwiki_scraper_with_filter()
    
    print()
    print("=" * 60)
    print("🎉 所有整合測試通過！")
    print("=" * 60)


if __name__ == "__main__":
    main()
