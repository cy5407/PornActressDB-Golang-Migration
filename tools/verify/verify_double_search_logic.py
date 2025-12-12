# -*- coding: utf-8 -*-
"""
驗證零女優番號檢測邏輯 - 簡化版
"""

import sys
from pathlib import Path

# 將 src 資料夾加入 Python 路徑
src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(Path(__file__).parent))

from src.models.incremental_json_database import IncrementalJSONDB
from datetime import datetime

def verify_zero_actress_detection():
    """驗證零女優番號檢測"""
    
    print("\n" + "="*80)
    print("✅ 零女優番號檢測邏輯驗證")
    print("="*80 + "\n")
    
    # 初始化資料庫
    db_manager = IncrementalJSONDB()
    
    # 測試番號
    test_codes = [
        'SNIS-539',  # 已知無結果
        'MIDV-777',  # 應該有女優
    ]
    
    print("📊 資料庫現有番號檢查:\n")
    
    all_videos = db_manager.get_all_videos()
    codes_in_db = {v['code']: v for v in all_videos}
    
    # 追蹤分類
    zero_actress_codes = []
    normal_codes = []
    not_in_db = []
    
    for code in test_codes:
        if code not in codes_in_db:
            not_in_db.append(code)
            print(f"❓ {code}: 不在資料庫中")
        else:
            video_record = codes_in_db[code]
            actresses = video_record.get('actresses', [])
            search_status = video_record.get('search_status', 'unknown')
            
            if not actresses or len(actresses) == 0:
                zero_actress_codes.append(code)
                print(f"⚠️ {code}:")
                print(f"   - 女優數: 0 (零女優)")
                print(f"   - 搜尋狀態: {search_status}")
                print(f"   - 🔄 將進行二次搜尋")
            else:
                normal_codes.append(code)
                print(f"✅ {code}:")
                print(f"   - 女優數: {len(actresses)}")
                print(f"   - 搜尋狀態: {search_status}")
    
    print("\n" + "-"*80)
    print("📈 檢測統計")
    print("-"*80)
    print(f"\n✅ 正常番號: {len(normal_codes)} 個")
    print(f"⚠️  零女優番號（需二次搜尋）: {len(zero_actress_codes)} 個")
    print(f"❓ 不在資料庫中: {len(not_in_db)} 個")
    
    if zero_actress_codes:
        print(f"\n🔄 二次搜尋清單:")
        for code in zero_actress_codes:
            print(f"  - {code}")
            print(f"    🧹 清除快取 → 🔍 重新查詢 → ✏️  複寫資料庫")
    
    print("\n" + "-"*80)
    print("💡 二次搜尋流程說明")
    print("-"*80)
    print("""
1️⃣  偵測階段: 識別零女優番號（actresses 列表為空或長度為 0）
2️⃣  清快取: 調用 clear_cache_for_code() 清除該番號的 JAVDB 快取
3️⃣  重新查詢: 使用 batch_search() 重新搜尋
4️⃣  複寫資料庫: 
   - 如果第二輪找到女優: 更新 actresses 列表，search_status = 'searched_found'
   - 如果仍無結果: 保持 actresses 為空，search_status = 'searched_not_found'
5️⃣  記錄方法: search_method 標記為 'JAVDB (二次搜尋)'
    """)
    
    print("="*80)
    print("✅ 驗證完成\n")
    
    return len(zero_actress_codes) > 0

if __name__ == "__main__":
    try:
        has_zero = verify_zero_actress_detection()
        sys.exit(0 if has_zero else 1)
    except Exception as e:
        print(f"\n❌ 驗證失敗: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
