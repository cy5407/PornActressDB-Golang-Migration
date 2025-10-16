# 資料庫配置說明

**最後更新**: 2025-10-17
**資料庫類型**: JSON 檔案型資料庫

---

## 📊 資料庫檔案位置

### 主要資料庫
- **路徑**: `data/json_db/data.json`
- **類型**: JSON 檔案型資料庫
- **狀態**: ✅ 正常運作
- **備份目錄**: `data/json_db/backup/`

### 舊版資料庫 (已遷移)
- **路徑**: `C:\Users\cy540\Documents\ActressClassifier\actress_database.db`
- **類型**: SQLite 資料庫
- **狀態**: 已遷移至 JSON 格式,保留作為備份

## 🔧 資料庫配置

### 預設設定 (config.ini)
```ini
[database]
json_data_dir = data/json_db
```

### 資料庫結構
```
data/json_db/
├── data.json           # 主要資料檔案
├── db.lock            # 檔案鎖定 (自動產生)
└── backup/            # 自動備份目錄
    └── backup_*.json  # 時間戳備份檔案
```

## 🎯 JSON 資料庫優勢

### 為何選擇 JSON 格式?
1. **零依賴**: 無需額外安裝 SQLite 或其他資料庫軟體
2. **輕量級**: 適合個人使用場景 (<10,000 筆記錄)
3. **易於備份**: 單一 JSON 檔案,方便複製和遷移
4. **人類可讀**: 可直接用文字編輯器查看和編輯
5. **跨平台**: 純文字格式,完全跨平台相容

### .gitignore 設定
```ignore
# JSON 資料庫
data/json_db/data.json
data/json_db/db.lock
data/json_db/backup/*.json

# 舊版 SQLite 資料庫
*.db
*.sqlite
*.sqlite3
```

### 設計原因
1. **隱私保護**: 資料庫包含使用者個人分類資料
2. **檔案大小**: 避免 git 儲存庫過大
3. **安全考量**: 防止意外提交敏感資訊
4. **使用者資料**: 每個使用者應有自己的資料庫

## 📋 資料庫檔案清單

### 主要檔案
- `data/json_db/data.json` - 主要 JSON 資料庫檔案
- `data/json_db/db.lock` - 檔案鎖定標記 (自動產生)
- `data/json_db/backup/backup_*.json` - 自動備份檔案

### JSON 資料結構
```json
{
  "schema_version": "1.0.0",
  "videos": {
    "video_id": {
      "id": "video_id",
      "title": "影片標題",
      "studio": "片商名稱",
      "studio_code": "片商代碼",
      "release_date": "2023-01-15",
      "actresses": ["actress_id_1", "actress_id_2"]
    }
  },
  "actresses": {
    "actress_id": {
      "id": "actress_id",
      "name": "女優名稱",
      "video_count": 5
    }
  },
  "links": [
    {
      "video_id": "video_id",
      "actress_id": "actress_id",
      "role_type": "主演",
      "timestamp": "2023-01-15T00:00:00Z"
    }
  ],
  "statistics": {},
  "metadata": {
    "version": "1.0.0",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-12-31T23:59:59Z"
  }
}
```

### 歷史檔案 (已淘汰)
- `actress_database.db` - 舊版 SQLite 資料庫
- `片商重新分類批次檔案.sql` - SQLite SQL 查詢
- `查看女優的影片數量.sql` - SQLite SQL 查詢
- `查看片商分布.sql` - SQLite SQL 查詢
- `actress_database.sqbpro` - SQLite 專案檔案

## ✅ 如何確認資料庫正常

1. **檢查檔案存在**:
   ```bash
   # Windows PowerShell
   Test-Path "data\json_db\data.json"

   # Linux/macOS
   test -f data/json_db/data.json && echo "存在"
   ```

2. **檢查 JSON 格式有效性**:
   ```python
   import json
   with open('data/json_db/data.json', 'r', encoding='utf-8') as f:
       data = json.load(f)
       print(f"✅ JSON 格式有效")
       print(f"影片數: {len(data['videos'])}")
       print(f"女優數: {len(data['actresses'])}")
   ```

3. **程式中驗證**:
   ```python
   from src.models.json_database import JSONDBManager

   db = JSONDBManager('data/json_db')
   validation = db.validate_data()

   if validation['valid']:
       print("✅ 資料庫驗證通過")
   else:
       print(f"❌ 驗證失敗: {validation['errors']}")
   ```

4. **執行統計查詢測試**:
   ```python
   from src.models.json_database import JSONDBManager

   db = JSONDBManager('data/json_db')

   # 女優統計
   actress_stats = db.get_actress_statistics()
   print(f"女優統計: {len(actress_stats)} 位")

   # 片商統計
   studio_stats = db.get_studio_statistics()
   print(f"片商統計: {len(studio_stats)} 間")
   ```

## 🔄 如果需要恢復資料庫

### 從備份恢復
```python
from src.models.json_database import JSONDBManager

db = JSONDBManager('data/json_db')

# 列出可用備份
backups = db.get_backup_list()
print("可用備份:", backups)

# 恢復最新備份
if backups:
    latest_backup = backups[-1]
    db.restore_from_backup(latest_backup)
    print(f"✅ 已恢復備份: {latest_backup}")
```

### 建立新資料庫
```python
# 程式會自動建立新的空 JSON 資料庫
from src.models.json_database import JSONDBManager

db = JSONDBManager('data/json_db')  # 自動建立 data.json
print("✅ 新資料庫已建立")
```

### 從 SQLite 遷移
```bash
# 使用遷移工具從 SQLite 轉換
python scripts/migrate_sqlite_to_json.py \
  --sqlite-path "C:\Users\{USERNAME}\Documents\ActressClassifier\actress_database.db" \
  --output-dir "data/json_db" \
  --validate
```

## 📱 最佳實務

### 備份管理
1. **自動備份**: 系統在重要操作前自動建立備份
2. **手動備份**: 定期複製 `data.json` 到安全位置
3. **備份清理**: 使用 `cleanup_old_backups()` 清理舊備份
   ```python
   db = JSONDBManager('data/json_db')
   deleted = db.cleanup_old_backups(days=30, max_count=50)
   print(f"清理了 {deleted} 個舊備份")
   ```

### 並行存取
1. **讀操作**: 支援多執行緒同時讀取
2. **寫操作**: 自動獲取獨佔鎖,確保資料一致性
3. **鎖定超時**: 預設 10 秒,可在 `json_types.py` 調整

### 效能最佳化
1. **資料大小**: 適合 <10,000 筆記錄的場景
2. **快取策略**: 資料載入至記憶體,查詢快速
3. **批次操作**: 大量寫入時考慮批次處理

### 安全性
1. **隱私保護**: 資料庫檔案不提交到 Git
2. **權限控制**: 確保檔案權限正確設定
3. **資料驗證**: 每次寫入前驗證資料完整性

## ⚠️ 注意事項

### 資料庫位置
- JSON 資料庫位於專案目錄 `data/json_db/`
- Git 儲存庫只包含程式碼,不包含使用者資料
- 每次啟動程式會自動檢查並建立資料庫

### 遷移說明
- 舊版 SQLite 資料庫可使用遷移工具轉換
- 遷移後建議保留 SQLite 作為備份
- 詳見 [遷移檢查清單](./migration_checklist.md)

### 效能考量
- JSON 資料庫適合小型個人使用
- 若資料量 >10,000 筆,考慮使用 SQLite
- 查詢效能約為 SQLite 的 1.6-2.7 倍

### 常見問題
1. **檔案鎖定錯誤**: 確認無其他程序正在存取資料庫
2. **JSON 解析失敗**: 檢查檔案是否損壞,考慮從備份恢復
3. **記憶體使用高**: 大型資料庫會佔用較多記憶體

## 📚 相關文檔

- [查詢等效性文檔](./query_equivalence.md) - SQLite 至 JSON 查詢對應
- [遷移檢查清單](./migration_checklist.md) - 完整的遷移指南
- [JSON 資料庫 API](../src/models/json_database.py) - 完整的 API 文檔
