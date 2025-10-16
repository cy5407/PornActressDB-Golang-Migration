# SQLite 至 JSON 遷移完成檢查清單

**建立日期**: 2025-10-16  
**版本**: 1.0  
**用途**: 指導系統管理員完成從 SQLite 至 JSON 的資料庫遷移過程

---

## 📋 遷移前準備

在執行遷移前，請完成以下準備工作：

### 資料備份
- [ ] 備份現有 SQLite 資料庫: `data/actress_classifier.db`
  - 方法: `cp data/actress_classifier.db data/actress_classifier.db.backup`
  - 驗證: 確認備份檔案大小合理
  
- [ ] 記錄當前的資料統計資訊
  - 影片數量: 執行 `SELECT COUNT(*) FROM videos`
  - 女優數量: 執行 `SELECT COUNT(*) FROM actresses`
  - 關聯數量: 執行 `SELECT COUNT(*) FROM video_actress_link`

### 環境檢查
- [ ] 驗證 Python 版本 ≥ 3.8
  - 命令: `python --version`
  
- [ ] 驗證 filelock 套件已安裝
  - 命令: `pip list | grep filelock`
  - 版本要求: ≥ 3.13.0

- [ ] 確認有足夠的磁碟空間
  - 需求: SQLite 檔案大小 × 2 (原始 + JSON 副本)

- [ ] 驗證 JSON 資料目錄不存在或為空
  - 路徑: `data/json_db/`
  - 檢查: 目錄應為空或不存在

---

## 🔄 遷移執行步驟

按照以下順序執行遷移工具：

### Step 1: 執行基本遷移
```bash
python scripts/migrate_sqlite_to_json.py
```

**驗證**:
- [ ] 工具成功執行 (exit code 0)
- [ ] 看到提示: "遷移成功!"
- [ ] 檢查日誌: `migration.log` 檔案已建立
- [ ] 檢查輸出目錄: `data/json_db/data.json` 檔案已建立

**檢查日誌輸出**:
```
遷移統計: {'total_records': XXX, 'file_size_mb': X.XX, ...}
```

### Step 2: 執行遷移並驗證
```bash
python scripts/migrate_sqlite_to_json.py --validate
```

**驗證**:
- [ ] 遷移完成
- [ ] 看到驗證報告:
  ```
  ✓ 影片計數一致: N
  ✓ 女優計數一致: N
  ✓ 關聯計數一致: N
  ✓ 關聯表完整性: 所有參考均有效
  ```

### Step 3: 檢查生成的檔案

**檢查 JSON 資料目錄**:
- [ ] `data/json_db/data.json` 存在
- [ ] `data/json_db/backup/` 目錄存在並包含備份
- [ ] `data/json_db/.gitkeep` 標記檔案存在

**檢查 JSON 檔案內容** (使用 jq 或文字編輯器):
- [ ] 檔案是有效的 JSON (無語法錯誤)
- [ ] 包含 `schema_version` 欄位: `"1.0.0"`
- [ ] 包含 `videos` 陣列
- [ ] 包含 `actresses` 陣列
- [ ] 包含 `video_actress_links` 陣列
- [ ] 包含 `metadata` 物件

**命令**:
```bash
# 驗證 JSON 語法
python -c "import json; json.load(open('data/json_db/data.json'))" && echo "JSON 有效"

# 查看基本統計
python -c "
import json
with open('data/json_db/data.json') as f:
    data = json.load(f)
    print(f'影片: {len(data[\"videos\"])}')
    print(f'女優: {len(data[\"actresses\"])}')
    print(f'關聯: {len(data[\"video_actress_links\"])}')
"
```

---

## ✅ 遷移後驗證

### 資料完整性檢查

- [ ] 比對記錄計數
  - SQLite 影片數 vs JSON 影片數 (應相同)
  - SQLite 女優數 vs JSON 女優數 (應相同)
  - SQLite 關聯數 vs JSON 關聯數 (應相同)

- [ ] 驗證資料樣本
  - 隨機選擇 5 部影片，確認所有欄位都已遷移
  - 隨機選擇 5 位女優，確認所有欄位都已遷移
  - 確認日期格式為 ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)

### 系統功能測試

**啟動應用程式**:
- [ ] 應用程式成功啟動 (無 SQLite 相關錯誤)
- [ ] GUI 介面正常顯示
- [ ] 沒有 "資料庫連接失敗" 之類的錯誤訊息

**測試基本功能**:
- [ ] 搜尋功能正常工作
  - 搜尋已知的影片名稱
  - 搜尋已知的女優名稱
  - 驗證搜尋結果與 SQLite 時期一致

- [ ] 分類功能正常工作
  - 執行一次分類操作
  - 驗證分類結果儲存到 JSON 資料庫
  - 確認新增的記錄在查詢時可見

- [ ] 統計功能正常工作
  - 查看女優統計
  - 查看片商統計
  - 驗證統計數字正確

**測試資料修改**:
- [ ] 能夠新增新影片 (JSON 資料庫應可寫入)
- [ ] 能夠新增新女優
- [ ] 能夠修改現有記錄
- [ ] 修改後的資料被正確儲存和檢索

### 備份驗證

- [ ] 初始備份已建立: `data/json_db/backup/backup_*.json`
- [ ] 備份檔案大小合理 (應接近原始 data.json)
- [ ] 備份檔案可以手動恢復

**恢復測試** (可選):
```bash
# 1. 刪除 data.json
rm data/json_db/data.json

# 2. 從備份恢復
python -c "
from src.models.json_database import JSONDBManager
db = JSONDBManager('data/json_db')
db.restore_from_backup('data/json_db/backup/backup_YYYY-MM-DD_HH-MM-SS.json')
"

# 3. 驗證資料恢復
python -c "
from src.models.json_database import JSONDBManager
db = JSONDBManager('data/json_db')
print(f'影片數: {len(db.get_all_videos())}')
print(f'女優數: {len(db.get_all_actresses())}')
"
```

---

## 🧹 清理步驟 (可選)

遷移成功並經過充分測試後，可以執行以下清理步驟：

### 備份舊資料庫

- [ ] 將原始 SQLite 資料庫移至歸檔位置
  ```bash
  mkdir -p archive/database
  mv data/actress_classifier.db archive/database/actress_classifier.db.$(date +%Y%m%d)
  ```

- [ ] 或刪除 SQLite 資料庫 (確認已備份!)
  ```bash
  rm data/actress_classifier.db
  ```

### 清理代碼

- [ ] 確認應用程式已完全移除對 SQLiteDBManager 的依賴
- [ ] 驗證所有服務層都使用 JSONDBManager
- [ ] 移除不再使用的 SQLite 相關程式碼 (可選，見 T032)

### 更新文件

- [ ] 更新 README.md: 移除 SQLite 相關說明
- [ ] 更新配置指南: 改為 JSON 資料庫說明
- [ ] 更新部署文件: 修改安裝步驟

---

## 🆘 故障排除

### 常見問題

**Q: 遷移工具提示 "SQLite 檔案不存在"**
- A: 檢查 SQLite 檔案路徑是否正確
- 預設路徑: `data/actress_classifier.db`
- 使用 `--sqlite-path` 選項指定自訂路徑

**Q: 遷移失敗，提示編碼錯誤**
- A: SQLite 資料庫可能包含非 UTF-8 字元
- 遷移工具會自動移除非法字元
- 檢查 `migration.log` 了解移除了哪些字元

**Q: JSON 檔案過大**
- A: 這是正常的，JSON 格式比 SQLite 二進制格式更冗長
- 通常 JSON 檔案是 SQLite 的 1-2 倍大小
- 如果大小超過 3 倍，請檢查資料完整性

**Q: 驗證失敗，提示記錄計數不一致**
- A: 可能原因:
  1. 遷移過程中資料被修改
  2. SQLite 資料庫已損壞
  3. 遷移工具錯誤
- 解決步驟:
  1. 檢查 `migration.log` 的詳細錯誤信息
  2. 從備份恢復並重試
  3. 聯繫技術支援

**Q: 應用程式啟動失敗，提示 "無法初始化 JSONDBManager"**
- A: 可能原因:
  1. JSON 資料目錄不存在
  2. data.json 檔案損壞
  3. 權限問題
- 解決步驟:
  1. 確認 `data/json_db/` 目錄存在
  2. 執行 `python scripts/migrate_sqlite_to_json.py --validate`
  3. 檢查檔案和目錄權限

---

## 📊 遷移總結範本

遷移完成後，請填寫以下資訊作為記錄：

```
遷移日期: _______________
執行人: _______________

遷移前統計:
- SQLite 影片數: _______________
- SQLite 女優數: _______________
- SQLite 檔案大小: _______________

遷移後統計:
- JSON 影片數: _______________
- JSON 女優數: _______________
- JSON 檔案大小: _______________

遷移耗時: _______________

驗證結果:
- 記錄計數驗證: [ ] 通過 [ ] 失敗
- 關聯表驗證: [ ] 通過 [ ] 失敗
- 系統功能測試: [ ] 通過 [ ] 失敗
- 備份恢復測試: [ ] 通過 [ ] 未執行

備註:
_______________________________________________________________
_______________________________________________________________
```

---

## ✅ 完成確認

請在完成所有步驟後，簽署此檢查清單：

**迴圈 1: 遷移準備** - 完成日期: ___________
- 初始人簽名: ___________________

**迴圈 2: 遷移執行** - 完成日期: ___________
- 執行人簽名: ___________________

**迴圈 3: 遷移驗證** - 完成日期: ___________
- 驗收人簽名: ___________________

**迴圈 4: 清理完成** - 完成日期: ___________
- 確認人簽名: ___________________

---

**備註**: 此檢查清單可作為系統遷移的官方記錄。建議以印製版本保存，並與備份檔案一起存檔。

**最後更新**: 2025-10-16  
**文件版本**: 1.0
