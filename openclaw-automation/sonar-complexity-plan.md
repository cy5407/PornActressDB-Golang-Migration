# Sonar Complexity Refactor Plan

目的：針對目前 Sonar 仍值得處理的高價值 complexity issue，先做結構理解，再拆成可執行的小步驟。

原則：
- 先處理搜尋/爬蟲流程，暫不優先動 `pkg/database/jsondb.go`
- 以「降低 Cognitive Complexity」為目標，但不能改變對外行為
- 優先抽 helper / 分階段函式，不做大規模重寫
- 每一項都要能獨立 review、獨立測試、獨立回退
- 若 Sonar 畫面檔名與 repo 實際檔名不一致，以 repo 實際檔名為準

## 0. 盤點備註

- Sonar 畫面提到的 `src/services/feat_javdb_searcher.py` 在目前 repo **不存在**。
- 目前實際存在且相關的檔案是：
  - `src/services/web_searcher.py`
  - `src/services/safe_javdb_searcher.py`
  - `src/scrapers/sources/avwiki_scraper.py`
  - `src/scrapers/sources/javdb_scraper.py`
  - `src/utils/actress_name_filter.py`
- 因此後續規劃以實際檔案為主；若 Sonar 仍顯示舊檔名，先確認分析是否有舊結果殘留。

---

## 1. `src/services/web_searcher.py`（第一優先）

### 目前理解的流程結構

#### 單筆搜尋主流程
- `search_info(code, stop_event)`
  1. 建立候選 code
  2. 依序走 AV-WIKI
  3. 失敗後走 JAVDB
  4. 成功時附加 alias metadata 與 cache

#### AV-WIKI 單筆搜尋
- `_search_av_wiki(code, stop_event)` 目前同時做了：
  - 組 search URL
  - 建立 request function
  - 抓搜尋頁 HTML
  - 判斷是否無結果
  - 從 tag link 提取 actresses
  - 補抓 detail page
  - fallback 文本掃描 actresses
  - 做結果品質判斷
  - 標準化片商
  - 組裝回傳 dict

#### 批次搜尋流程
- `batch_search_avwiki_concurrent(...)`
  - 過濾 cache
  - 包裝 progress callback
  - 建立 async runner
  - chunk 分段執行
  - 合併快取與新結果
  - 統計成功率

- `batch_cascade_search(...)`
  - Phase 1: AV-WIKI 批次搜尋
  - Phase 2: 對失敗 code 做 alias fallback
  - 更新 result_callback / progress
  - 組裝 tried_sources / final_source

### 為什麼它 complexity 高
- 單一函式混了太多責任：HTTP、HTML、fallback、品質檢查、結果組裝、log
- 同時兼顧單筆與批次、同步與 async、UI progress 與搜尋邏輯
- 大量 `if/for/try` 巢狀

### 建議拆分任務
- [x] **WBS-1**：拆 `_search_av_wiki()`
  - 已抽出 helper，並保留原回傳格式與錯誤語義。

- [x] **WBS-2**：整理 `_search_av_wiki()` 的 fallback 分支
  - 已將「no results 判斷」「text scan fallback」「>10 actresses quality gate」抽成 helper，主函式改為 orchestration。

- [x] **WBS-3**：拆 `batch_search_avwiki_concurrent()`
  - 已抽出：cache 分流、progress callback 包裝、async chunk runner、result cache/merge helper
  - 保留快取與 progress 行為

- [x] **WBS-4**：拆 `batch_cascade_search()`
  - 已拆成：phase1 result apply、alias candidate build、phase2 alias apply、summary orchestration
  - 保留 `tried_sources` / `final_source` 語義

### 驗收重點
- 單筆搜尋輸出欄位不變
- alias metadata 不丟失
- progress callback 輸出順序不亂
- 搜尋失敗 / search_error / no_result 三種狀態語義保持一致

---

## 2. `src/scrapers/sources/avwiki_scraper.py`（第一優先）

### 目前理解的流程結構
- `parse_content()` 依 URL 分成搜尋頁 / 詳情頁
- `_parse_search_results()` 會：
  - 判斷 no-result
  - 做多策略 actress element 抽取
- `_parse_detail_page()` 會：
  - 提取 title
  - 多層 actresses 提取
  - 文本掃描 fallback
  - 提取片商與日期
- `batch_search_concurrent()` 會：
  - 建立 adaptive concurrency controller
  - 建立 semaphore
  - 包住單筆搜尋、退避、錯誤分類、統計

### complexity 集中點
- `_parse_detail_page()`
- `batch_search_concurrent()`
- 可能還有 `_extract_actresses_from_text()`

### 建議拆分任務
- [x] **AVW-1**：拆 `_parse_detail_page()`
  - 已抽出標題與女優抽取 helper，detail page 主流程較線性。

- [x] **AVW-2**：把 detail actresses 的三段式策略線性化
  - 已拆成 tag link / actress-name / text scan 三段 helper。

- [x] **AVW-3**：拆 `batch_search_concurrent()`
  - 已抽出：
    - 單筆搜尋 helper `_search_single_video_batch()`
    - 進度通知 helper `_notify_batch_search_progress()`
    - 暫時性錯誤判斷 helper `_is_temporary_batch_search_error()`
    - 結果統計 helper `_summarize_batch_search_results()`
  - 保留 adaptive concurrency / backoff 行為

- [x] **AVW-4**：審視 `_extract_actresses_from_text()`
  - 已抽出：
    - candidate line selection helper `_select_actress_scan_lines()`
    - name extraction helper `_extract_actress_names_from_lines()`
    - result limit / dedup 維持原行為

### 驗收重點
- `unique_actresses` / `search_results` / `found` 欄位語義不變
- 批次搜尋成功率統計邏輯不變
- adaptive concurrency 行為不退化

---

## 3. `src/scrapers/sources/javdb_scraper.py`（第一優先）

### 目前理解的流程結構
- `_parse_search_results()`
  - 掃 `div.item`
  - 提取 detail url / title / actresses / studio / date
- `_parse_detail_page()`
  - title / cover / panel blocks / rating / studio_code
- `_extract_detail_panel_data()` + `_apply_detail_panel()`
  - 依 label 分派演員、片商、日期、時長、導演、系列、類別
- `search_video()`
  - 搜尋頁 -> 取第一筆 -> 如果有 detail_url 再抓 detail -> 合併結果

### complexity 集中點
- `_parse_search_results()`
- `_parse_detail_page()`
- `search_video()`

### 建議拆分任務
- [x] **JDB-1**：拆 `_parse_search_results()`
  - 已抽出 `_parse_search_result_item(item)`，主函式改為迭代聚合。

- [ ] **JDB-2**：拆 `_parse_detail_page()`
  - 抽出：
    - title / cover helper
    - panel parse helper（保留 `_apply_detail_panel()`）
    - studio code from title helper
    - result builder

- [ ] **JDB-3**：拆 `search_video()`
  - 分成：
    - `_search_video_results(video_code)`
    - `_load_first_detail_if_present(first_result)`
    - `_finalize_search_video_result(...)`
  - 讓主流程變成「搜尋 -> 取第一筆 -> 補詳情 -> 回傳」

### 驗收重點
- 搜尋頁 fallback 與 detail page merge 邏輯不變
- `video_code` / `search_url` / `content_quality` 欄位仍一致
- detail_url 存在與不存在兩條路都要保留

---

## 4. `src/utils/actress_name_filter.py`（第二優先）

### 目前理解的流程結構
- `is_valid_actress_name()` 是規則密集型函式：
  - 長度檢查
  - title keyword（日文/中文）
  - verb patterns
  - 截斷標題判斷
  - 純數字/符號判斷
  - hiragana ratio
  - 日文/中文 / 西文格式驗證

### complexity 來源
- 規則多、if 連鎖長
- 內含多個早退判斷
- 同時兼顧日文/中文/英文藝名條件

### 建議拆分任務
- [x] **ANF-1**：將 `is_valid_actress_name()` 改成 rule pipeline
  - 已抽成 rule helpers，保留原判準與 logging。

- [ ] **ANF-2**：整理 `get_most_likely_actress()`
  - 保持邏輯不變
  - 將 score helper 外提成 private static method

### 驗收重點
- 現有名稱過濾結果不應大幅改變
- 中文 / 日文 / 英文藝名判準不能被意外放寬或收緊

---

## 5. `pkg/database/jsondb.go`（暫緩，最後處理）

### 目前策略
- [ ] **DB-PAUSE**：暫不因 Sonar complexity 立即重構 `pkg/database/jsondb.go`

### 原因
- 這是核心資料層
- 目前 priority 應是先處理搜尋/爬蟲類 complexity
- 等有更完整測試保護與時間窗口，再單獨規劃 DB refactor

---

## 建議執行順序

### 第一波（最有投報比）
1. `web_searcher.py`
   - WBS-1
   - WBS-2
2. `avwiki_scraper.py`
   - AVW-1
   - AVW-2
3. `javdb_scraper.py`
   - JDB-1
   - JDB-2

### 第二波（批次/協程 orchestration）
4. `web_searcher.py`
   - WBS-3
   - WBS-4
5. `avwiki_scraper.py`
   - AVW-3
   - AVW-4
6. `javdb_scraper.py`
   - JDB-3

### 第三波（規則函式整理）
7. `actress_name_filter.py`
   - ANF-1
   - ANF-2

### 最後單獨評估
8. `pkg/database/jsondb.go`
   - DB-PAUSE（先不做）

---

## 完成定義
- [ ] 每個高 complexity 函式都被拆成較小 helper，但對外行為不變
- [ ] 每一批變更都可獨立 review
- [ ] 不因為降 complexity 而引入功能差異
- [ ] DB 核心層暫不為 Sonar 分數硬拆
