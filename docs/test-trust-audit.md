# 測試可信度盤點（Test Trust Audit）

> 更新時間：2026-04-11  
> 目的：區分「真實驗證」與「coverage 補點」，避免只看 passed 數量或 coverage 百分比就誤判品質。

---

## 核心原則

測試的價值不只在於：

- 有多少個 `passed`
- coverage 是多少 `%`

更重要的是：

- 這些測試是否真的驗證**真實程式行為**
- 是否會真的打到 `classifier(.exe)` / subprocess / 檔案系統 / 真實資料流
- 還是只是用 mock / monkeypatch 補分支、補 coverage

本文件將現有測試分為以下幾類：

- **A 級**：真實整合驗證，可信度高
- **A- 級**：接近真實驗證，但範圍較窄
- **B 級**：模組邏輯 / contract 測試，有價值但不能替代整合驗證
- **B- 級**：coverage 補點，但 mock 較少，仍有補強價值
- **C 級**：coverage 補點且 mock 比例高，應視為補強，不應當成主要品質保證

---

## A 級：真實整合驗證

### `tests/integration/test_db_cli_contract.py`
**定位**：真實 CLI 契約驗證  
**原因**：
- 直接執行 `classifier.exe`
- 驗證 `db merge -source ... -data-dir ...` 真實行為
- 不是只測 Python wrapper 組參數

**評語**：
- 這類測試最有價值，因為它能驗證 Python / Go / 檔案輸出之間的真實鏈路
- 建議保留並逐步擴充

### `tests/integration/test_go_cli_smoke.py`
**定位**：真實 Go CLI smoke / integration test  
**原因**：
- 真實執行 `classifier(.exe)`
- 驗證 `go_cli` wrapper 到真實 CLI 的路徑
- 已涵蓋：
  - `extract_code`
  - `identify_studio`
  - `cache_set/get/delete/stats`
  - `db stats`

**評語**：
- 這類測試是目前最值得擴充的方向之一
- 可以逐步補成 `go_cli` 的真實 smoke 套件，而不是只靠 mock contract test

---

## A- 級：接近真實驗證，但範圍較窄

### `tests/test_ci_workflows.py`
**定位**：靜態品質驗證  
**原因**：
- 不屬於整合測試
- 但直接檢查 workflow 內容本身，而不是純 mock 邏輯

**評語**：
- 雖然不是 runtime integration，但對避免 CI 配置回歸有實際價值

---

## B 級：模組邏輯 / contract 測試（有價值，但不是最終真驗證）

### 代表檔案
- `tests/test_extractor.py`
- `tests/test_studio.py`
- `tests/test_json_database.py`
- `tests/test_safe_searcher.py`
- `tests/test_safe_javdb_searcher.py`
- `tests/test_scanner_integration.py`
- `tests/test_split_search_entrypoints.py`
- `tests/test_go_cli_contracts.py`
- `tests/test_batch_d_services_core.py`
- `tests/test_actress_name_filter.py`
- `tests/test_avwiki_scraper.py`
- `tests/test_javdb_scraper.py`
- `tests/test_incremental_db.py`
- `tests/test_integration_actress_filter.py`
- `tests/test_json_utils.py`
- `tests/test_log_sanitizer.py`
- `tests/test_shiroutowiki_scraper.py`
- `tests/test_code_review_regressions.py`
- `tests/test_go_only_cleanup.py`
- `tests/test_sonar_quick_wins.py`

### 共同特徵
- 驗證模組邏輯、邊界條件、資料結構或 wrapper 契約
- 有些包含 `monkeypatch` / `patch` / `AsyncMock`
- 有助於防回歸，但通常不是整條真實執行鏈

### 特別說明

#### `tests/test_go_cli_contracts.py`
**價值**：高  
**限制**：
- 多數測試是 mock `subprocess.run`
- 它回答的是：Python wrapper 有沒有把命令、參數、錯誤處理寫對
- 它**不能單獨保證**真實 `classifier.exe` 一定正確

**結論**：
- 應與 `tests/integration/test_go_cli_smoke.py` 一起看，兩者互補

#### `tests/test_scanner_integration.py`
**注意點**：
- 檔名雖然叫 integration，但內容較偏 `UnifiedFileScanner` 層的行為驗證
- 並非大比例直接打到真實 `classifier.exe`

**結論**：
- 不是低價值測試
- 但不能因為檔名叫 integration 就把它視為 A 級真整合驗證

#### `tests/test_json_database.py`
**價值**：中高  
**原因**：
- 雖然非 A 級，但測到了資料結構、schema 正規化、CRUD 路徑
- 對資料層回歸保護有實際幫助

---

## B- 級：coverage 補點，但 mock 較少

### 代表檔案
- `tests/test_coverage_actress_name_filter.py`
- `tests/test_coverage_progress_tracker.py`
- `tests/test_coverage_web_searcher.py`

### 評語
- 這類測試不該被當成「主驗收依據」
- 但如果它測到的是純邏輯邊界，仍然有補強價值
- 可以視為：
  - 補 branch
  - 補回歸保護
  - 但不是最終真實行為保證

---

## C 級：coverage 補點且 mock 比例高

### 代表檔案
- `tests/test_coverage_async_scraper.py`
- `tests/test_coverage_cache_manager.py`
- `tests/test_coverage_encoding_utils.py`
- `tests/test_coverage_json_utils.py`
- `tests/test_coverage_rate_limiter.py`
- `tests/test_coverage_retry_utils.py`
- `tests/test_coverage_scanner.py`
- `tests/test_coverage_unified_cache.py`

### 評語
- 這類測試不是沒用
- 但應被明確標示為：
  - **coverage 補強**
  - **分支保護**
  - **不是主要品質保證來源**

### 使用規則
- 可以留
- 可以擴充
- 但不要因為這些測試全綠，就認為整體功能鏈已被驗證

---

## 目前結論

### 現況摘要
- 現有測試數量不少
- 但 **A 級真實整合驗證比例偏少**
- 大量測試仍屬 B / B- / C 類
- 因此不能只看：
  - `568 passed`
  - `coverage 73%`
  來判斷系統整體很安全

### 真正該怎麼看
應分三層看：

1. **真實驗證層**
   - integration / subprocess / CLI / 打包後測試
2. **模組保護層**
   - unit / regression / contract
3. **coverage 補強層**
   - `test_coverage_*`

只有三層一起看，品質判讀才不會失真。

---

## 接下來的建議方向

### 1. 優先擴充 A 級測試
建議持續補：
- `tests/integration/test_go_cli_smoke.py`
- `tests/integration/test_db_cli_contract.py`
- 新增：
  - `run_search.py` 真實 subprocess smoke
  - `run_batch_search.py` 真實 subprocess smoke

### 2. 保留 B 級測試，但不要誤用
- `test_go_cli_contracts.py`、`test_json_database.py` 等仍值得保留
- 但應明確知道它們測的是 wrapper / 模組 / contract，而不是整條實際鏈路

### 3. 把 C 級視為補強而非主驗收
- `tests/test_coverage_*` 應被當成 coverage 與邊界補強
- 不應單獨作為品質結論

---

## 一句話版結論

**目前測試很多，但真整合驗證比例仍偏少；coverage 與 passed 數量可以當輔助訊號，不能直接當最終品質保證。**
