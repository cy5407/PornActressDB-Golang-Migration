# Hermes Code Review — 2026-04-21

本文件整理本次以「superpowers / dead-code-audit」方式，對 PornActressDB-Golang-Migration 專案進行的靜態交叉審查結果。

審查目的有兩個：
1. 驗證先前審計清單中，哪些「可刪除 / 死碼 / fallback 殘留」判斷是正確的，哪些可能誤導刪除。
2. 在真正動手清理前，先確認常數、函式、模組是否仍被 `src/`、`tests/`、`tools/`、`integration tests` 或文件化工作流實際依賴，避免誤刪。

注意：本次是證據導向的靜態審查結論，不等同於已完成實際重構；除少數明顯無引用項目外，凡涉及公開 API、跨模組 import graph、Python ↔ Go 邊界、或工具腳本契約者，皆不應僅憑單檔閱讀就刪除。

---

## 一、審查方法

本次審查採以下原則：

- 同時搜尋 `src/`、`tests/`、`tools/`，避免把「只被 tests 呼叫」或「只被工具腳本使用」的符號誤判為死碼。
- 不只看文件敘述，也交叉查驗：
  - 直接 import / from-import
  - 實際函式呼叫點
  - integration / smoke tests
  - 工具腳本與 schema 驗證工具
- 對於「重複實作」類項目，不只比較函式內容是否相同，也檢查：
  - 模組間 import graph
  - 測試是否直接 import 該函式
  - monkeypatch / patch 路徑是否會受影響
- 對於「零風險」措辭採保守標準：
  - 只有在確認無外部引用、無公開語意變更、且不牽涉工具或測試契約時，才可稱低風險。
  - 多數清理項目最多只能稱「低風險」，不宜寫成「零風險」。

---

## 二、對先前審計結論的交叉驗證

### 1. `src/services/go_cli.py` 不是可刪殘留

此結論成立，而且證據很強。

`AGENTS.md` 已明確寫出：
- `src/services/go_cli.py` 是 Python 呼叫 `classifier.exe` 的唯一正式入口。
- 非爬蟲層的 DB、掃描、搬移、操作歷史等，都應透過 `go_cli.py` 委派給 Go CLI。

靜態交叉搜尋也證實它被多條正式執行路徑直接依賴，包括：
- `src/utils/scanner.py`
- `src/models/json_database.py`
- `src/models/incremental_json_database.py`
- `src/scrapers/cache_manager.py`
- `src/models/extractor.py`
- `src/models/studio.py`

被正式使用的 API 包含：
- `run`, `is_available`
- `db_get_video`, `db_update_video`, `db_delete_video`, `db_get_all_videos`
- `db_get_actress`, `db_update_actress`, `db_delete_actress`
- `db_backup_create`, `db_backup_list`, `db_backup_restore`, `db_backup_cleanup`
- `cache_get`, `cache_set`, `cache_delete`, `cache_prune`, `cache_get_stats`, `cache_clear`
- `extract_code`
- `identify_studio`, `normalize_studio_name`
- `GoError`, `GoNotFoundError`

另外，多組 tests 與 integration tests 也直接驗證 go_cli 契約，因此它不僅是 runtime 邊界，也已是被測試鎖定的公共 API。

結論：
- `src/services/go_cli.py` 現階段不可直接刪除。
- 若未同步重構所有呼叫端與測試，刪除它將直接破壞多條正式路徑。

### 2. `web_searcher.py` / `safe_searcher.py` / `safe_javdb_searcher.py` / `unified_cache.py` 不是可疑 fallback 殘留

此結論也成立。

`AGENTS.md` 已將 `src/services/web_searcher.py` 列入現行 Python 搜尋管線，而靜態依賴鏈進一步證實：

- `src/scrapers/run_search.py` 直接 import `WebSearcher`
- `src/scrapers/run_batch_search.py` 直接 import `WebSearcher`
- `WebSearcher` 在初始化時直接建立並使用：
  - `SafeSearcher`
  - 日文站用的 `SafeSearcher`
  - `SafeJAVDBSearcher`
  - `get_cache_manager()` / `UnifiedCacheManager`

實際鏈路可整理為：

`run_search.py` / `run_batch_search.py`
→ `WebSearcher`
→ `SafeSearcher` / `SafeJAVDBSearcher` / `UnifiedCacheManager`

具體使用包含：
- `SafeSearcher.safe_request()` 被搜尋流程與 scraper 路徑實際調用
- `SafeJAVDBSearcher.search_javdb()` 被 `WebSearcher` 直接調用
- `get_cache_manager()` 被搜尋初始化流程直接調用並註冊 cache source

tests / integration tests 亦有明確覆蓋：
- `tests/test_safe_searcher.py`
- `tests/test_safe_javdb_searcher.py`
- `tests/test_coverage_safe_javdb_searcher.py`
- `tests/test_coverage_unified_cache.py`
- `tests/test_coverage_web_searcher.py`
- 搜尋入口 smoke / subprocess 類 integration tests

結論：
- 這四個模組屬現行搜尋管線的一部分，不可視為可刪 fallback 殘留。
- 刪除任一個都會破壞現行搜尋鏈或其測試契約。

### 3. `MIGRATION_STATUS.md` 的判定要精準區分路徑

原先較粗略的說法需要修正為更精準版本。

較準確的結論是：
- **repo 根目錄的** `MIGRATION_STATUS.md`，依 `AGENTS.md` 與內容格式來看，確實是目前的「現況摘要」。
- 但 repo 內**另有** `docs/MIGRATION_STATUS.md`，那份仍保留較早期的 phase checklist / tracking，不宜與根目錄那份混稱。

因此較安全的描述是：
- 「repo 根目錄的 `MIGRATION_STATUS.md` 看起來是目前狀態摘要；`docs/MIGRATION_STATUS.md` 則仍保留較舊的 phase tracking，不應混為同一文件用途。」

### 4. `.audit_report` 類檔案的結論

針對當時那兩份本地 `.audit_report.json` / `.audit_report.txt`，本次審查支持以下結論：
- 它們內容含有明顯錯誤的可刪除判斷，例如把仍在正式路徑上的核心模組誤列為可刪。
- 因此它們不適合作為現行權威審計結論保留或提交。

但若泛化成「所有 audit_report 都不應 commit」，則屬說法過滿。

更精準的表述應為：
- 「那兩份本地 `.audit_report` 因內容包含明顯錯誤的可刪除判斷，不適合作為現行權威審計結果保留或提交。若日後要保留類似審查報告，必須清楚標示其時效、範圍、可信度與適用限制，且不能把未驗證的刪除建議當正式結論。」

---

## 三、對這次清理清單的逐項審查結果

原清單大意如下：
- 無用 import（5 處）
- 未使用常數（`json_types.py`）
- `_secure_uniform` 三份重複實作去重
- 幾個暫不動項目
- 並聲稱「純刪除死碼，不改任何邏輯，跑完測試就能確認乾淨」

本次審查結論：**不能原封不動照單全收。**

### A. 可直接修，低風險

#### 1) `src/models/config.py`
可刪：
- `json_dump`
- `json_load`

原因：
- 只在 import 行出現，未發現檔內使用。
- 未發現跨檔 import、反射、字串引用。

判定：
- 低風險，可直接刪。

#### 2) `src/utils/progress_tracker.py`
可刪：
- `builtins`
- `contextlib`

原因：
- 只在 import 行出現，未發現檔內使用。
- 未發現跨檔引用或 patch 依賴。

判定：
- 低風險，可直接刪。

#### 3) `src/scrapers/async_scraper.py`
候選可刪：
- `RateLimiter` import

原因：
- `async_scraper.py` 內實際使用的是 `get_global_rate_limiter()` 與 `self.rate_limiter`，未直接使用 `RateLimiter` 型別名。

但注意：
- 這項可視為**低風險**，不建議宣稱為「零風險」。
- 它雖像是未使用 import，但仍位於 scraper / rate limiter 公共語境中，措辭應保守。

判定：
- 低風險，可修；但文件措辭不應寫成零風險。

#### 4) `src/models/json_types.py`
可刪常數：
- `ISO_DATE_FORMAT`
- `DATA_DIR`
- `JSON_DB_FILE`
- `BACKUP_DIR`
- `ROLE_TYPES`
- `MAX_STRING_LENGTH`
- `MAX_ACTRESSES_PER_VIDEO`
- `MAX_ALIASES_PER_ACTRESS`

原因：
- 經搜尋 `src/`、`tests/`、`tools/`，未發現有效引用。
- 未發現反射、`__all__`、字串名稱路徑、patch target 依賴。

判定：
- 低風險，可直接刪。

### B. 不可照原清單刪除

#### `src/models/json_types.py::VIDEO_ALLOWED_FIELDS`
原清單將其列為未使用常數，判定錯誤。

實際引用：
- `tools/diagnostics/normalize_json_db_schema.py`
- `tools/verify/verify_json_db_schema.py`

而且是實際用於檢查 video 欄位合法性，不是單純 import 未使用。

判定：
- 不可刪。
- 不能列為零風險清理項目。

### C. 需要更多驗證，不能當作純刪除零風險

#### `_secure_uniform` 三份重複實作
定義位置：
- `src/utils/retry_utils.py`
- `src/scrapers/rate_limiter.py`
- `src/scrapers/base_scraper.py`

靜態比對結果：
- 三份函式邏輯等價，差異幾乎只有 docstring。
- 所以「存在重複實作」這件事成立。

但不能因此直接下結論說：
- 「刪掉兩份、改 import 一份，是純刪除、零風險」

原因：
- 這會改到模組 import graph。
- 現有測試有直接從模組 namespace import `_secure_uniform`。
- 此 repo 同時存在 `src.*` 與裸模組 import style，若硬收斂，可能影響載入路徑與測試 patch 相容性。

比較安全的做法若真要去重，應是：
- 以 `retry_utils.py` 保留唯一實作
- 在 `rate_limiter.py` / `base_scraper.py` 保留相容 alias / re-export
- 再跑相關測試驗證

判定：
- 中等風險，需要額外驗證。
- 不可歸類為純刪除零風險。

---

## 四、對「暫不動」項目的風險評估

### 1. `asyncio.get_event_loop()`
判定：
- 保留暫不動，合理。

原因：
- 現有 async scraper 測試綁定多種 event loop 分支語意。
- 若改寫為 `get_running_loop()`、`asyncio.run()` 或其他模式，容易改變現有 fallback 行為。

### 2. dirty tracking 空集合
判定：
- 保留暫不動，合理，且風險偏中高。

原因：
- 這不只是死碼清除，而是 Python 與 Go index / journal 契約問題。
- 若動到 dirty tracking，需一起驗證 Go CLI 與 Python 記憶體狀態的關係。

### 3. `encoding_utils.py` 的 `chardet` 路徑
判定：
- 保留暫不動，合理。

原因：
- 涉及解碼策略、confidence threshold、fallback 行為與既有測試。
- 同 repo 內還有 `web_searcher.py` 的另一套 `chardet` 使用，不能草率收斂。

### 4. `benchmark.py`
判定：
- 比原清單寫的更低風險。

原因：
- 目前看起來偏 inert stub，若只是標 deprecated、刪除或替換提示內容，風險偏低。
- 但若使用者傾向保守，也可暫時不動。

---

## 五、對原清單措辭的修正建議

原清單最大的問題，不是「方向完全錯」，而是把：
- 低風險
- 純刪除
- 零風險
- 測試可驗證

這幾種不同層次混在一起寫，導致表述過度樂觀。

### 不建議使用的說法
- 「純刪除，零風險」
- 「這份清單的所有修改都是純粹刪除死碼，不改任何邏輯，跑完測試就能確認乾淨」

### 建議改寫
更精準的版本可寫成：

1. 低風險清理
- 「已確認無外部引用、且不影響公開語意的無用 import 與未使用常數，可列為低風險清理項目。」

2. 不能稱零風險的項目
- 「凡涉及跨模組去重、公開 API 匯出、import graph 變動、或可能影響測試 import / patch 路徑者，不應稱為零風險。」

3. 關於測試
- 「跑完現有測試可提升信心，但不能單獨證明『已清理乾淨』；若涉及共享資料結構、跨層契約或工具腳本，仍需補做相應 smoke / contract / e2e 驗證。」

---

## 六、最終結論

### 可直接進入修正的項目
- `src/models/config.py`
  - 刪除 `json_dump`, `json_load`
- `src/utils/progress_tracker.py`
  - 刪除 `builtins`, `contextlib`
- `src/scrapers/async_scraper.py`
  - 刪除未使用的 `RateLimiter` import（建議標低風險，不要寫零風險）
- `src/models/json_types.py`
  - 刪除：
    - `ISO_DATE_FORMAT`
    - `DATA_DIR`
    - `JSON_DB_FILE`
    - `BACKUP_DIR`
    - `ROLE_TYPES`
    - `MAX_STRING_LENGTH`
    - `MAX_ACTRESSES_PER_VIDEO`
    - `MAX_ALIASES_PER_ACTRESS`

### 不可列入可刪清單的項目
- `src/models/json_types.py::VIDEO_ALLOWED_FIELDS`
  - 已被 `tools/diagnostics/normalize_json_db_schema.py` 與 `tools/verify/verify_json_db_schema.py` 直接依賴。

### 需要二次驗證後再動的項目
- `_secure_uniform` 三份去重
- `asyncio.get_event_loop()` 相關清理
- dirty tracking 空集合
- `encoding_utils.py` 的 `chardet` 路徑

### 關於更大方向的保守原則
- `go_cli.py` 現階段不可直接刪除。
- `web_searcher.py`、`safe_searcher.py`、`safe_javdb_searcher.py`、`unified_cache.py` 都屬現行搜尋管線的一部分，不能當作 fallback 殘留直接清理。
- 任何「疑似可刪」清單，在真正動手前都應至少依序做：
  1. 看文件定位
  2. 查 `src/` 的實際 import / 呼叫
  3. 查 `tests/` 與 `integration tests`
  4. 查 `tools/` 是否有工具腳本依賴
  5. 再決定是 live dependency、僅測試依賴，還是真死碼

---

## 七、建議後續行動

最安全的實作順序如下：

### 第一波：低風險清理
只處理這些：
- config.py 的 2 個無用 import
- progress_tracker.py 的 2 個無用 import
- async_scraper.py 的 `RateLimiter` import
- json_types.py 的 8 個未用常數（排除 `VIDEO_ALLOWED_FIELDS`）

### 第二波：中等風險項目分開驗證
- `_secure_uniform` 去重另開一波
- 先設計相容 alias / re-export 策略
- 再跑對應測試

### 第三波：保留待議題化
- `asyncio.get_event_loop`
- dirty tracking
- encoding/chardet 路徑
- benchmark.py 是否清理

---

## 八、審查結語

本次審查最重要的發現，不是「這份清單完全不能用」，而是：
- 裡面有一批可直接修的低風險項目；
- 但也混入了至少一個明顯錯誤項（`VIDEO_ALLOWED_FIELDS`），以及若干被過度樂觀描述的項目（尤其 `_secure_uniform` 去重與「零風險」措辭）。

因此，正確做法不是全盤否定，也不是直接照單全收，而是：
- 先分級
- 先做真正低風險的清理
- 把中風險項目拆開審
- 對跨模組、跨層、跨工具鏈的部分保持保守

以上結論可作為後續清理與重構前的基線參考。