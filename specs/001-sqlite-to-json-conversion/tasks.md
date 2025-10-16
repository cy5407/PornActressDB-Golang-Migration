# Implementation Tasks: SQLite 轉換為 JSON 資料庫儲存

**Feature Branch**: `001-sqlite-to-json-conversion`  
**Tasks Created**: 2025-10-16  
**Status**: Ready for Implementation

---

## Overview

本文件包含完整的任務清單，按使用者故事組織，支援獨立並行實施。

**總任務數**: 32 tasks  
**故事數**: 4 (US1-US4)  
**預計時程**: 40-60 小時

---

## Task Organization

### Phase Structure

```
Phase 1: Setup (共享基礎設施)
  └─ T001-T003: 專案初始化

Phase 2: Foundational (阻塞性先決條件)
  └─ T004-T007: JSONDBManager 核心框架

Phase 3: [Story US1-P1] 資料庫平滑遷移
  └─ T008-T015: 遷移工具和驗證

Phase 4: [Story US2-P2] 完全使用 JSON
  └─ T016-T021: 業務邏輯適配

Phase 5: [Story US3-P2] 複雜查詢等價
  └─ T022-T027: 統計查詢實作

Phase 6: [Story US4-P3] 並行存取
  └─ T028-T030: 並行安全性

Phase 7: Polish & Integration
  └─ T031-T032: 最終驗證和清理
```

---

## Phase 1: Setup (共享基礎設施)

### Phase Goal
建立專案基礎設施和依賴環境。

### Checkpoint
依賴安裝完成，目錄結構建立。

---

**T001** - 安裝 filelock 依賴套件 [P] ✅
- **檔案**: `requirements.txt`
- **操作**:
  1. 在 requirements.txt 新增: `filelock>=3.13.0` ✅
  2. 執行 `pip install -r requirements.txt` ✅
  3. 驗證: `python -c "import filelock; print(filelock.__version__)"` ✅
- **驗證**: filelock 3.18.0 成功安裝 ✅

---

**T002** - 建立 JSON 資料目錄結構 [P] ✅
- **檔案**: `data/json_db/`, `data/json_db/backup/`
- **操作**:
  1. 建立 `data/json_db` 目錄 ✅
  2. 建立 `data/json_db/backup` 子目錄 ✅
  3. 建立 `data/json_db/.gitkeep` 標記檔案 ✅
- **驗證**: 目錄結構完整，可寫入 ✅

---

**T003** - 建立型別定義和常數檔案 [P] ✅
- **檔案**: `src/models/json_types.py`
- **操作**:
  1. 建立檔案定義 JSON 資料結構的 TypedDict: ✅
     - VideoDict: 影片資料結構 ✅
     - ActressDict: 女優資料結構 ✅
     - LinkDict: 關聯資料結構 ✅
     - StatisticsDict: 統計快取結構 ✅
  2. 定義常數: `SCHEMA_VERSION`, `SEARCH_STATUSES`, 等 ✅ (20+ 常數)
  3. 定義例外類別: `JSONDatabaseError`, `ValidationError`, `LockError` 等 ✅ (6 個例外)
- **驗證**: 型別定義完整，可在其他模組導入 ✅

---

## Phase 2: Foundational (阻塞性先決條件)

### Phase Goal
實作 JSONDBManager 核心框架和驗證層。這些任務必須在任何故事之前完成。

### Checkpoint
JSONDBManager 框架完成，驗證機制可用。

---

**T004** - JSONDBManager 基礎類別框架 [Story: Foundational] ✅
- **檔案**: `src/models/json_database.py` (新檔案)
- **操作**:
  1. 建立 `JSONDBManager` 類別，包含: ✅
     - `__init__(data_dir: str)` - 初始化，建立鎖和快取 ✅
     - `_ensure_data_file_exists()` - 確保 JSON 檔案存在 ✅
     - `_load_all_data()` - 從磁碟載入，含驗證 ✅
     - `_save_all_data(data)` - 原子寫入磁碟，含備份 ✅
     - 屬性: `self.data_file`, `self.backup_dir`, `self.data`, `self.write_lock`, `self.read_lock` ✅
  2. 實作基本的錯誤處理和日誌 ✅
- **驗證**: 類別可實例化，鎖和目錄初始化成功 ✅

---

**T005** - 多層資料驗證層實作 [Story: Foundational]
- **檔案**: `src/models/json_database.py` (同檔案, 新增方法)
- **操作**:
  1. 實作驗證方法:
     - `_validate_json_format()` - JSON 語法檢查
     - `_validate_structure()` - 必需鍵檢查
     - `_validate_referential_integrity()` - 外鍵約束
     - `_validate_consistency()` - 統計快取一致性
     - `validate_data()` - 全面驗證，傳回結果
  2. 驗證失敗時記錄詳細錯誤
- **驗證**: 驗證方法能正確偵測和報告問題

---

**T006** - 備份和恢復機制實作 [Story: Foundational]
- **檔案**: `src/models/json_database.py` (同檔案, 新增方法)
- **操作**:
  1. 實作備份方法:
     - `create_backup()` - 建立時間戳備份
     - `restore_from_backup(backup_path)` - 還原備份
     - `get_backup_list()` - 列出可用備份
     - `cleanup_old_backups(days=30, max_count=50)` - 清理舊備份
  2. 建立 `BACKUP_MANIFEST.json` 追蹤備份
- **驗證**: 備份可建立和還原，MANIFEST 正確更新

---

**T007** - 並行鎖定機制實作 [Story: Foundational]
- **檔案**: `src/models/json_database.py` (同檔案, 新增方法)
- **操作**:
  1. 使用 filelock 實作:
     - `_acquire_read_lock(timeout=5)` - 共享鎖
     - `_acquire_write_lock(timeout=10)` - 獨佔鎖
     - `_release_locks()` - 釋放鎖
  2. 實作上下文管理器支援 `with` 語句
  3. 實作鎖定超時和錯誤處理
- **驗證**: 鎖定機制正常工作，無死鎖

---

## Phase 3: [Story US1-P1] 資料庫平滑遷移

### User Story
系統管理員希望將現有 SQLite 資料庫無損地轉換至 JSON 檔案儲存格式，同時保持所有功能可用。

### Independent Test Criteria
1. 遷移工具可執行並驗證數據完整性後，系統應能使用新的 JSON 資料庫繼續運作
2. 遷移完成後，所有記錄應完整轉移至 JSON 檔案且資料無損
3. 系統查詢影片資訊應返回與 SQLite 相同的結果

### Checkpoint: [US1-Checkpoint]
遷移工具完成並驗證成功，所有資料無損轉移。

---

**T008** - 遷移工具主函式實作 [Story: US1] [P] ✅
- **檔案**: `scripts/migrate_sqlite_to_json.py` (新檔案)
- **操作**:
  1. 建立遷移指令行工具 ✅
  2. 實作 `export_sqlite_to_json()` 函式: ✅
     - 連接 SQLite 資料庫 ✅
     - 讀取所有 videos, actresses, video_actress_links ✅
     - 計算資料統計 ✅
  3. 驗證記錄計數和資料型別 ✅
  4. 輸出遷移報告 (記錄數、處理時間等) ✅
- **驗證**: 工具可執行，生成遷移報告 ✅
- **實施日期**: 2025-10-16
- **提交**: (待提交)

---

**T009** - SQLite 至 JSON 資料轉換邏輯 [Story: US1] [P] ✅
- **檔案**: `scripts/migrate_sqlite_to_json.py` (同檔案)
- **操作**:
  1. 實作資料轉換函式: ✅
     - `convert_sqlite_data_to_json()` - 轉換格式 ✅
     - `handle_datetime_conversion()` - TIMESTAMP 轉 ISO 8601 ✅
     - `build_json_structure()` - 建構 JSON 檔案格式 ✅
  2. 處理特殊情況: NULL 值、日期、編碼 ✅
  3. 驗證轉換後的資料完整性 ✅
- **驗證**: 轉換後 JSON 結構正確，資料無遺失 ✅
- **實施日期**: 2025-10-16
- **提交**: (待提交)

---

**T010** - JSONDBManager 基礎 CRUD 方法實作 [Story: US1] [P] ✅
- **檔案**: `src/models/json_database.py`
- **操作**:
  1. 實作方法:
     - `add_or_update_video(video_info)` - 新增或更新影片 ✅
     - `get_video_info(video_id)` - 查詢影片 ✅
     - `get_all_videos(filter_dict=None)` - 取得影片清單 ✅
     - `delete_video(video_id)` - 刪除影片 ✅
     - `add_or_update_actress(actress_info)` - 新增/更新女優 ✅
     - `get_actress_info(actress_id)` - 查詢女優 ✅
     - `delete_actress(actress_id)` - 刪除女優 ✅
     - `_apply_video_filters()` - 過濾輔助方法 ✅
  2. 所有方法支援並行鎖定 ✅
  3. 修改後自動更新 `updated_at` 時間戳 ✅
- **驗證**: CRUD 操作正常，資料持久化 ✅
- **實施日期**: 2025-10-16
- **提交**: 2d6cacb

---

**T011** - 遷移資料寫入與驗證 [Story: US1]
- **檔案**: `scripts/migrate_sqlite_to_json.py` (同檔案)
- **操作**:
  1. 實作 `write_json_database()`:
     - 建立 JSONDBManager 實例
     - 寫入轉換後的資料
     - 建立初始備份
     - 驗證寫入成功
  2. 錯誤恢復: 若寫入失敗則還原
- **驗證**: JSON 檔案正確建立，內容可讀取

---

**T012** - 遷移驗證工具實作 [Story: US1] [P]
- **檔案**: `scripts/migrate_sqlite_to_json.py` (同檔案)
- **操作**:
  1. 實作 `validate_migration()` 函式:
     - 對比 SQLite 和 JSON 的記錄計數
     - 驗證每筆記錄的完整性
     - 計算資料雜湊並對比
     - 驗證關聯表完整性
  2. 生成詳細的驗證報告
- **驗證**: 驗證報告完整，所有檢查通過

---

**T013** - 遷移日誌和進度追蹤 [Story: US1] [P]
- **檔案**: `scripts/migrate_sqlite_to_json.py` (同檔案)
- **操作**:
  1. 使用 Python `logging` 模組
  2. 記錄:
     - 遷移開始/結束時間
     - 處理的記錄數量
     - 任何警告或錯誤
     - 驗證結果
  3. 日誌級別: DEBUG, INFO, WARNING, ERROR
  4. 所有日誌消息使用繁體中文
- **驗證**: 日誌輸出完整且可讀

---

**T014** - 遷移工具命令行介面 [Story: US1] [P]
- **檔案**: `scripts/migrate_sqlite_to_json.py` (同檔案)
- **操作**:
  1. 使用 argparse 實作 CLI:
     - `--sqlite-path`: SQLite 檔案路徑 (預設: data/actress_classifier.db)
     - `--json-dir`: JSON 輸出目錄 (預設: data/json_db)
     - `--backup`: 是否建立備份 (預設: true)
     - `--validate`: 遷移後驗證 (預設: true)
  2. 支援 `--help` 和版本資訊
- **驗證**: CLI 介面可用，幫助文本完整

---

**T015** - 遷移完成檢查清單 [Story: US1]
- **檔案**: `docs/migration_checklist.md`
- **操作**:
  1. 建立檢查清單文件，包含:
     - 遷移前準備 (備份 SQLite, 驗證資料)
     - 執行遷移步驟
     - 遷移後驗證 (記錄計數, 查詢測試)
     - 系統測試 (功能完整性)
     - 清理步驟 (可選移除 SQLite)
- **驗證**: 文件完整，可作為操作指南

---

## Phase 4: [Story US2-P2] 完全使用 JSON

### User Story
系統完全遷移至 JSON 資料庫後，所有組件均應使用新的 JSON 儲存層，無 SQLite 相依性。

### Independent Test Criteria
1. SQLite 已完全遷移至 JSON，刪除 SQLiteDBManager 程式碼後，系統仍能正常啟動和運作
2. 系統執行所有業務功能時無任何 SQLite 相依性錯誤
3. 舊的 SQLite 檔案存在時，系統應完全忽略並使用 JSON

### Checkpoint: [US2-Checkpoint]
SQLiteDBManager 完全替換為 JSONDBManager，無相依性。

---

**T016** - 更新 classifier_core.py 使用 JSONDBManager [Story: US2]
- **檔案**: `src/services/classifier_core.py`
- **操作**:
  1. 替換:
     ```python
     # 舊
     from src.models.database import SQLiteDBManager
     self.db_manager = SQLiteDBManager(...)
     
     # 新
     from src.models.json_database import JSONDBManager
     self.db_manager = JSONDBManager(...)
     ```
  2. 驗證所有 db_manager 呼叫相同 (介面相容)
  3. 更新初始化邏輯: 移除 SQLite 路徑配置
- **驗證**: 檔案編譯正常，無 import 錯誤

---

**T017** - 更新其他服務層適配 [Story: US2] [P]
- **檔案**: `src/services/studio_classifier.py`, `src/services/interactive_classifier.py`
- **操作**:
  1. 在兩個檔案中替換:
     - 導入: SQLiteDBManager → JSONDBManager
     - 初始化參數傳遞
  2. 驗證介面相容性
- **驗證**: 檔案編譯正常

---

**T018** - 更新 main_gui.py 移除 SQLite 配置 [Story: US2]
- **檔案**: `src/ui/main_gui.py`
- **操作**:
  1. 移除:
     - SQLite 路徑選擇對話框
     - 資料庫類型設定選項
     - 相關配置讀取邏輯
  2. 硬編碼 JSON 資料目錄: `data/json_db`
  3. 更新初始化為 JSONDBManager
- **驗證**: GUI 啟動正常，無配置警告

---

**T019** - 更新 preferences_dialog.py 簡化設定 [Story: US2]
- **檔案**: `src/ui/preferences_dialog.py`
- **操作**:
  1. 移除資料庫相關設定 UI
  2. 移除相應的獲取/設定方法
  3. 如無其他設定，可簡化對話框
- **驗證**: 對話框啟動正常

---

**T020** - 更新 cache_manager.py [Story: US2] [P]
- **檔案**: `src/scrapers/cache_manager.py`
- **操作**:
  1. 移除 SQLite 索引層:
     - 刪除 `CREATE TABLE cache_index` 邏輯
     - 刪除 sqlite3 連接程式碼
  2. 改用 JSON 搜尋快取 (已存在)
  3. 驗證快取機制仍正常工作
- **驗證**: 快取操作正常，無 SQLite 相依性

---

**T021** - 更新配置檔案和文件 [Story: US2] [P]
- **檔案**: `config.ini`, `README.md`, `docs/configuration.md`
- **操作**:
  1. 在 config.ini 中:
     - 移除 `[database]` 的 `type` 和 `database_path` 設定
     - 新增 `json_data_dir` 預設設定
  2. 在 README.md 中更新:
     - 資料庫層說明改為 JSON 儲存
     - 移除 SQLite 相關內容
  3. 更新其他文件參考
- **驗證**: 配置檔案有效，文件一致

---

## Phase 5: [Story US3-P2] 複雜查詢等價

### User Story
業務分析師執行統計查詢時，JSON 資料庫應返回與 SQLite 相同的結果集。

### Independent Test Criteria
1. 女優統計查詢結果完全相同 (計數、名單)
2. 片商統計查詢結果完全相同
3. 交叉統計 (女優-片商) 結果完全相同

### Checkpoint: [US3-Checkpoint]
所有複雜查詢實作完成，結果與 SQLite 等價。

---

**T022** - 女優統計查詢實作 [Story: US3]
- **檔案**: `src/models/json_database.py`
- **操作**:
  1. 實作 `get_actress_statistics()` 方法:
     - 遍歷所有女優
     - 手動 JOIN: actress → video_actress_links → videos
     - 計算每位女優的出演部數
     - 計算最新發行日期、片商清單等
  2. 結果格式與 SQLite 版本相同
  3. 支援篩選和排序
- **驗證**: 查詢結果與 SQLite 對比相同

---

**T023** - 片商統計查詢實作 [Story: US3]
- **檔案**: `src/models/json_database.py`
- **操作**:
  1. 實作 `get_studio_statistics()` 方法:
     - 遍歷所有影片按片商分組
     - 計算每間片商的影片數
     - 計算女優數、日期範圍等
  2. 支援日期範圍篩選
- **驗證**: 查詢結果與 SQLite 對比相同

---

**T024** - 交叉統計查詢實作 [Story: US3]
- **檔案**: `src/models/json_database.py`
- **操作**:
  1. 實作 `get_enhanced_actress_studio_statistics()` 方法:
     - 遍歷關聯表
     - 建立 (actress_id, studio) 組合計數
     - 支援多維聚合
  2. 結果格式與 SQLite 版本相同
- **驗證**: 查詢結果與 SQLite 對比相同

---

**T025** - 統計查詢快取層實作 [Story: US3]
- **檔案**: `src/models/json_database.py`
- **操作**:
  1. 實作快取機制:
     - `_compute_statistics()` - 計算統計
     - `_cache_statistics()` - 快取結果
     - `get_cached_statistics()` - 獲取快取
  2. 快取失效策略: 新增/修改影片時重新計算
  3. 支援手動重新整理快取
- **驗證**: 快取正常更新，性能改善

---

**T026** - 查詢等價性驗證測試 [Story: US3]
- **檔案**: `scripts/verify_query_equivalence.py` (新檔案)
- **操作**:
  1. 建立驗證工具:
     - 連接 SQLite 和 JSON 資料庫
     - 執行相同查詢
     - 對比結果
  2. 驗證項目:
     - 女優統計
     - 片商統計
     - 交叉統計
     - 邊界情況
  3. 生成對比報告
- **驗證**: 報告顯示 100% 等價

---

**T027** - 複雜查詢完成檢查清單 [Story: US3]
- **檔案**: `docs/query_equivalence.md`
- **操作**:
  1. 建立查詢對應表:
     - SQLite SQL → JSON 實作映射
     - 每個查詢的性能特性
  2. 記錄已驗證的測試用例
- **驗證**: 文件完整

---

## Phase 6: [Story US4-P3] 並行存取

### User Story
多個程式同時讀寫資料庫時，JSON 資料庫應確保資料一致性。

### Independent Test Criteria
1. 5 個並發進程同時讀寫時無資料損壞或損失
2. 讀操作在寫操作進行時無阻塞
3. 寫操作之間正確序列化

### Checkpoint: [US4-Checkpoint]
並行安全性驗證通過，無資料競爭。

---

**T028** - 並行存取測試工具 [Story: US4]
- **檔案**: `tests/test_concurrent_access.py` (新檔案)
- **操作**:
  1. 建立測試套件:
     - 多執行緒讀取測試
     - 多執行緒寫入測試
     - 讀寫並行測試
  2. 壓力測試: 100+ 並發操作
  3. 驗證資料一致性 (記錄計數、雜湊)
- **驗證**: 所有測試通過，無競爭條件

---

**T029** - 資料損壞恢復測試 [Story: US4]
- **檔案**: `tests/test_data_recovery.py` (新檔案)
- **操作**:
  1. 模擬資料損壞:
     - JSON 語法錯誤
     - 遺失關鍵欄位
     - 不一致的統計快取
  2. 驗證恢復機制:
     - 自動修復
     - 備份還原
  3. 驗證還原後資料完整性
- **驗證**: 所有損壞情況都能恢復

---

**T030** - 並行性能基準測試 [Story: US4] [P]
- **檔案**: `tests/test_performance_benchmarks.py` (新檔案)
- **操作**:
  1. 建立效能基準:
     - 單執行緒讀取: 目標 <5ms
     - 單執行緒寫入: 目標 <100ms
     - 並行讀取 (5 執行緒): 目標 <10ms 每個
     - 記憶體使用: 目標 <100MB (150 筆記錄)
  2. 記錄基準結果
- **驗證**: 效能在可接受範圍內

---

## Phase 7: Polish & Integration

### Phase Goal
最終驗證、清理和部署準備。

### Checkpoint
系統完全遷移完成，所有測試通過。

---

**T031** - 完全系統集成測試 [P]
- **檔案**: `tests/test_integration_full.py` (新檔案)
- **操作**:
  1. 端到端流程測試:
     - 執行遷移工具
     - 啟動系統
     - 執行所有主要業務流程
     - 驗證結果
  2. 測試覆蓋:
     - 影片新增和查詢
     - 統計查詢
     - 並行操作
  3. 驗證日誌輸出
- **驗證**: 系統功能完整

---

**T032** - 清理 SQLite 相關程式碼和文件 [P]
- **檔案**: `src/models/database.py`, 文件
- **操作**:
  1. 最終檢查: 
     - 確認 SQLite 無任何相依性
     - 掃描程式碼中的 "sqlite" 字樣
  2. 建立遷移報告: `MIGRATION_REPORT.md`
  3. 驗證所有測試通過 (≥70% 覆蓋)
- **驗證**: 完全移除 SQLite，只保留 JSON

---

## Dependencies Graph

```
Phase 1 (Setup)
  ↓
Phase 2 (Foundational) ← 必須完成
  ↓
├─→ Phase 3 (US1) ──┐
├─→ Phase 4 (US2) ──┤
├─→ Phase 5 (US3) ──┼→ Phase 7 (Integration)
└─→ Phase 6 (US4) ──┘

並行機會:
- US1, US2, US3, US4 可部分並行 (都依賴 Phase 2)
- 但 US2 需 US1 遷移完成才能驗證
- US3 可與 US2 並行
- US4 測試可與 US3 並行
```

---

## Parallel Execution Examples

### Example 1: 快速路徑 (2 周)
```
第 1 周:
- 並行: T001-T003 (Setup)
- 並行: T004-T007 (Foundational)
- 並行: T008-T015 (US1 - 遷移)

第 2 周:
- 並行: T016-T021 (US2 - 適配)
- 並行: T022-T027 (US3 - 查詢)
- 並行: T028-T030 (US4 - 並行)
- 最後: T031-T032 (Integration)
```

### Example 2: 穩健路徑 (3 周)
```
第 1 周:
- T001-T003 (Setup)
- T004-T007 (Foundational)

第 2 周:
- T008-T015 (US1 - 遷移完整測試)

第 3 周:
- 並行: T016-T021, T022-T027, T028-T030
- 最後: T031-T032
```

---

## Implementation Strategy

### MVP Scope
**最小可行產品**: US1 完成
- 成功標準: 資料無損遷移，驗證通過
- 時程: 1 週

### Incremental Delivery
1. **Phase 1** (1 天): 基礎設施
2. **Phase 2** (1-2 天): 核心框架
3. **Phase 3** (2-3 天): 遷移 (可作為 MVP)
4. **Phase 4** (1-2 天): 業務邏輯適配
5. **Phase 5** (1-2 天): 複雜查詢
6. **Phase 6** (1 天): 並行測試
7. **Phase 7** (1 天): 整合驗證

### Quality Gates

每個階段完成前:
- ✅ 所有任務代碼完成
- ✅ 方法論文件齊全
- ✅ 日誌輸出使用繁體中文
- ✅ 無 SQL 引用 (若適用)

最終:
- ✅ 程式碼覆蓋率 ≥70%
- ✅ 並行安全性驗證通過
- ✅ 查詢等價性 100% 
- ✅ 文件完整和一致

---

## Task Reference by Story

### US1 (P1) - 資料庫平滑遷移
- T008, T009, T010, T011, T012, T013, T014, T015
- 小計: 8 tasks

### US2 (P2) - 完全使用 JSON  
- T016, T017, T018, T019, T020, T021
- 小計: 6 tasks

### US3 (P2) - 複雜查詢等價
- T022, T023, T024, T025, T026, T027
- 小計: 6 tasks

### US4 (P3) - 並行存取
- T028, T029, T030
- 小計: 3 tasks

### Setup & Foundational
- T001-T007
- 小計: 7 tasks

### Integration & Polish
- T031, T032
- 小計: 2 tasks

**總計: 32 tasks**

---

## Next Steps

1. ✅ 任務清單已建立
2. 📋 選擇並行或順序執行路徑
3. 🚀 開始 Phase 1 (Setup)
4. 📊 追蹤進度，更新完成狀態

建議: 從 **MVP 路徑** 開始，先完成 US1，驗證遷移成功後再進行後續階段。

