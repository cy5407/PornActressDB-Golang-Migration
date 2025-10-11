#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
女優分類系統編碼修復測試程式
"""

import logging
import threading
import time
from pathlib import Path
import sys

# 添加模組路徑
sys.path.insert(0, str(Path(__file__).parent))

# 設定日誌
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('encoding_test.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

def test_encoding_fix():
    """測試編碼修復功能"""
    
    print("🧪 開始測試女優分類系統編碼修復...")
    print("=" * 60)
    
    try:
        # 導入必要模組
        from models.config import ConfigManager
        from src.services.web_searcher import WebSearcher
        
        # 初始化配置
        config = ConfigManager()
        
        # 創建搜尋器
        searcher = WebSearcher(config)
        
        # 測試番號列表
        test_codes = [
            "IPZZ-158",  # 常見番號
            "SSIS-123",  # S1 番號
            "MIDV-456",  # MOODYZ 番號
        ]
        
        # 停止事件
        stop_event = threading.Event()
        
        print(f"📋 測試番號: {', '.join(test_codes)}")
        print("-" * 60)
        
        # 測試每個番號
        for code in test_codes:
            print(f"\n🔍 測試番號: {code}")
            print("-" * 30)
            
            # 測試 AV-WIKI 搜尋
            print("🇯🇵 測試 AV-WIKI...")
            av_wiki_result = searcher._search_av_wiki(code, stop_event)
            
            if av_wiki_result:
                print(f"✅ AV-WIKI 成功:")
                print(f"   女優: {', '.join(av_wiki_result['actresses'])}")
                print(f"   片商: {av_wiki_result.get('studio', '未知')}")
                print(f"   來源: {av_wiki_result['source']}")
            else:
                print("❌ AV-WIKI 未找到結果")
            
            # 測試 chiba-f.net 搜尋
            print("\n🇯🇵 測試 chiba-f.net...")
            chiba_result = searcher._search_chiba_f_net(code, stop_event)
            
            if chiba_result:
                print(f"✅ chiba-f.net 成功:")
                print(f"   女優: {', '.join(chiba_result['actresses'])}")
                print(f"   片商: {chiba_result.get('studio', '未知')}")
                print(f"   來源: {chiba_result['source']}")
            else:
                print("❌ chiba-f.net 未找到結果")
            
            # 測試綜合搜尋
            print(f"\n🔍 測試綜合搜尋...")
            combined_result = searcher.search_info(code, stop_event)
            
            if combined_result:
                print(f"✅ 綜合搜尋成功:")
                print(f"   女優: {', '.join(combined_result['actresses'])}")
                print(f"   片商: {combined_result.get('studio', '未知')}")
                print(f"   來源: {combined_result['source']}")
            else:
                print("❌ 綜合搜尋未找到結果")
            
            # 延遲避免過快請求
            time.sleep(2)
        
        print("\n" + "=" * 60)
        print("🎉 編碼修復測試完成！")
        
        # 顯示統計資訊
        stats = searcher.get_all_search_stats()
        print(f"\n📊 搜尋統計:")
        print(f"   快取條目: {stats.get('local_cache_entries', 0)}")
        
    except ImportError as e:
        print(f"❌ 模組導入失敗: {e}")
        print("請確認您在正確的目錄中運行此測試")
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        logger.error(f"測試失敗: {e}", exc_info=True)

def test_encoding_detection():
    """測試編碼檢測功能"""
    
    print("\n🧪 測試編碼檢測功能...")
    print("=" * 60)
    
    try:
        from models.config import ConfigManager
        from src.services.web_searcher import WebSearcher
        import httpx
        
        config = ConfigManager()
        searcher = WebSearcher(config)
        
        # 測試不同編碼的內容
        test_content = [
            (b'\xe3\x81\x93\xe3\x82\x93\xe3\x81\xab\xe3\x81\xa1\xe3\x81\xaf', 'UTF-8'),  # "こんにちは"
            (b'\x82\xb1\x82\xf1\x82\xc9\x82\xbf\x82\xcd', 'Shift_JIS'),  # "こんにちは"
            (b'\xa4\xb3\xa4\xf3\xa4\xcb\xa4\xc1\xa4\xcf', 'EUC-JP'),  # "こんにちは"
        ]
        
        for content_bytes, expected_encoding in test_content:
            print(f"\n📄 測試編碼: {expected_encoding}")
            print(f"📄 原始位元組: {content_bytes}")
            
            # 創建模擬 response
            class MockResponse:
                def __init__(self, content):
                    self.content = content
                    self.encoding = None
            
            mock_response = MockResponse(content_bytes)
            
            # 測試編碼檢測
            try:
                decoded_text = searcher._detect_and_decode_content(mock_response)
                print(f"✅ 檢測成功: {decoded_text}")
                
                # 驗證是否為有效文字
                is_valid = searcher._is_valid_decoded_text(decoded_text)
                print(f"✅ 有效性檢驗: {'通過' if is_valid else '失敗'}")
                
            except Exception as e:
                print(f"❌ 檢測失敗: {e}")
        
        print("\n🎉 編碼檢測測試完成！")
        
    except Exception as e:
        print(f"❌ 編碼檢測測試失敗: {e}")
        logger.error(f"編碼檢測測試失敗: {e}", exc_info=True)

def main():
    """主要測試函數"""
    
    print("🚀 女優分類系統編碼修復測試程式")
    print("=" * 60)
    
    # 運行基本功能測試
    test_encoding_fix()
    
    # 運行編碼檢測測試
    test_encoding_detection()
    
    print("\n✅ 所有測試完成！")
    print("📋 請檢查 encoding_test.log 檔案以查看詳細日誌")

if __name__ == "__main__":
    main()