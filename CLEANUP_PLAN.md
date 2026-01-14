# 專案清理計劃

> 📅 建立日期：2026-01-11  
> 🎯 目標：移除未使用或重複的檔案，清理專案結構

## ✅ 確認主程式功能正常

### 測試結果
- ✅ Go 編譯通過
- ✅ Go 測試全部通過
- ✅ Go CLI 建構成功
- ⚠️  Python 測試部分失敗（test_json_statistics.py - 8個測試）
- ✅ 整合測試通過
- ✅ 主程式模組載入成功

### 核心功能模組（使用中，不刪除）
以下模組被 `run.py` → `ui/main_gui.py` 實際使用：

#### models/
- ✅ `config.py` - 設定管理
- ✅ `extractor.py` - 番號提取
- ✅ `incremental_json_database.py` - 資料庫
- ✅ `json_database.py` - JSON 資料庫管理
- ✅ `json_types.py` - 型別定義
- ✅ `studio.py` - 片商識別

#### services/
- ✅ `classifier_core.py` - 核心分類邏輯
- ✅ `web_searcher.py` - 網路搜尋
- ✅ `safe_searcher.py` - 安全搜尋器
- ✅ `safe_javdb_searcher.py` - JAVDB 搜尋
- ✅ `unified_cache.py` - 快取管理
- ✅ `interactive_classifier.py` - 互動式分類
- ✅ `studio_classifier.py` - 片商分類
- ✅ `go_bridge.py` - Go 橋接層
- ✅ `encoding_enhancer.py` - 編碼增強
- ✅ `japanese_site_enhancer.py` - 日文網站增強

#### ui/
- ✅ `main_gui.py` - 主介面
- ✅ `search_result_dialog.py` - 搜尋結果對話框
- ✅ `preferences_dialog.py` - 偏好設定
- ✅ `operation_history_dialog.py` - 操作歷史

#### utils/
- ✅ `scanner.py` - 檔案掃描
- ✅ `file_mover.py` - 檔案移動
- ✅ `json_utils.py` - JSON 工具
- ✅ `retry_utils.py` - 重試工具
- ✅ `progress_tracker.py` - 進度追蹤
- ✅ `path_setup.py` - 路徑設定

#### scrapers/
- ✅ `base_scraper.py` - 爬蟲基類
- ✅ `unified_scraper.py` - 統一爬蟲
- ✅ `sources/avwiki_scraper.py` - AV-WIKI 爬蟲
- ✅ `sources/chibaf_scraper.py` - chiba-f 爬蟲
- ✅ `sources/javdb_scraper.py` - JAVDB 爬蟲
- ✅ `enhanced/encoding_handler.py` - 編碼處理

---

## 📦 待刪除檔案分類

### 1. 過時的診斷/分析工具
這些是開發過程中的臨時工具，不影響主程式：

```
tools/analysis/
tools/diagnostics/
tools/verify/
```

### 2. 手動測試腳本
```
tools/manual_tests/
```

### 3. 重複或過時的測試檔案
```
tests/test_json_statistics.py  # 8個測試失敗，需修復或移除
```

### 4. 備份與臨時檔案
```
backups/data_backup_20251017_150802.json
backups/data.json
backups/scripts/
temp_benchmark/
```

### 5. 文件檔案夾（需評估）
```
docs/archives/  # 舊文件
my-test-project/  # 測試專案
```

### 6. 過時的 Go 測試檔案（如果有）
待確認

---

## 🗂️ 清理結構

將建立以下資料夾結構：

```
_to_delete/
├── analysis_tools/      # 分析工具
├── diagnostic_tools/    # 診斷工具
├── manual_tests/        # 手動測試
├── temp_files/          # 臨時檔案
├── old_backups/         # 舊備份
├── failed_tests/        # 失敗測試
└── outdated_docs/       # 過時文件
```

---

## ⚠️ 不刪除的項目

### 測試檔案（修復後保留）
- `tests/test_incremental_db.py` - ✅ 通過
- `tests/test_json_statistics.py` - ⚠️  需修復但不刪除

### 開發工具（有用）
- `.github/` - Agent 設定
- `tools/integration/` - 整合範例
- `tools/studio_updates/` - 片商更新工具
- `tools/fix_filenames.py` - 檔名修復工具
- `tools/fix_sys_path.py` - 路徑修復工具

### 核心程式碼
- `src/` 下所有模組（全部使用中）
- `pkg/` Go 套件
- `cmd/` Go CLI

---

## 📋 清理檢查清單

### Phase 1: 安全移動（不影響主程式）
- [ ] 移動 `tools/analysis/` 到 `_to_delete/analysis_tools/`
- [ ] 移動 `tools/diagnostics/` 到 `_to_delete/diagnostic_tools/`
- [ ] 移動 `tools/verify/` 到 `_to_delete/diagnostic_tools/`
- [ ] 移動 `tools/manual_tests/` 到 `_to_delete/manual_tests/`
- [ ] 移動 `backups/scripts/` 到 `_to_delete/old_backups/`
- [ ] 移動 `temp_benchmark/` 到 `_to_delete/temp_files/`
- [ ] 移動 `docs/archives/` 到 `_to_delete/outdated_docs/`
- [ ] 移動 `my-test-project/` 到 `_to_delete/temp_files/`

### Phase 2: 評估後移動
- [ ] 檢查 `backups/data*.json` 是否需要
- [ ] 評估 `code_usage_analysis.txt` 是否保留

### Phase 3: 測試驗證
- [ ] 移動失敗測試（修復後再決定）
  - [ ] `tests/test_json_statistics.py` 暫不移動，待修復

---

## 🚀 執行計劃

1. **建立清理腳本** - 自動化移動檔案
2. **執行測試** - 確認移動後主程式正常
3. **生成報告** - 記錄所有移動操作
4. **手動確認** - 使用者最終決定是否刪除

---

## 📊 預期效果

### 移動前
- Python 檔案：97 個
- 專案大小：~150 MB（含 cache）

### 移動後（預估）
- 保留核心檔案：~60 個
- 移到 _to_delete：~37 個檔案 + 多個資料夾
- 減少專案複雜度：~30%

---

**下一步**：建立自動化清理腳本
