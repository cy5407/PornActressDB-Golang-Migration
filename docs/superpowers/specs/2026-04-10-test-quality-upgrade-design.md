# 測試品質提升設計規格

## 背景

目前專案中有一批為了提升覆蓋率而新增的測試。它們並非全部無效，但部分測試過度依賴 `mock`、`MagicMock`、`lambda` 替身或錯誤的平台假設，導致測試主要驗證「回傳值搬運」或「控制流程表面分支」，而不是驗證真正功能契約。

這份規格的目標，是把這批低效測試重構為以**本地真實樣本**為主的高價值測試，同時保留少量必要的 mock，僅用於隔離不可控邊界，例如 `sleep`、時間與少數外部依賴。

## 目標

1. 移除或重寫只驗證 mock 回傳值搬運的低效測試。
2. 讓搜尋、快取、批次處理與 safefile 路徑測試盡量跑到真實邏輯。
3. 以本地 fixture 驅動測試，避免直接依賴外網。
4. 明確區分：
   - 驗證業務規則的必要 mock
   - 為了撐 coverage 而存在的無效 mock
5. 在不破壞既有可重現性的前提下，提升測試對真 bug 的捕捉能力。

## 非目標

1. 不把測試改成大量直接打外網的整合測試。
2. 不做與本次低效測試無關的大規模 production refactor。
3. 不追求覆蓋率數字本身；優先追求測試保護力。

## 範圍

### 優先重構的測試檔

1. `tests\test_coverage_cache_manager.py`
2. `tests\test_coverage_web_searcher.py`
3. `tests\test_coverage_unified_cache.py`
4. `tests\test_coverage_async_scraper.py`
5. `pkg\safefile\safefile_test.go`

### 保留但補強的測試檔

1. `tests\test_coverage_progress_tracker.py`
2. `tests\test_coverage_rate_limiter.py`
3. `tests\test_coverage_encoding_utils.py`
4. `tests\test_coverage_scanner.py`

## 設計原則

### 1. 能跑真邏輯就不 mock

若測試可以直接餵真實資料給 production code，優先選擇真資料，而不是把中間方法整個替換掉。

### 2. mock 只留在真正的外部邊界

以下情況允許 mock：

- `time.sleep` / `asyncio.sleep`
- 時間來源控制
- 執行緒排程不可控因素
- 明確的外部依賴邊界，且該測試的責任不是驗證該依賴本身

以下情況不應使用 mock：

- 把被測層的核心方法整個替換為固定回傳
- 先指定假資料，再 assert 外層原樣回傳
- 只驗證函式是否被呼叫，而不驗證功能結果

### 3. fixture 優先於 MagicMock

如果功能本質是解析、轉換、判斷、合併、序列化，就優先用 fixture 驅動，而不是 `MagicMock`。

### 4. 測試要能回答一個問題

**如果 production code 真壞掉，這個測試會不會紅？**

如果答案是「大多數真 bug 它還是會過」，那就是低價值測試。

## 測試資料策略

### 本地 fixture 類型

預計新增或整理以下本地樣本：

1. **真實 HTML 片段**
   - AV-WIKI 搜尋結果頁
   - JAVDB 或相關解析所需頁面片段
   - 編碼邊界案例 HTML

2. **真實番號樣本**
   - 使用真實番號字串作為輸入
   - 包含 alias / 前導 0 / 搜尋候選展開情境

3. **真實 cache payload 樣本**
   - JSON payload
   - 壓縮/未壓縮 payload
   - flag byte + payload 組合
   - not-found / invalid payload 邊界樣本

4. **真實 CLI JSON 輸出樣本**
   - 掃描結果
   - 快取結果
   - 錯誤回傳資料

### fixture 位置

優先放在 `tests\fixtures\` 下，依功能分子目錄，例如：

- `tests\fixtures\web_searcher\`
- `tests\fixtures\cache_manager\`
- `tests\fixtures\async_scraper\`

## 各模組重構方案

### A. cache_manager

#### 現況問題

- 多個測試直接 mock `_go_cache_set` / `_go_cache_get` / `_go_cache_delete`
- 測到的是回傳值搬運，不是快取序列化、payload 結構、記憶體快取更新或錯誤語意

#### 重構方向

1. 保留純邏輯測試：
   - `_is_expired`
   - LRU eviction
   - payload 序列化/反序列化

2. 重寫 Go 路徑測試：
   - 不直接 mock 高層結果
   - 改成餵真實 bytes payload 給 `_get_go` 邏輯
   - 驗證 flag byte、壓縮還原、版本不符、JSON 損壞、NotFound/Error 分支

3. 清理與統計測試改為：
   - 驗證參數轉換與輸出正規化是否正確
   - 避免只測字典搬運

### B. web_searcher

#### 現況問題

- 把 `_search_candidates_in_av_wiki` / `_search_candidates_in_javdb` 直接替換成 lambda
- 測不到搜尋順序、HTML 解析、alias metadata、候選展開是否正確

#### 重構方向

1. 保留純邏輯 helper 測試：
   - `_build_code_candidates`
   - `_attach_alias_metadata`
   - 名稱過濾與判斷

2. 重寫搜尋流程測試：
   - 用真實 HTML fixture 驅動 parser
   - 只在最外層 HTTP 回傳或 scraper 輸入邊界做隔離
   - 驗證 AV-WIKI 優先、JAVDB fallback、stop_event、中途命中 cache

3. 強化契約：
   - 當候選命中 alias 時，metadata 是否正確標記
   - 當第一層找不到時，是否真的進第二層

### C. unified_cache

#### 現況問題

- 大量 `MagicMock` 讓 manager 只是把下游結果抄上來
- 對 source 註冊、聚合、錯誤隔離的真契約驗證不足

#### 重構方向

1. 用最小 fake cache source 類別取代 `MagicMock`
2. 讓 fake source 有真實行為：
   - get / set / delete / stats / cleanup
3. 驗證 manager 的責任：
   - source 路由
   - 聚合結果
   - 單一 source 出錯時，其它 source 是否仍可運作

### D. async_scraper

#### 現況問題

- batch 類測試直接 mock `scrape_multiple_sync`
- 只測 callback 或 sleep 是否被呼叫，沒有測到批次切割與合併

#### 重構方向

1. 保留有價值的純邏輯：
   - `_should_retry_result`
   - UA rotation
   - 統計與 reset

2. 重寫 batch 測試：
   - 用可控的 fake scraper，回傳與輸入 URL 綁定的結果
   - 驗證：
     - batch 切割是否正確
     - 批次結果是否完整合併
     - progress callback 訊息是否與批次進度一致

3. 僅保留 `sleep` 類 mock

### E. safefile

#### 現況問題

- 使用錯誤的 Unix 路徑假設在 Windows 測試
- 一些測試只是「應該有 error」，但沒有測到真正的 Windows 路徑契約

#### 重構方向

1. 全面改用：
   - `t.TempDir()`
   - `filepath.Join()`
   - 平台正確路徑組裝

2. 補真正重要邊界：
   - 不存在目錄
   - 相對路徑 / `.` / `..`
   - 真實檔案讀寫
   - OpenRoot 邊界下的合法/非法路徑

3. 避免再用與平台語意不一致的測資

## 錯誤處理原則

測試要驗證的不是「有沒有任何錯」，而是：

1. 錯誤是否在正確邊界被轉譯
2. NotFound 是否與一般 GoError 區分
3. 損壞 payload 是否被安全忽略
4. stop_event、空結果、異常輸入是否有穩定輸出

## 驗證策略

每個模組重寫後都要至少驗證：

1. **功能主路徑**
2. **關鍵 fallback / 分支**
3. **錯誤語意**
4. **真實樣本解析結果**

執行順序：

1. 先跑單檔測試
2. 再跑相關回歸測試
3. 必要時補 coverage 檢查，但 coverage 不是決策依據

## 成功標準

本次重構完成後，應達成：

1. 原本被判定為低效的測試，已改成 fixture 驅動或真邏輯驅動
2. 每個保留的 mock 都能說明保留理由
3. 測試失敗時，能反映真實功能壞掉，而不是只反映 mock 沒對齊
4. safefile 測試不再依賴錯誤的平台路徑假設

## 風險與對策

### 1. fixture 過度擬真造成維護成本上升

對策：fixture 只保留最小可表達樣本，不整頁照搬無關內容。

### 2. 測試重寫後短期內數量變少

對策：接受測試數量下降，只保留對真功能有保護力的案例。

### 3. 單元測試與整合測試邊界混亂

對策：明確標註哪些是 fixture 驅動單元測試，哪些是本地薄整合測試。

## 實作順序建議

1. `test_coverage_cache_manager.py`
2. `test_coverage_web_searcher.py`
3. `test_coverage_unified_cache.py`
4. `test_coverage_async_scraper.py`
5. `pkg\safefile\safefile_test.go`
6. 相關回歸測試與整理 fixture

## 預期成果

完成後，測試將不再主要依賴「指定假答案再 assert 假答案」，而是用本地真實樣本驅動關鍵邏輯，讓測試更能捕捉：

- 搜尋與解析錯誤
- 快取 payload 錯誤
- 批次流程錯誤
- 路徑與平台邏輯錯誤

也就是說，這次重構的核心成果不是更漂亮的 coverage，而是**更可信的測試保護力**。
