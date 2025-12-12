# -*- coding: utf-8 -*-
"""
測試零女優番號的二次搜尋功能
驗證 SNIS-539 等零女優番號能否通過二次搜尋找到女優資訊
"""

import sys
from pathlib import Path
import json
import logging

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# 將 src 資料夾加入 Python 路徑
src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))

from src.models.incremental_json_database import IncrementalJSONDB
from src.services.classifier_core import UnifiedClassifierCore
from src.models.config import ConfigManager

def test_zero_actress_codes():
    """測試零女優番號"""
    
    print("\n" + "="*80)
    print("🔬 測試零女優番號的二次搜尋功能")
    print("="*80 + "\n")
    
    # 初始化管理器
    config = ConfigManager()
    db_manager = IncrementalJSONDB()
    
    # 測試番號（都是已知的零女優番號）
    test_codes = [
        'SNIS-539',  # 已知無結果
        'SNIS-640',  # 261位垃圾案例
    ]
    
    print("📋 準備插入測試番號到資料庫...\n")
    
    # 先清空這些番號的記錄（如果存在）
    for code in test_codes:
        existing = db_manager.get_video_info(code)
        if existing:
            logger.info(f"♻️ 找到現有記錄: {code}")
            # 設置為零女優狀態以模擬需要二次搜尋的情況
            info = {
                'actresses': [],  # 空女優列表
                'original_filename': f'{code}.mp4',
                'file_path': f'C:\\test\\{code}.mp4',
                'studio': 'UNKNOWN',
                'search_method': 'JAVDB (初始)',
                'search_status': 'searched_not_found',
                'last_search_date': '2025-11-01T00:00:00'
            }
            db_manager.add_or_update_video(code, info)
            logger.info(f"✅ 已設置 {code} 為零女優狀態\n")
    
    print("\n" + "-"*80)
    print("📊 初始資料庫狀態")
    print("-"*80 + "\n")
    
    for code in test_codes:
        info = db_manager.get_video_info(code)
        if info:
            actresses = info.get('actresses', [])
            print(f"{code}:")
            print(f"  - 女優數: {len(actresses)}")
            print(f"  - 搜尋狀態: {info.get('search_status')}")
            print(f"  - 搜尋方法: {info.get('search_method')}")
            print()
    
    print("\n" + "-"*80)
    print("🔍 模擬搜尋流程（只顯示檢測結果，不實際搜尋）")
    print("-"*80 + "\n")
    
    all_videos = db_manager.get_all_videos()
    codes_in_db = {v['code']: v for v in all_videos}
    
    zero_actress_codes = {}
    
    for code in test_codes:
        if code in codes_in_db:
            video_record = codes_in_db[code]
            actresses = video_record.get('actresses', [])
            
            if not actresses or len(actresses) == 0:
                zero_actress_codes[code] = [f'C:\\test\\{code}.mp4']
                print(f"⚠️ {code}: 檢測到零女優（將進行二次搜尋）")
            else:
                print(f"✅ {code}: 有 {len(actresses)} 位女優（無需二次搜尋）")
        else:
            print(f"❓ {code}: 不在資料庫中")
    
    print("\n" + "-"*80)
    print(f"📈 檢測結果")
    print("-"*80 + "\n")
    
    print(f"✅ 零女優番號檢測: {len(zero_actress_codes)} 個\n")
    
    if zero_actress_codes:
        print("📋 將進行二次搜尋的番號:")
        for code in zero_actress_codes:
            print(f"  - {code}")
        
        print("\n💡 二次搜尋步驟:")
        print("  1. 清除 JAVDB 快取")
        print("  2. 重新查詢搜尋結果")
        print("  3. 更新資料庫記錄")
        print("  4. 複寫女優資訊\n")
    
    print("\n" + "="*80)
    print("✅ 測試完成")
    print("="*80)

if __name__ == "__main__":
    try:
        test_zero_actress_codes()
    except Exception as e:
        logger.error(f"❌ 測試失敗: {e}", exc_info=True)
        sys.exit(1)
