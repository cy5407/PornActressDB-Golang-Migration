# 資料庫配置說明

## 📊 資料庫檔案位置

### 主要資料庫
- **路徑**: `C:\Users\cy540\Documents\ActressClassifier\actress_database.db`
- **大小**: 159KB (截至 2025-06-18 01:32)
- **狀態**: ✅ 正常運作
- **備份**: 有多個自動備份檔案

### 測試資料庫
- **路徑**: `./data/test_database.db`
- **大小**: 45KB
- **用途**: 開發測試用途

## 🔧 資料庫配置

### 預設設定 (config.py)
```python
db_path = Path.home() / "Documents" / "ActressClassifier" / "actress_database.db"
```

### 實際路徑
```
C:\Users\cy540\Documents\ActressClassifier\actress_database.db
```

## 🚫 為什麼資料庫不在 Git 中

### .gitignore 設定
```ignore
# 資料庫
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
- `actress_database.db` - 主要資料庫 (159KB)
- `actress_database.db.*.bak` - 自動備份檔案

### SQL 查詢檔案
- `片商重新分類批次檔案.sql`
- `查看女優的影片數量.sql`
- `查看片商分布.sql`
- `查看所有影片和對應女優.sql`

### 歷史檔案
- `unified_actress_database.json` - 舊版 JSON 格式資料
- `actress_database.sqbpro` - 資料庫專案檔案

## ✅ 如何確認資料庫正常

1. **檢查檔案存在**:
   ```powershell
   Test-Path "C:\Users\cy540\Documents\ActressClassifier\actress_database.db"
   ```

2. **檢查檔案大小**:
   ```powershell
   Get-Item "C:\Users\cy540\Documents\ActressClassifier\actress_database.db" | Select-Object Length
   ```

3. **程式中驗證**:
   - 啟動 run.py
   - 檢查日誌中的資料庫連接訊息

## 🔄 如果需要恢復資料庫

### 從備份恢復
```powershell
Copy-Item "C:\Users\cy540\Documents\ActressClassifier\actress_database.db.20250616_001539.bak" "C:\Users\cy540\Documents\ActressClassifier\actress_database.db"
```

### 建立新資料庫
程式會自動建立新的空資料庫檔案

## 📱 最佳實務

1. **定期備份**: 系統已自動建立備份檔案
2. **隱私保護**: 資料庫檔案不應提交到公開 git 儲存庫
3. **路徑管理**: 使用設定檔管理資料庫路徑
4. **測試分離**: 使用獨立的測試資料庫

## ⚠️ 注意事項

- 主要資料庫在使用者目錄中，不會遺失
- Git 儲存庫只包含程式碼，不包含使用者資料
- 每次啟動程式會自動檢查並建立資料庫連接
- 如果資料庫檔案遺失，程式會自動建立新的空資料庫
