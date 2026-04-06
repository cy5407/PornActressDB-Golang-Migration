# 命名規範

> 來源：`CODING_STANDARDS.md`（完整版）  
> 適用：Python、Go、JSON、CLI、API、橋接層  
> 更新：2026-04-06

---

## 核心原則

### 主名稱唯一化
每個概念只能有一個主名稱。若既有名稱已存在，新程式碼沿用；若要換名，整體重構，不允許並存。

### 一致性 > 個人偏好
命名的第一原則是讓整個專案在閱讀、搜尋、維護時保持穩定。

### 動詞不可混用
同一操作意圖只用一個動詞：
- 已用 `identify_studio` 就不新增 `detect_studio`
- 已用 `list_videos` 就不新增 `get_video_list`

---

## Python 命名規則

| 類型 | 規則 | 範例 |
|------|------|------|
| 類別 | PascalCase | `GoBridge`、`ConfigManager` |
| 函式/方法 | snake_case | `scan_directory`、`identify_studio` |
| 變數 | snake_case | `input_dir`、`search_results` |
| 常數 | UPPER_SNAKE_CASE | `DEFAULT_TIMEOUT`、`MAX_CONCURRENT` |
| 私有成員 | 前置底線 | `_run_command`、`_parse_json` |
| 測試函式 | `test_` 開頭 + 描述行為 | `test_identify_studio_fallback_on_bridge_error` |

---

## Go 命名規則

| 類型 | 規則 | 範例 |
|------|------|------|
| 匯出符號 | PascalCase | `ScanResult`、`BatchMove` |
| 私有符號 | 小寫開頭 | `cleanupIndex`、`parseCode` |
| Package | 簡短小寫，無底線 | `extractor`、`database`、`studio` |
| Receiver | 簡短有語意 | `db`、`mover`、`extractor` |
| 錯誤 | `ErrXxx` | `ErrNotFound`、`ErrInvalidCode` |

---

## JSON / Schema 命名規則

- 所有對外欄位：`snake_case`（`file_path`、`created_at`）
- 布林欄位：`is_`、`has_`、`can_` 開頭（`is_available`、`has_cache`）
- 時間欄位：`created_at`、`updated_at`、`last_search_date`
- 識別欄位：`code`（外部業務識別碼）、`id`（內部唯一識別，舊版相容）

---

## API 動詞規則

| 動詞 | 用途 | 範例 |
|------|------|------|
| `get_xxx` | 取得單一物件（已知唯一鍵） | `db_get_video` |
| `list_xxx` | 列出多筆（無模糊搜尋） | `db_list_videos` |
| `query_xxx` | 條件查詢（條件可能擴充） | `query_videos` |
| `search_xxx` | 模糊搜尋或外部搜尋 | `search_video_info` |
| `identify_xxx` | 規則判斷/推論 | `identify_studio` |
| `create_xxx` | 建立全新物件 | — |
| `add_xxx` | 加入既有集合 | `add_or_update_video` |
| `update_xxx` | 更新既有物件 | `db_update_video` |
| `delete_xxx` | 刪除既有物件 | `db_delete_video` |
| `compact_xxx` | 合併/壓縮狀態 | `db_compact_journal` |
| `normalize_xxx` | 標準化輸出格式 | — |

---

## 橋接層前綴規則

若函式明確綁定某個 Go CLI 子命令家族，在動詞前加穩定領域前綴：

```python
# ✅ 正確：db 家族
db_get_video
db_update_video
db_compact_journal
db_fix_studios

# ❌ 錯誤：不一致
db_get_video  vs  database_get_stats  # 同一家族兩種前綴
```

---

## 批次命名規則

批次命名跟隨既有 API 家族慣例：

```python
# 後綴 _batch 家族（已有 identify_studio）
identify_studio → identify_studios_batch

# 前綴 batch_ 家族（已有 move_file）
move_file → batch_move

# 同一模組不得同時出現兩種寫法
```

---

## CLI 命名規則

- 子命令：短、明確、不重疊（`scan`、`move`、`db`、`identify`、`cache`）
- 旗標：語意明確，避免同義旗標並存
- 既有旗標慣例：`-dir`、`-src`、`-dst`、`-batch`（保持向後相容）
- `--json` flag：Go 子命令必須宣告此 flag，即使 no-op（Python 固定傳送）

---

## 跨語言對應

| Python | Go | JSON |
|--------|-----|------|
| `get_video_stats` | `GetVideoStats` | `video_stats` |
| `db_get_stats` | `db stats`（CLI）| `journal_size` |
| `identify_studio` | `IdentifyStudio` | `studio` |

---

## 反模式

| 反模式 | 說明 |
|--------|------|
| `data`、`info`、`thing` | 模糊名稱 |
| `result2`、`temp_result` | 臨時名稱流入正式 API |
| `get_video` 與 `fetch_video` 並存 | 同義動詞混用 |
| `get_list_of_videos_filtered_by_...` | 過長名稱（條件放參數，不放函式名） |
| `cfg2`、`rslt` | 縮寫濫用 |

---

## 提交前 Checklist

- [ ] 是否引入第二個主名稱？
- [ ] 是否違反 API 動詞規則？
- [ ] 是否與既有模組名稱不一致？
- [ ] JSON 欄位是否可穩定映射？
- [ ] 是否需要同步更新文件與測試？

---

## 相關頁面

- [wiki/patterns/add-go-api-function.md](add-go-api-function.md)
- [wiki/pitfalls/go-api-export-missing.md](../pitfalls/go-api-export-missing.md)
