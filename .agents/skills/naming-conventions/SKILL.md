---
name: naming-conventions
description: 通用命名規範 Skill - 用於統一 Python、Go、JSON、CLI、API 的命名方式，避免跨模組與跨專案命名偏差，特別適合新增函式、類別、資料結構、橋接層 API、批次介面與重構命名時使用
argument-hint: "[module-name or api-area]"
user-invocable: true
---

# 命名規範 Skill

## 何時使用此 Skill

當需要：
1. **新增類別、函式、變數、常數**
2. **設計公開 API 或 CLI 命令**
3. **建立 Python ↔ Go 橋接介面**
4. **建立 JSON 資料結構或跨語言型別對照**
5. **進行重構並統一舊命名**
6. **檢查不同模組是否對同一概念使用不同名稱**
7. **建立新專案 Skill，想沿用一致命名治理方式**

## 核心定位

本 Skill 是**通用層命名規範**，不綁定任何特定專案領域。

它負責：
1. 定義跨專案都適用的命名原則
2. 定義 Python、Go、JSON、CLI、API 的通用命名規則
3. 規範主名稱唯一化與 API 動詞邊界
4. 提供跨語言映射與命名反模式

它**不負責**：
1. 定義專案專屬術語
2. 替代專案 Skill 中的領域詞彙表
3. 強制某一專案採用特定名詞

若專案有領域固定詞彙，應由專案 Skill 覆寫。例如：
1. 哪個詞代表主資料物件
2. 哪個詞代表識別碼
3. 哪個詞代表外部來源
4. 哪個批次命名家族是該專案標準

## 核心原則

### 1. 一致性優先於個人偏好

同一個概念在同一個專案中只能有一個主名稱。
如果既有主名稱已存在，後續程式碼必須沿用，而不是另起別名。

### 2. 語意清楚優先於縮寫

名稱應直接表達用途、資料型態或動作。
除非縮寫是領域內公認寫法，否則不要使用模糊縮寫。

### 3. 對外名稱穩定，對內名稱可語言化

對外 API、JSON、CLI、文件中的名稱應穩定。
語言內部可以依語言慣例調整，但必須能明確映射回同一個主名稱。

### 4. 動詞只能表達一種操作意圖

同一層 API 不要把 `get`、`fetch`、`load`、`query` 混用在相同語意上。
先定義每個動詞的邊界，再命名。

### 5. 通用規則在本 Skill，專案術語在專案 Skill

本 Skill 不綁特定領域詞。
像 `actress`、`studio`、`code` 這類專案詞彙，應由專案 Skill 覆寫與補充。

## 主名稱唯一化規則

### 定義

主名稱是指某個概念在專案中的標準稱呼。

範例概念：
1. 使用者物件
2. 影片編號
3. 批次識別結果
4. 暫存檔路徑
5. 回滾操作記錄

### 規則

1. 每個重要概念只能有一個主名稱
2. 新名稱若與既有名稱語意重疊，應優先沿用既有名稱
3. 若要改主名稱，必須整體重構，不接受新舊名稱長期並存
4. 文件、程式碼、測試、JSON 欄位應盡量使用同一主名稱
5. 若某層因語言慣例不同而不同名，需可一對一映射
6. 若因相容性保留舊欄位或舊名稱，必須明確標示為相容層，不得把它寫成新的主名稱

### 範例

不建議：
1. 同時使用 `code`、`video_code`、`movie_id` 指同一概念
2. 同時使用 `studio`、`vendor`、`maker` 指同一概念
3. 同時使用 `result`、`response`、`payload` 指同一種固定輸出

建議：
1. 先選一個主名稱，再在全專案統一
2. 若對外名稱已穩定，內部也應盡量貼齊
3. 若既有格式同時保留 `code` 與 `id`，應明確註明誰是主名稱、誰是舊版相容欄位

## Python 命名規則

### 類別

使用 `PascalCase`

範例：
1. `ConfigManager`
2. `GoBridge`
3. `BatchSearchResult`

### 函式與方法

使用 `snake_case`

範例：
1. `scan_directory`
2. `identify_studio`
3. `build_search_request`

### 變數

使用 `snake_case`

範例：
1. `input_dir`
2. `batch_results`
3. `temp_file_path`

### 常數

使用 `UPPER_SNAKE_CASE`

範例：
1. `DEFAULT_TIMEOUT`
2. `MAX_CONCURRENT_REQUESTS`
3. `JOURNAL_COMPACT_THRESHOLD`

### 私有成員

使用前置底線

範例：
1. `_run_command`
2. `_load_cache`
3. `_normalize_result`

## Go 命名規則

### 匯出型別與函式

使用 `PascalCase`

範例：
1. `ScanResult`
2. `NewJSONDatabase`
3. `BatchMove`

### 私有型別與函式

使用小寫開頭

範例：
1. `parseCode`
2. `cleanupIndex`
3. `writeJournalEntry`

### receiver 命名

短但有語意，不用單字母亂縮寫。

建議：
1. `db`
2. `mover`
3. `extractor`

避免：
1. `x`
2. `t`
3. `z`

### 錯誤名稱

使用 `ErrXxx`

範例：
1. `ErrNotFound`
2. `ErrInvalidCode`
3. `ErrJournalCorrupted`

## JSON 命名規則

### 對外 JSON 欄位

一律使用 `snake_case`。

範例：
1. `file_path`
2. `created_at`
3. `is_major`
4. `batch_results`

### 規則

1. 不使用 `camelCase`
2. 不使用 `PascalCase`
3. 不把語言內部縮寫直接搬到 JSON
4. 布林欄位以 `is`、`has`、`can` 開頭
5. 時間欄位優先使用 `created_at`、`updated_at`、`deleted_at` 這類標準形式

## CLI 命名規則

### 子命令

使用短、明確的動詞或名詞。

範例：
1. `scan`
2. `move`
3. `identify`
4. `history`
5. `db`

### 參數

同一層級保持一致：
1. 若使用短旗標，需有清楚理由
2. 若已有完整語意旗標，不要再新增同義旗標
3. 避免同專案內混用 `dir`、`directory`、`path` 表示重疊概念

### 檔案參數命名

1. 路徑用 `path`
2. 輸入檔用 `input_file`
3. 輸出檔用 `output_file`
4. 目錄用 `directory` 或 `dir` 二選一，專案內固定

補充：
1. 若既有 CLI 為了向後相容已穩定使用 `-dir`、`-src`、`-dst`、`-batch`，新文件應延續描述該家族，而不是硬改成另一套同義旗標
2. 同一命令家族內若已存在語意化長旗標，例如 `-data-dir`、`-log-dir`，後續也應沿用同層風格

## API 動詞規則

### 查單筆

使用 `get_xxx`

適用：
1. 已知唯一鍵
2. 明確取得單一物件

範例：
1. `get_video`
2. `get_operation`
3. `get_config`

### 查列表

使用 `list_xxx`

適用：
1. 列出多筆資料
2. 不帶模糊搜尋語意

範例：
1. `list_videos`
2. `list_studios`
3. `list_operations`

### 條件查詢

使用 `query_xxx`

適用：
1. 帶條件篩選
2. 查詢條件可能擴充

範例：
1. `query_videos`
2. `query_operations`

### 網頁搜尋或模糊搜尋

使用 `search_xxx`

適用：
1. 網站搜尋
2. 模糊匹配
3. 不保證唯一命中

範例：
1. `search_actress`
2. `search_codes`

### 辨識或推斷

使用 `identify_xxx`

適用：
1. 輸入不是直接鍵值
2. 輸出來自規則判斷或推論

範例：
1. `identify_studio`
2. `identify_provider`

### 建立

使用 `create_xxx`

適用：
1. 明確建立新物件
2. 不隱含更新

範例：
1. `create_operation_log`
2. `create_cache_entry`

### 新增到集合

使用 `add_xxx`

適用：
1. 加入既有集合
2. 不保證是全新物件

範例：
1. `add_video`
2. `add_prefix`

### 更新

使用 `update_xxx`

適用：
1. 修改既有物件
2. 需要唯一目標

範例：
1. `update_video`
2. `update_cache_index`

### 刪除

使用 `delete_xxx`

適用：
1. 實際移除資料

範例：
1. `delete_video`
2. `delete_cache_entry`

### 合併、整理、壓縮

使用 `compact_xxx` 或 `normalize_xxx`

適用：
1. 整理資料狀態
2. 不屬於 CRUD

範例：
1. `compact_journal`
2. `normalize_studio_name`

### 橋接層前綴

規則：
1. 若某 helper 明確綁定子命令家族，可在動詞前加穩定前綴
2. 前綴應代表既有家族邊界，不可變成任意縮寫集合
3. 同一家族只保留一種前綴寫法

範例：
1. `db_get_video`
2. `db_update_video`
3. `db_get_stats`

### 批次操作

規則：
1. 單筆與批次介面應成對出現
2. 批次介面要跟隨既有 API 家族，不強迫全專案只有一種字尾
3. 同一家族內只能選一種批次模式
4. 若專案已有既有慣例，沿用既有慣例

範例：
1. `identify_studio` / `identify_studios_batch`
2. `update_video` / `update_videos_batch`
3. `move_file` / `batch_move`
4. `search_video_info` / `batch_search`

補充：
1. 已使用 `batch_xxx` 的家族，後續維持前綴模式
2. 已使用 `_batch` 的家族，後續維持後綴模式
3. 不要在同一家族混用 `batch_identify_studio` 與 `identify_studios_batch`

## 跨語言映射規則

### 規則

1. Python 使用 `snake_case`
2. Go 使用 `PascalCase` 或語言慣例
3. JSON 使用 `snake_case`
4. 文件中以主名稱作為第一語意來源

### 範例

Python：
`get_video_stats`

Go：
`GetVideoStats`

JSON：
`video_stats`

### 映射要求

1. 名稱必須可一眼對照
2. 不要在不同語言層使用不同動詞
3. 不要讓 Python 叫 `identify`，Go 叫 `Detect`，JSON 叫 `match_result`

## 命名反模式

### 模糊名稱

避免：
1. `data`
2. `info`
3. `thing`
4. `object`
5. `item_data`

### 無語意縮寫

避免：
1. `cfg2`
2. `tmp_obj`
3. `rslt`
4. `mgr_new`

### 過長名稱

避免把所有條件硬塞進名稱。

不建議：
`get_list_of_videos_filtered_by_studio_and_date_range`

建議：
`query_videos`

說明：把條件放在參數，不放在函式名。

### 同義動詞並存

避免：
1. `get_video` 與 `fetch_video` 指同一行為
2. `identify_studio` 與 `detect_studio` 指同一行為
3. `delete_video` 與 `remove_video` 指同一行為

### 臨時命名流入正式 API

避免：
1. `new_manager`
2. `result2`
3. `temp_result`
4. `final_final_data`

## 專案覆寫規則

本 Skill 只定義通用命名原則，不直接綁定專案術語。

若專案有領域固定詞彙，應由專案 Skill 補充，例如：
1. 哪個詞代表主資料物件
2. 哪個詞代表識別碼
3. 哪個詞代表外部來源
4. 哪個批次命名家族為專案標準

若通用 Skill 與專案 Skill 衝突：
1. 動詞規則以通用 Skill 為準
2. 領域名詞以專案 Skill 為準
3. JSON 對外欄位穩定性優先於局部重構偏好

## 自檢清單

在提交前檢查：
1. 這個新名稱是否與既有主名稱衝突
2. 這個動詞是否符合 API 動詞規則
3. Python、Go、JSON 三層是否可明確映射
4. 批次介面是否與單筆介面成對
5. 是否出現模糊名稱或臨時命名
6. 是否把專案術語硬寫進通用規則
7. 文件、測試、程式碼是否使用同一主名稱

## 與現有 Skill 的搭配方式

1. 與 `code-review` 搭配：審查問題時用本 Skill 判定命名是否偏離標準
2. 與 `go-bridge-development` 搭配：檢查 Python、Go、JSON 的命名對齊
3. 與 `documentation-guide` 搭配：確保文件中的 API 名稱與實作名稱一致
4. 與專案 Skill 搭配：由專案 Skill 補上特定領域詞與既有名詞表

## 相關文件

1. 專案術語請參考對應專案 Skill
2. 命名審查可搭配 `code-review` Skill
3. 橋接層對照可搭配 `go-bridge-development` Skill
4. 文件命名與 API 描述可搭配 `documentation-guide` Skill