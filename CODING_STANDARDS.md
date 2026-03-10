# Coding Standards

## 1. Purpose

本文件定義跨專案可重用的程式碼命名與介面設計標準。

目的：
1. 建立通用層的一致命名規範
2. 降低跨模組、跨語言、跨專案的命名漂移
3. 讓 Skill、文件、程式碼與審查流程引用同一套基準
4. 為專案特定術語提供可覆寫但不混亂的結構

本文件是長文版標準來源。
若需要精簡執行版，請搭配 `.claude/skills/naming-conventions/SKILL.md` 使用。

## 2. Scope

本標準適用於：
1. Python
2. Go
3. JSON / schema
4. CLI 命令與旗標
5. 公開 API 與橋接層 API
6. 文件中的 API 名稱
7. 測試名稱與測試資料結構命名

## 3. Core Naming Principles

### 3.1 主名稱唯一化

每個重要概念在同一專案中只能有一個主名稱。

若既有主名稱已存在：
1. 新增程式碼應沿用既有名稱
2. 不得用語意相近的新名稱平行存在
3. 若要換名，必須以重構方式整體替換

相容性例外：
1. 若舊欄位或舊 API 名稱仍需保留，必須明確標示為相容層或 deprecated 別名
2. 相容性別名不得被文件描述成新的主名稱
3. 新程式碼不得再擴散使用相容性別名

### 3.2 一致性優先於個人偏好

命名的第一原則不是美感，而是讓整個專案在閱讀、搜尋、維護與重構時保持穩定。

### 3.3 語意清楚優先於縮寫

名稱必須能說明：
1. 它是什麼
2. 它做什麼
3. 它是否為集合、單筆、狀態、結果或設定

### 3.4 對外名稱穩定

對外 API、JSON 欄位、CLI 參數、文件中的名稱必須保持穩定。

內部重構時：
1. 優先保留對外名稱
2. 若不得不變更，必須同步更新文件、測試與呼叫端

### 3.5 動詞不可混用

當多個函式描述相同操作意圖時，必須使用同一個動詞。

例如：
1. 若專案中已用 `identify_studio` 表達辨識，不應再新增 `detect_studio`
2. 若專案中已用 `list_videos` 表達列出，不應再新增 `get_video_list`

## 4. Name Registry Rules

### 4.1 什麼是主名稱

主名稱是專案中某概念的標準稱呼。

常見概念包括：
1. 主要資料物件
2. 唯一識別碼
3. 搜尋結果
4. 批次操作輸入
5. 回滾記錄
6. 暫存檔路徑

### 4.2 建立主名稱的時機

以下情況應建立或確認主名稱：
1. 建立新模組
2. 設計公開 API
3. 定義 JSON 欄位
4. 建立 Python ↔ Go 橋接
5. 擴充既有領域模型

### 4.3 舊名稱淘汰規則

若主名稱變更：
1. 應有明確替換範圍
2. 文件、測試、呼叫端一起調整
3. 若需相容期，需標記 deprecated 名稱與移除時程

## 5. Python Naming Rules

### 5.1 類別

使用 `PascalCase`

正例：
1. `GoBridge`
2. `ConfigManager`
3. `BatchSearchResult`

### 5.2 函式與方法

使用 `snake_case`

正例：
1. `scan_directory`
2. `query_videos`
3. `identify_studio`

### 5.3 變數

使用 `snake_case`

正例：
1. `input_dir`
2. `search_results`
3. `temp_file_path`

### 5.4 常數

使用 `UPPER_SNAKE_CASE`

正例：
1. `DEFAULT_TIMEOUT`
2. `MAX_CONCURRENT_REQUESTS`
3. `CACHE_CLEANUP_INTERVAL`

### 5.5 私有成員

使用前置底線。

正例：
1. `_run_command`
2. `_parse_json`
3. `_normalize_result`

### 5.6 測試名稱

1. 測試函式使用 `test_` 開頭
2. 名稱要描述行為與條件

正例：
1. `test_identify_studio_fallback_on_bridge_error`
2. `test_batch_move_cleans_temp_file`

## 6. Go Naming Rules

### 6.1 匯出符號

使用 `PascalCase`

正例：
1. `ScanResult`
2. `NewJSONDatabase`
3. `BatchMove`

### 6.2 私有符號

使用小寫開頭。

正例：
1. `cleanupIndex`
2. `writeJournalEntry`
3. `parseCode`

### 6.3 package 名稱

1. 使用簡短小寫
2. 不用底線
3. 不用複數與語意重疊名稱

正例：
1. `extractor`
2. `database`
3. `studio`

### 6.4 receiver 名稱

簡短但有語意，不用無意義單字母。

正例：
1. `db`
2. `mover`
3. `extractor`

### 6.5 錯誤名稱

使用 `ErrXxx`

正例：
1. `ErrNotFound`
2. `ErrInvalidCode`
3. `ErrJournalCorrupted`

## 7. JSON and Schema Rules

### 7.1 欄位命名

所有對外 JSON 欄位一律使用 `snake_case`。

正例：
1. `file_path`
2. `created_at`
3. `is_major`
4. `batch_results`

### 7.2 布林欄位

以 `is`、`has`、`can` 開頭。

正例：
1. `is_available`
2. `has_cache`
3. `can_retry`

### 7.3 時間欄位

優先使用標準欄位名。

正例：
1. `created_at`
2. `updated_at`
3. `deleted_at`
4. `last_search_date`

### 7.4 識別欄位

識別欄位名稱應穩定且可跨語言映射。

建議：
1. `id` 用於內部唯一識別
2. `code` 用於外部業務識別碼
3. `name` 用於可讀名稱

補充：
1. 若既有資料格式同時存在 `code` 與 `id`，文件必須註明哪個是主名稱、哪個只是舊版相容欄位
2. `video_code` 這類名稱只應在關聯結構或需要消除歧義的欄位中使用，不應回頭取代既有主名稱 `code`

## 8. API Verb Rules

### 8.1 `get_xxx`

用於取得單一物件。

適用：
1. 已知唯一鍵
2. 預期回傳單筆資料

### 8.2 `list_xxx`

用於列出多筆資料。

適用：
1. 無模糊搜尋
2. 回傳多筆結果

### 8.3 `query_xxx`

用於條件查詢。

適用：
1. 查詢條件較複雜
2. 條件可能擴充

### 8.4 `search_xxx`

用於模糊搜尋或外部搜尋。

適用：
1. 網站搜尋
2. 模糊匹配
3. 不保證唯一命中

### 8.5 `identify_xxx`

用於規則判斷、辨識、推論。

適用：
1. 輸入不是直接鍵值
2. 輸出依規則推斷

### 8.6 `create_xxx`

用於建立全新物件。

### 8.7 `add_xxx`

用於加入既有集合。

### 8.8 `update_xxx`

用於更新既有物件。

### 8.9 `delete_xxx`

用於刪除既有物件。

### 8.10 `compact_xxx`

用於合併、壓縮、整理狀態。

### 8.11 `normalize_xxx`

用於標準化輸出格式或名稱。

### 8.12 橋接層前綴規則

若某函式是公開橋接 helper，且它明確綁定某個子命令家族，可以在動詞前加上穩定領域前綴。

適用：
1. Python wrapper 直接對應 Go CLI 子命令家族
2. 需要避免與同模組其他一般 helper 撞名
3. 前綴本身已是既有穩定命名，而非臨時縮寫

正例：
1. `db_get_video`
2. `db_update_video`
3. `db_compact_journal`

限制：
1. 前綴只用於表達穩定家族邊界，不可任意堆疊
2. 同一 API 家族內要一致，例如不要同時出現 `db_get_video` 與 `database_get_stats`

### 8.13 批次命名規則

1. 單筆與批次介面應成對出現
2. 批次命名必須跟隨既有 API 家族，而不是強迫全專案只有單一字尾
3. 同一 API 家族內只能有一種批次模式
4. 既有穩定介面可保留不同家族慣例，但新程式碼不可在同一家族再混出第三種寫法

正例：
1. `identify_studio` / `identify_studios_batch`
2. `update_video` / `update_videos_batch`
3. `move_file` / `batch_move`
4. `search_video_info` / `batch_search`

說明：
1. 若某家族已經使用 `batch_xxx` 前綴，延續前綴模式
2. 若某家族已經使用 `_batch` 後綴，延續後綴模式
3. 不要在同一模組內同時新增 `batch_identify_studio`、`identify_studios_batch`、`identify_many_studios`

## 9. CLI Naming Rules

### 9.1 子命令

使用短、明確、不可重疊的名稱。

正例：
1. `scan`
2. `move`
3. `identify`
4. `history`
5. `db`

### 9.2 旗標命名

1. 同層旗標保持一致
2. 避免語意重疊旗標並存
3. 路徑、目錄、檔案類型參數名稱需明確區分
4. 若 CLI 已存在短旗標慣例且有向後相容需求，應優先延續既有名稱，而不是在同一命令家族再引入同義長旗標

### 9.3 路徑與檔案參數

建議：
1. `path`
2. `input_file`
3. `output_file`
4. `directory` 或 `dir` 二選一

相容性補充：
1. 若既有 CLI 已穩定使用 `-dir`、`-src`、`-dst`、`-batch` 這類短旗標，應視為命令家族標準
2. 文件需標示該選擇來自既有 CLI 相容性，而不是新的通用偏好
3. 新增旗標時優先貼齊既有家族，例如既有 `-data-dir`、`-log-dir` 已採語意化長旗標時，後續應沿用同層風格

## 10. Cross-Language Mapping Rules

### 10.1 映射原則

1. Python 使用 `snake_case`
2. Go 使用 `PascalCase` 或私有小寫慣例
3. JSON 使用 `snake_case`
4. 文件以主名稱作為共通對照層

### 10.2 範例

Python：`get_video_stats`

Go：`GetVideoStats`

JSON：`video_stats`

橋接層範例：

Python：`db_get_stats`

Go 子命令：`db stats`

JSON：`journal_size`

### 10.3 禁止事項

1. 不同語言層使用不同動詞表達同一行為
2. 不同層使用不同主名稱指同一資料
3. JSON 欄位與文件主名稱完全脫鉤

## 11. Project Override Rules

### 11.1 可以覆寫的內容

專案 Skill 可以覆寫：
1. 領域名詞
2. 主要資料物件名稱
3. 外部來源名稱
4. 批次命名後綴偏好

### 11.2 不應覆寫的內容

專案 Skill 不應覆寫：
1. 主名稱唯一化原則
2. API 動詞邊界
3. JSON 對外穩定性原則
4. 通用命名反模式

## 12. Anti-Patterns

### 12.1 模糊名稱

避免：
1. `data`
2. `info`
3. `thing`
4. `object`

### 12.2 臨時名稱流入正式 API

避免：
1. `result2`
2. `temp_result`
3. `final_final_data`

### 12.3 同義動詞混用

避免：
1. `get_video` 與 `fetch_video`
2. `identify_studio` 與 `detect_studio`
3. `delete_video` 與 `remove_video`

### 12.4 過長名稱

不建議：
`get_list_of_videos_filtered_by_studio_and_date_range`

建議：
`query_videos`

說明：條件放在參數，不放在函式名。

### 12.5 縮寫濫用

避免：
1. `cfg2`
2. `rslt`
3. `mgr_new`

## 13. Review Checklist

提交前檢查：
1. 是否引入第二個主名稱
2. 是否違反 API 動詞規則
3. 是否與既有模組名稱不一致
4. JSON 欄位是否仍可穩定映射
5. 是否需要同步更新文件與測試

## 14. Migration Rules

若要重命名：
1. 先確認主名稱是否真的要更換
2. 明確列出受影響程式碼、文件、測試、JSON 欄位
3. 若需相容期，標註 deprecated 名稱與淘汰時程
4. 不允許新舊名稱長期並存而無說明

## 15. Examples

### 好的命名

1. `identify_studios_batch`
2. `db_get_stats`
3. `GetVideoStats`
4. `created_at`

### 壞的命名

1. `do_search`
2. `tmp_data`
3. `fetch_video_info` 與 `get_video` 並存
4. `manager_new`

## 16. Related Standards

1. 專案 Skill：補充專案術語
2. `code-review` Skill：審查重要問題時引用本文件
3. `go-bridge-development` Skill：檢查跨語言命名對齊
4. `documentation-guide` Skill：確保文件名稱與程式名稱一致