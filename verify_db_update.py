#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""驗證資料庫更新是否成功"""

import sqlite3
from pathlib import Path

db_path = Path('data/actress_classifier.db')

if db_path.exists():
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # 獲取資料表欄位
        cursor.execute("PRAGMA table_info(videos)")
        columns = cursor.fetchall()
        
        print("=" * 60)
        print("📊 Videos 資料表欄位信息:")
        print("=" * 60)
        
        col_names = []
        for row in columns:
            col_id, col_name, col_type, not_null, default_val, pk = row
            col_names.append(col_name)
            print(f"  {col_name:20s} | 類型: {col_type:15s} | Default: {default_val}")
        
        print("\n" + "=" * 60)
        print(f"✅ 總共 {len(col_names)} 個欄位")
        print("=" * 60)
        
        # 檢查新欄位
        print("\n🔍 檢查新欄位:")
        if 'search_status' in col_names:
            print("  ✅ search_status 欄位已存在")
        else:
            print("  ❌ search_status 欄位缺失")
        
        if 'last_search_date' in col_names:
            print("  ✅ last_search_date 欄位已存在")
        else:
            print("  ❌ last_search_date 欄位缺失")
        
        # 檢查索引
        print("\n📇 已建立的索引:")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='videos'")
        indexes = cursor.fetchall()
        for idx in indexes:
            print(f"  - {idx[0]}")
        
        conn.close()
        print("\n✅ 資料庫驗證完成")
        
    except Exception as e:
        print(f"❌ 驗證失敗: {e}")
else:
    print(f"❌ 資料庫檔案不存在: {db_path}")
