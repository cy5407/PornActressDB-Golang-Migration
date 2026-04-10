# Sonar Safe Fixes Todo

狀態說明：
- `[ ]` 未處理
- `[-]` 進行中
- `[x]` 已完成
- `[s]` 略過（需附原因）

規則：
- 只處理低風險 Sonar 小修，不改核心邏輯。
- 若 git 工作樹不乾淨，整輪跳過並保留原狀。
- 每次 cron run 最多處理 1 個小項或 1 個極小批次。
- 每次完成後更新本檔狀態與簡短註記。
- 若全部項目都為 `[x]` 或 `[s]`，代表清單已完成，可停止排程。

## Todo

### 1) Remove commented-out code
- [s] `src/models/config.py`（此檔未找到可安全移除的註解程式碼）
- [s] `src/scrapers/__init__.py`（未找到可安全移除的註解程式碼）
- [s] `src/scrapers/async_scraper.py`（僅見說明性註解，未發現可安全移除的註解程式碼）
- [s] `src/scrapers/cache_manager.py`（檢查後未找到可安全移除的註解程式碼）
- [s] `src/scrapers/encoding_utils.py`（檢查後未找到可安全移除的註解程式碼）
- [s] `src/scrapers/rate_limiter.py`（檢查後未找到可安全移除的註解程式碼）
- [s] `src/utils/actress_name_filter.py`（多處；目前僅見合法說明註解，無可安全移除的註解程式碼）
- [s] `src/utils/progress_tracker.py`（檢查後未找到可安全移除的註解程式碼）
- [s] `src/utils/retry_utils.py`（檢查後未找到可安全移除的註解程式碼）

### 2) Define constants for duplicated literals
- [x] `src/scrapers/run_batch_search.py` — 抽出 `CONFIG_INI_FILENAME`
- [x] `src/scrapers/run_search.py` — 抽出 `CONFIG_INI_FILENAME`
- [x] `src/services/web_searcher.py` — 抽出 `AV_WIKI_SEARCH_METHOD`
- [x] `src/scrapers/cache_manager.py` — 抽出 `CACHE_PRUNE_EMPTY_RESULT_MESSAGE`

### 3) Other low-risk cleanups
- [x] `src/utils/actress_name_filter.py` — remove unused local variable `total_kana`
- [s] `src/scrapers/cache_manager.py` — 未找到可安全移除的 redundant Exception class

## Run Log

- 初始化：建立追蹤檔，等待第一次執行。
- `src/utils/actress_name_filter.py`: 移除未使用的 `total_kana`。
- `src/models/config.py`: 檢查後未找到可安全移除的註解程式碼，略過。
- `src/scrapers/__init__.py`: 檢查後未找到可安全移除的註解程式碼，略過。
- `src/scrapers/async_scraper.py`: 僅見說明性註解，未發現可安全移除的註解程式碼，略過。
- `src/scrapers/cache_manager.py`: 未找到可安全移除的註解程式碼與 redundant Exception class，改列為略過。
- `src/scrapers/encoding_utils.py`: 未找到可安全移除的註解程式碼，略過。
- `src/scrapers/rate_limiter.py`: 未找到可安全移除的註解程式碼，略過。
- `src/utils/actress_name_filter.py`: 目前僅見合法說明註解，無可安全移除的註解程式碼，略過。
- `src/utils/progress_tracker.py`: 未找到可安全移除的註解程式碼，略過。
- `src/utils/retry_utils.py`: 未找到可安全移除的註解程式碼，略過。

## Auto Commit State
- Last auto-commit completed count: 4
- Last auto-commit hash: N/A
