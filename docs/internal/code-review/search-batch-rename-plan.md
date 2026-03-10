# 搜尋批次命名家族重構計畫

建立時間: 2026-03-10 14:05:00 +08:00

## 目標

把目前搜尋批次相關 API 的命名收斂到同一條家族規則，避免同一層同時出現：
1. `batch_search_*`
2. `search_batch_*`
3. 其他未來可能衍生的第三種寫法

本計畫只處理 **search 家族**。
不處理 `scrape_in_batches` 這種屬於 **scrape 家族** 的工具型 API，因為它表達的是不同操作意圖。

## 現況盤點

目前主要相關 API：
1. [src/services/web_searcher.py](src/services/web_searcher.py#L539) `batch_search`
2. [src/services/web_searcher.py](src/services/web_searcher.py#L1102) `batch_cascade_search`
3. [src/scrapers/unified_scraper.py](src/scrapers/unified_scraper.py#L421) `batch_search_videos`
4. [src/scrapers/sources/avwiki_scraper.py](src/scrapers/sources/avwiki_scraper.py#L585) `batch_search_concurrent`
5. [src/scrapers/sources/avwiki_scraper.py](src/scrapers/sources/avwiki_scraper.py#L826) `search_batch_concurrent`（相容層）

目前問題：
1. 同一家族已經同時存在 `batch_search_*` 與 `search_batch_*`
2. 呼叫端閱讀時，無法一眼判斷哪個才是主命名模式
3. 後續新功能很容易再長出第三種變體

## 命名收斂原則

主規則：
1. 批次搜尋一律以 `batch_search` 作為主前綴
2. 額外能力放在後綴，例如 `batch_search_concurrent`
3. 先保留相容 wrapper，再分批移除舊名

建議主名稱：
1. `batch_search`
2. `batch_cascade_search`
3. `batch_search_videos`
4. `batch_search_concurrent`

建議淘汰名稱：
1. `search_batch_concurrent`

## 分批提交策略

### Commit 1: 建立新主名稱與相容 wrapper

狀態：已完成（commit `8ad2a16`）

目標：
1. 在 AV-WIKI scraper 中新增 `batch_search_concurrent`
2. 保留 `search_batch_concurrent` 作為薄 wrapper 或 deprecated alias
3. 補註解說明舊名僅為相容層

受影響檔案：
1. `src/scrapers/sources/avwiki_scraper.py`

驗證：
1. 現有呼叫端不需同步改動也能運作
2. 新名稱與舊名稱回傳結果完全一致

### Commit 2: 切換內部呼叫端到新主名稱

狀態：已完成（commit `d1824c2`）

目標：
1. 將內部呼叫端從 `search_batch_concurrent` 改為 `batch_search_concurrent`
2. 保持外部行為不變

受影響檔案：
1. `src/services/web_searcher.py`
2. 可能包含其他直接呼叫 AV-WIKI batch API 的測試或文件

驗證：
1. `batch_search_avwiki_concurrent` 流程維持原樣
2. 批次搜尋結果與快取邏輯不回歸

### Commit 3: 更新測試與文件名稱

狀態：已完成（本次工作樹）

目標：
1. 將測試、說明、註解中的舊名同步換成新主名稱
2. 文件只保留一個主名稱，舊名只在相容說明中出現

受影響檔案：
1. 相關單元測試
2. 技術文件與 skill 文件

驗證：
1. 搜尋 repo，不再把舊名當成主名稱介紹
2. 相容 wrapper 已有最小單元測試覆蓋

### Commit 4: 移除舊相容 wrapper

前提：
1. 所有內部呼叫端已完成切換
2. 沒有外部依賴需要保留舊名
3. 文件與測試已確認只把舊名視為遷移相容層

目標：
1. 刪除 `search_batch_concurrent`
2. 完成 search 批次家族收斂

驗證：
1. 搜尋 repo，舊名僅存在於 changelog 或遷移紀錄

## 不建議納入本輪 rename 的項目

1. `scrape_in_batches`
原因：屬於 scrape 家族，不是 search 家族

2. `batch_search_videos`
原因：已符合 `batch_search_*` 主規則，暫不需要改名

3. `batch_search` / `batch_cascade_search`
原因：已是目前應保留的主命名模式

## 實作順序建議

1. 先完成 `batch_move / move_batch` 跨語言統一並提交
2. 再做搜尋批次 API 的 Commit 1 與 Commit 2
3. 等呼叫端穩定後，再決定是否做 Commit 4 清除舊 alias

## 驗證清單

1. 搜尋 API 主名稱是否只剩 `batch_search_*`
2. 相關批次搜尋流程是否仍正常回傳結果
3. 進度回調、快取、併發限制是否未被 rename 破壞
4. 文件與測試是否同步更新

## 目前判定

截至 2026-03-10：
1. 內部正式呼叫端已切換到 `batch_search_concurrent`
2. `search_batch_concurrent` 僅剩相容 wrapper 與遷移說明用途
3. 已補上相容 wrapper 的最小測試，確認舊名仍正確代理到新主名稱
4. 本輪採保守策略：先保留 wrapper，等下一個 checkpoint 再評估移除

## Commit 4 啟動條件檢查

1. 內部正式呼叫端：已完成切換
2. 文件主名稱：已完成切換
3. 相容層保護：已有最小測試可在移除前後協助比對
4. 目前阻塞點：本輪決策為保留對外相容性到下一個 checkpoint

## 遷移註記

1. 正式主名稱：`batch_search_concurrent`
2. 暫時保留舊名稱：`search_batch_concurrent`
3. 保留原因：避免外部腳本、個人分支或未同步文件在本輪 rename 後立即失效
4. 下個 checkpoint 要做的事：重新掃描呼叫點、確認外部依賴是否已完成切換，再執行 Commit 4
