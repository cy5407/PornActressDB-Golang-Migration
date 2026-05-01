# Rust Shadow DB 改善 Implementation Plan

> **建立日期**：2026-05-01
> **修訂**：Rev 2（Rev 1 後再經 review 修正：Task 3 排序語意、Task 4 prepare 退讓策略與 restore 測試方式、Task 5 版本檢查順序、Task 7 `black_box` 引用、實測結果同步寫入 plan）。Rev 1 主要變更：Task 8 不碰 Go、補 v1 schema 防護、效能驗收放寬為記錄不設硬門檻、benchmark 同時輸出 cold/warm、任務順序重排為「先正確性、再 schema、最後效能」
> **目標分支**：`codex/rust-adn-db-branch`
> **工作目錄**：`tools-rs/` 與 `scripts/`
> **前置依賴**：分支已合入 `71fac70 add rust sqlite shadow db` 與 `9be4357 Document SQLite shadow DB commands`

**Goal:** 修正 `tools-rs/db-tool` 第一版的正確性缺口、移除設計浪費、並讓 shadow SQLite 成為 `classifier db compact` 後**手動執行的驗證流程**（不是自動 gate，本計畫不接 CI、不改 Go CLI）。

**Architecture:** 維持「SQLite 是衍生物，不是 source of truth」的原始定位。所有改動都在 `tools-rs/` 內部與 `scripts/db-sync.ps1` + 文件。Go classifier、Python `src/`、Wails `wails-app/` 完全不動，避免在這份 plan 內把「Go-only 邊界」與「Rust shadow tool」的責任揉在一起。

**Tech Stack:** Rust 2021 (`anyhow`, `clap`, `rusqlite` bundled, `serde_json`, `time`), PowerShell 5.1+

---

## 執行邊界

- 只修 `tools-rs/`、`scripts/db-sync.ps1`、`docs/tools-rs-sqlite-shadow-db.md`、`docs/sqlite-shadow-db-commands.md`
- **不動 `cmd/scanner/` 與任何 Go 程式碼**。Go classifier 是否該在 `db compact` 後印同步提示，另開獨立 plan 評估
- 不動 Python `src/` 與 Wails `wails-app/`
- 不引入新的 Cargo dependency。`tempfile` 已在 dev-dependencies，需要更多測試輔助時優先用標準庫
- 不重寫 schema 大架構；本計畫只允許 schema v1 → v2 的單次 bump（理由：拿掉 `raw_json`），且明確走 rebuild-only 升級路徑

## 工作樹注意事項

目前 worktree 位於 `C:\Users\cy5407\.codex\worktrees\72b7\PornActressDB-Golang-Migration`。所有 `cargo` 命令都帶 `--manifest-path tools-rs\Cargo.toml`，不要 `cd` 進去再回來，避免相對路徑混淆。

`data\shadow.sqlite` 是衍生物且在 `.gitignore`，每次測試前可直接刪除重建。`data\json_db\data.json`（約 2.3MB，**實測 3363 筆 video**）為實際資料，**任何整合測試只能讀取，不能寫入**。注意：本計畫所有效能討論都基於這個量級，不要把任何「百分比降低」當成必過驗收條件（見 Task 4）。

## 檔案責任

- Modify: `tools-rs/src/json_db.rs`
  - 修掉 dead code（Task 1）
  - 拿掉 `raw_json` 在 `VideoRow` 上的承載（Task 5 配套）
  - `parse_actresses` 統一規則：`actresses` 改成依 ordinal 順序去重（Task 3 配套）
- Modify: `tools-rs/src/sqlite_db.rs`
  - schema 拿掉 `raw_json` 欄位、`SCHEMA_VERSION` bump 到 2（Task 5）
  - 新增 v1/v2/未知版本的防呆檢查（Task 5 配套）
  - import 改成 prepare-once reuse（優先 `prepare_cached`，必要時 fallback 到 `tx.prepare`）（Task 4）
  - bulk import PRAGMA 開關 + try/finally restore（Task 4）
  - replace 模式跳過 per-row delete（Task 6）
  - load actresses 時讀 `ordinal`（Task 3）
- Modify: `tools-rs/src/commands.rs`
  - `compare_rows` 補 9 個欄位的 mismatch 檢查（Task 2）
  - `compare_rows` 比對 ordinal 排序的 actress_items（Task 3）
  - `db-benchmark` 改成 cold + warm 雙量測，輸出新 key（Task 7）
- Modify: `tools-rs/src/main.rs`
  - 若 Task 5 的 v1 防護需要新增 CLI 行為（例如統一 error 訊息），只在這層做最小調整
- Modify: `scripts/db-sync.ps1`
  - 新增 `-Quiet` 旗標，方便整合呼叫（Task 8）
- Modify: `docs/tools-rs-sqlite-shadow-db.md`
  - 同步 schema 變更（拿掉 `raw_json`）、新增 `cargo clippy` 到驗收清單、補 benchmark 公平性說明（Task 5、7 配套）
- Modify: `docs/sqlite-shadow-db-commands.md`
  - 補「先刪舊 shadow.sqlite 才能升 v2」warning、`-Quiet` 用法、提醒 compact 後手動跑 `db-sync.ps1`（Task 5、8 配套）

---

### Task 1: 修掉 `video_from_value` 的 dead code

**Files:**
- Modify: `tools-rs/src/json_db.rs` (L86-L128)
- Modify: `tools-rs/src/json_db.rs` (新增測試)

**問題定位：**

```rust
// json_db.rs:124-127 — 兩條 branch 回傳完全相同
if row.code != map_key.trim() && !map_key.trim().is_empty() {
    return Ok((row, duplicate_count));
}
Ok((row, duplicate_count))
```

兩條 branch 都回傳 `Ok((row, duplicate_count))`，條件判斷沒有任何作用。從上下文看，原意應該是「map key 與 video.code 不一致時記為 invalid」，但寫一半沒寫完。

**決策：** 採「key/code 不一致時回 invalid，並用 map_key 當作 invalid record 的 key」這個語意。理由是 `data.json` 的 video map 約定是 `{ "<code>": { "code": "<code>", ... } }`，key 與內部 code 不一致代表資料寫入有 bug，應該被抓出來而不是默默匯入。

- [x] 修改 `video_from_value` 簽名，回傳 `Result<(VideoRow, usize), String>`（從 `&'static str` 改成 `String`，以便包含實際的 key/code 值）
- [x] code 為空、record 不是 object 等既有錯誤訊息保持原語意，只是字串型別改成 `String`
- [x] 新增「map_key 與 row.code 不相等」的 error path，訊息範例：`"map key \"ABC-123\" does not match record code \"DEF-456\""`
- [x] `load_json_rows` 的 caller 端不需改動（已經處理 `Err` → `invalid` push）
- [x] 補 unit test：fixture 用 `{ "WRONG-KEY": { "code": "RIGHT-CODE", ... } }`，斷言 `rows.invalid.len() == 1` 且 `rows.invalid[0].reason` 同時包含 `WRONG-KEY` 與 `RIGHT-CODE`

**Acceptance criteria:**

- `cargo clippy --manifest-path tools-rs/Cargo.toml -- -D warnings` 不再報 dead code
- 新測試通過
- 既有 `load_json_rows_uses_id_fallback_and_tracks_duplicate_actresses` 測試仍通過（既有 fixture 的 key 與 code 都是 `"A"`，不受影響）

---

### Task 2: `compare_rows` 補其餘 9 個字串欄位比對（合計覆蓋 11 個 video 字串欄位）

**Files:**
- Modify: `tools-rs/src/commands.rs` (L142-L200)
- Modify: `tools-rs/src/commands.rs` (新增測試)

**問題定位：**

`compare_rows` 目前只比對 `title / studio / actresses` 三個欄位。`VideoRow` 上的其他 9 個欄位（`release_date, url, search_status, search_method, last_search_date, created_at, updated_at, original_filename, file_path`）寫入若漂移，compare 不會抓到。`db-compare-json` 名為「等價保證」，實際只覆蓋少數欄位，名實不符。

**決策：** 補完所有字串欄位的比對。維持既有 `FieldMismatch { code, field, json, sqlite }` 結構，欄位名稱用 snake_case 與 JSON DB 一致。

- [x] 在 `commands.rs` 抽出小 table，避免重複呼叫 `push_string_mismatch`：

  ```rust
  const COMPARED_STRING_FIELDS: &[(&str, fn(&VideoRow) -> &str)] = &[
      ("title", |r| &r.title),
      ("studio", |r| &r.studio),
      ("release_date", |r| &r.release_date),
      ("url", |r| &r.url),
      ("search_status", |r| &r.search_status),
      ("search_method", |r| &r.search_method),
      ("last_search_date", |r| &r.last_search_date),
      ("created_at", |r| &r.created_at),
      ("updated_at", |r| &r.updated_at),
      ("original_filename", |r| &r.original_filename),
      ("file_path", |r| &r.file_path),
  ];
  ```

- [x] `compare_rows` for-loop 內遍歷這個表，不再個別 hard-code
- [x] 補 unit test：建構 JSON / SQLite 兩個 `BTreeMap`，每個欄位故意各製造一筆 mismatch，斷言 `report.success == false` 且 `report.field_mismatches` 數量正確、`field` 名稱齊全
- [x] 補 unit test：所有欄位都相等時 `report.success == true` 且 `field_mismatches` 為空

**Acceptance criteria:**

- 跑一次真實 `data.json` 的 `db-compare-json`，輸出仍是 `success: true`（代表既有資料在新欄位上沒漂移）
- 故意改 SQLite 中某筆 video 的 `release_date`，compare 應該回 `success: false` 並列出該 mismatch
- 新測試通過

---

### Task 3: 驗證 actress 的 ordinal 順序

**Files:**
- Modify: `tools-rs/src/json_db.rs` (`parse_actresses` L139-L162)
- Modify: `tools-rs/src/sqlite_db.rs` (L207-L268)
- Modify: `tools-rs/src/commands.rs` (`compare_rows`)
- Modify: `tools-rs/src/commands.rs` (新增測試)

**問題定位：**

`load_rows_from_conn:230` 直接把 `actress_items` 設為 `Vec::new()`，所以 SQLite 端 `actress_items` 永遠是空。compare 只比對 alphabetical-sorted 的 `actresses: Vec<String>`，ordinal 寫錯也抓不到。但 SQL view `videos_with_actresses` 用 `ORDER BY ordinal` 拼字串輸出，ordinal 寫錯會直接污染 view 的觀感。

**決策：** SQLite 端載入時也填 `actress_items`（含 ordinal），compare 時加上 `actress_items` 內容比對（依 `(name, ordinal)` 排序後比較，避免插入順序假陽性）。**附帶統一規則：** 兩邊 `actresses` 都改成依 ordinal 順序去重（保留第一次出現的位置），不再用 alphabetical。

- [x] `load_all_actresses` 改成回傳 `BTreeMap<String, Vec<ActressItem>>`，SQL 加上 `ordinal` 欄位：

  ```sql
  SELECT video_code, actress_name, ordinal
  FROM video_actresses
  ORDER BY video_code, ordinal, actress_name
  ```

- [x] `load_rows_from_conn` 同時填 `actresses`（按 ordinal 順序的去重 `Vec<String>`）與 `actress_items`
- [x] `parse_actresses` 同步改：把 `let actresses = seen.into_iter().collect()` 改成 `let actresses = actress_items.iter().map(|i| i.name.clone()).collect()`，與 SQLite 端一致
- [x] `compare_rows` 在現有 actress set 比對通過後，加一段 `actress_items` 比對。比對前先把兩邊 `sort_by` `(name, ordinal)`。**排序的目的是消除插入順序造成的假陽性，不是消除 ordinal 差異**：同名但 ordinal 不同仍應被視為 mismatch（因為這代表 `videos_with_actresses` view 的拼字串輸出會不同）
- [x] 補 unit test：SQLite 與 JSON 的 actress 名字相同但 ordinal 不同，斷言 compare 抓到 `field: "actress_items"` 的 mismatch
- [x] 補 unit test：`load_rows_from_conn` 的 `actresses` 順序為 ordinal 順序（驗證新一致性規則）

**Acceptance criteria:**

- 真實 `data.json` 跑 `db-import-json` + `db-compare-json` 為 `success: true`
- 既有 `import_and_load_rows_without_n_plus_one_shape` 測試需要更新預期：`loaded["A"].actresses` 順序由 ordinal 決定（測試 fixture 是 `[Alice ord=0, Bob ord=2]`，所以仍是 `["Alice", "Bob"]`，巧合通過，需在註解標明依賴 ordinal 而非字典序）
- 既有 `duplicate_actresses_do_not_fail_compare` 測試仍通過

---

### Task 5: 拿掉 `raw_json` 欄位、schema bump 到 v2、加入版本防護

**Files:**
- Modify: `tools-rs/src/sqlite_db.rs` (schema、import、load、版本檢查)
- Modify: `tools-rs/src/json_db.rs` (`VideoRow` struct 與 `video_from_value`)
- Modify: `tools-rs/src/commands.rs` (compare 測試 fixture)
- Modify: `tools-rs/src/main.rs` (若需統一 error 訊息)
- Modify: `docs/tools-rs-sqlite-shadow-db.md` (schema 段落同步)
- Modify: `docs/sqlite-shadow-db-commands.md` (補升級警告)

**問題定位：**

`raw_json` 欄位每筆 video 都存一份完整原始 JSON，但程式中沒有任何 reader：`compare_rows`、`stats`、`videos_with_actresses` view 都不讀。對 ~3363 筆 / 2.3MB JSON 來說，SQLite 體積至少多一倍，且 `videos.raw_json TEXT NOT NULL` 是不可空的，import 時還要序列化一次（`serde_json::to_string`）。

同時，schema bump 後若使用者拿舊 v1 DB 直接跑 v2 工具，會出現「import 成功但欄位對應錯亂」的悄然錯誤。需要主動防護。

**決策：**

1. 拿掉 `raw_json`，`SCHEMA_VERSION` 從 `1` 升到 `2`
2. **rebuild-only 升級路徑**：本計畫不寫 in-place migration，理由是 SQLite 對 DROP COLUMN 支援差，rebuild 較乾淨。`db-init --replace` 是唯一升級方式
3. **v1/未知版本主動防呆**：`db-init` 與 `db-import-json` 開頭都讀 `PRAGMA user_version`，依下表處理。**版本檢查必須只讀 `PRAGMA user_version`，不得執行任何假設 v2 schema 的 SQL（例如 SELECT 新欄位、查 view 結構）**。v1 + `--replace` 路徑允許直接 drop 後重建，**不要先 query 欄位確認結構**：

   | `user_version` | 行為 |
   |---|---|
   | `0`（全新檔，沒跑過 init） | 照常建 v2 |
   | `2` | 照常 |
   | `1` 且有 `--replace` | 照常 drop 重建（既行為） |
   | `1` 且無 `--replace` | error：`"shadow DB is schema v1, run with --replace to rebuild as v2 (or delete data\\shadow.sqlite)"` |
   | 其他（≥3 或負數） | error：`"unknown shadow DB schema version: <n>. expected 0/1/2"` |

   `db-import-json` 也必須檢查（不能只在 `db-init` 檢查），否則使用者跳過 init 直接 import 仍會中招

- [ ] `init_schema` 的 `videos` table DDL 移除 `raw_json TEXT NOT NULL`
- [ ] `init_schema` 的 `DROP TABLE` 順序與內容不變
- [ ] `SCHEMA_VERSION` 常數從 `1` 升到 `2`
- [ ] 新增 `pub fn ensure_schema_compatible(conn: &Connection, replace: bool) -> Result<()>`，包含上表邏輯，回傳 `anyhow::Error` with 上述訊息
- [ ] `db_init` 在 `init_schema` 前呼叫 `ensure_schema_compatible(&conn, replace)`
- [ ] `db_import_json` 在 `import_rows` 前先 `open_db` 一次呼叫 `ensure_schema_compatible(&conn, replace)`，再丟回原本的流程
- [ ] `import_rows` 的 INSERT 拿掉 `raw_json` 欄位與對應 param
- [ ] `load_rows_from_conn` 的 SELECT 與 `query_map` 拿掉 `raw_json`
- [ ] `VideoRow` struct 拿掉 `raw_json: String` 欄位
- [ ] `video_from_value` 拿掉 `serde_json::to_string(value)` 那一行與對應 error path
- [ ] 所有測試 fixture 拿掉 `raw_json: "{}".to_string()`
- [ ] 補 unit test：v1 DB（手動建 `PRAGMA user_version = 1`）+ 無 `--replace` → `db_init` 應 error
- [ ] 補 unit test：v1 DB + `--replace` → `db_init` 應成功且 `user_version` 變成 2
- [ ] 補 unit test：v3 DB（手動 `PRAGMA user_version = 3`）→ 不論 `--replace` 與否都應 error
- [ ] 補 unit test：`db_import_json` 對 v1 DB 無 `--replace` 也應 error（驗證 import 不可繞過）
- [ ] `docs/tools-rs-sqlite-shadow-db.md` 的 schema SQL 段落同步移除 `raw_json` 並補一句「`raw_json` 已於 v2 schema 移除，理由：未被任何 reader 使用，且導致 DB 體積翻倍」
- [ ] `docs/sqlite-shadow-db-commands.md` 補 warning：「升級到 v2 schema 後，舊的 `data\shadow.sqlite` 必須刪除或用 `--replace` rebuild。工具會在偵測到 v1 DB 時直接 error，不做 in-place migration」

**Acceptance criteria:**

- `cargo test` 全部通過（修改後的 fixture 不再有 `raw_json`）
- 真實 `data.json` 重新 import 後，`data\shadow.sqlite` 體積有可量測下降（記錄改前/改後數字於 commit message **與本 plan 的「實測結果」段落**，**不設絕對門檻**）
- `db-stats` 輸出的 `schema_version: 2`
- 手動測試 v1 防呆四個情境（init/import × replace/無 replace）行為與上表一致

---

### Task 4: import 改用 `prepare_cached` 並調 PRAGMA（含 try/finally restore）

**Files:**
- Modify: `tools-rs/src/sqlite_db.rs` (L126-L205, `import_rows`)
- Modify: `tools-rs/src/sqlite_db.rs` (新增 helper `apply_bulk_pragmas` / `restore_pragmas`)

**問題定位：**

`import_rows` 的 for-loop 內每筆 row 都 `tx.execute(SQL_STRING, ...)`，rusqlite 每次都重新 prepare（在 ~3363 筆規模上 ≈ 萬次量級的 prepare）。同時 SQLite 預設 `synchronous = FULL` + `journal_mode = DELETE`，bulk write 時磁碟同步成本高。

**決策：**

1. 把 3 條 SQL 各 prepare **一次**，loop 內只 `bind` + `execute`。**優先用 `tx.prepare_cached(...)`**；若該 API 在 `Transaction` 上行為與預期不符（例如 cache scope 限制），退回到 `tx.prepare(...)` 在 loop 外手動 prepare 並重用 statement handle。重點是消除「每筆 row 重新 prepare」的 overhead，不一定非得是 cached 版本
2. 在 transaction 開始前暫時設定 `PRAGMA synchronous = OFF` 與 `PRAGMA journal_mode = MEMORY`，import 結束後 restore 回 `synchronous = NORMAL` 與 `journal_mode = DELETE`
3. **restore 路徑必須堅固**：用手寫 try/finally 模式（不引入 `scopeguard`），原始 bulk error 永遠優先，restore error 只在 bulk 成功時才能讓整體失敗

**PRAGMA restore 處理樣板：**

```rust
let bulk_result: Result<usize> = (|| -> Result<usize> {
    let tx = conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
    // ... loop with prepared statements, commit ...
    Ok(actress_link_count)
})();

let restore_result = restore_pragmas(&conn);

match (bulk_result, restore_result) {
    (Ok(n), Ok(())) => Ok(n),
    (Err(e), Ok(())) => Err(e),
    (Ok(_), Err(e)) => Err(e.context("bulk import 成功但 PRAGMA restore 失敗")),
    (Err(e), Err(restore_e)) => {
        Err(e.context(format!(
            "bulk import 失敗，且 PRAGMA restore 也失敗: {restore_e}"
        )))
    }
}
```

**重點：** bulk 失敗時，原始錯誤是主訊息，restore 錯誤只放 context；不能反過來蓋掉 bulk 的 root cause。

- [ ] 新增 `fn apply_bulk_pragmas(conn: &Connection) -> Result<()>` 設定 `synchronous = OFF`、`journal_mode = MEMORY`
- [ ] 新增 `fn restore_pragmas(conn: &Connection) -> Result<()>` 設定 `journal_mode = DELETE`、`synchronous = NORMAL`
- [ ] 注意：`journal_mode` 不能在 transaction 內變更，要在 `transaction()` **之前**設定
- [ ] `import_rows` 改成上述 try/finally 樣板；bulk 區塊內 3 條 SQL 改成 prepare-once-reuse（優先 `tx.prepare_cached`，必要時 fallback 到 loop 外 `tx.prepare`）
- [ ] for-loop 內三條 statement（video insert、actress delete、actress insert）只 `bind` + `execute([])`，不再傳 SQL 字串
- [ ] 把 4-arm match 邏輯抽成純 helper，例如：

  ```rust
  fn merge_bulk_and_restore(
      bulk: Result<usize>,
      restore: Result<()>,
  ) -> Result<usize> { /* 4 arms */ }
  ```

  對該 helper 寫純函式 unit test 覆蓋 4 種組合（Ok/Ok、Err/Ok、Ok/Err、Err/Err），驗證原始 bulk error 不會被 restore error 蓋掉。**不為了測試硬加 mock 架構**
- [ ] 補 unit test（成功路徑）：import 完成後，獨立開新連線檢查 `PRAGMA journal_mode == "delete"`、`PRAGMA synchronous == 1`（NORMAL）
- [ ] 跑一次 `cargo test --manifest-path tools-rs/Cargo.toml`（確認既有測試仍通過）
- [ ] 跑一次 `db-benchmark` 對比改前改後的 import 耗時，記錄在 commit message **與本 plan 的「實測結果」段落**

**Acceptance criteria:**

- 既有 `import_and_load_rows_without_n_plus_one_shape` 測試通過
- 真實 `data.json` 的 import **耗時記錄於 commit message**（改前/改後數字各列一行）。**不設百分比門檻**
- 若改後反而明顯變慢，需在 commit message 或 PR 說明原因（例如：~3363 筆規模下 prepare overhead > savings）；無正當理由則應 revert
- import 完成後，獨立開新連線檢查 `PRAGMA journal_mode == "delete"`、`PRAGMA synchronous == 1`（驗證 restore 沒漏）

---

### Task 6: replace 模式跳過 per-row delete

**Files:**
- Modify: `tools-rs/src/sqlite_db.rs` (`import_rows` for-loop)

**問題定位：**

`import_rows` 在 `replace=true` 時，先 `DELETE FROM videos / video_actresses` 全表清空（L137-L139），然後 for-loop 內每一筆又執行：

```rust
tx.execute("DELETE FROM video_actresses WHERE video_code = ?1", params![row.code])?;
```

全表已空，這個 per-row delete 找不到任何東西可刪，純粹浪費。在非 replace 模式（增量更新場景）這個 delete 才有意義（清掉舊 actress link 再插新的）。

**決策：** for-loop 內的 per-row delete 改成 `if !replace` 才執行。配合 Task 4 的 `prepare_cached`，這條 statement 也已是 cached，只是省掉執行。

- [ ] `import_rows` 簽名不變
- [ ] for-loop 內把：

  ```rust
  tx.execute("DELETE FROM video_actresses WHERE video_code = ?1", params![row.code])?;
  ```

  改成：

  ```rust
  if !replace {
      delete_actresses_stmt.execute(params![row.code])?;
  }
  ```

- [ ] 補 unit test：在現有 DB 中先 import 一次（含 actress），再用 `replace=false` 重新 import 同一筆 video 但 actress 換成不同名字，斷言新 actress 取代舊 actress（驗證非 replace 模式仍正確）
- [ ] 補 unit test：在現有 DB 中先 import 一次，再用 `replace=true` 重新 import 完全不同 video set，斷言舊資料完全消失（驗證 replace 模式仍正確）

**Acceptance criteria:**

- 兩個新 unit test 通過
- 真實 `data.json` 跑 `db-sync.ps1`（內部用 `--replace`），結束後 `db-compare-json` 為 `success: true`

---

### Task 7: `db-benchmark` 改成 cold + warm 雙量測

**Files:**
- Modify: `tools-rs/src/commands.rs` (L100-L140, `db_benchmark`)
- Modify: `docs/tools-rs-sqlite-shadow-db.md` (`db-benchmark` 段落補說明)

**問題定位：**

`db-benchmark` 的兩種 SQLite 測試節奏不一致：`load_sqlite_rows` 每次 iteration 都 `open_db` 新連線（cold），`stats_from_conn` 連線在 loop 外（warm）。讀者看到 `sqlite_total_ms` vs `sqlite_stats_total_ms` 的差異會誤以為純粹是查詢效能差距，實際上有一部分是連線建立成本差距。

**決策：** 不把 SQLite 改成「只測 warm」，而是同時輸出 cold + warm 兩組數字，並把 `open_db × N` 的累計時間獨立量測，讀者自己看哪個對自己使用情境更接近。**直接 break** 舊的 `sqlite_total_ms` key（不保留別名），用更明確的命名取代。

**新輸出 schema：**

| key | 語意 |
|---|---|
| `iterations` | 不變 |
| `json_rows` / `sqlite_rows` | 不變 |
| `json_total_ms` | JSON cold-read + parse × N（不變） |
| `sqlite_cold_total_ms` | 每輪 `open_db` + full load × N |
| `sqlite_warm_total_ms` | 單一 connection + full load × N |
| `sqlite_stats_total_ms` | 單一 connection + stats query × N |
| `sqlite_open_overhead_ms` | 只量 `open_db` × N |

- [ ] `db_benchmark` 內把原本 SQLite full load 拆成兩段：

  ```rust
  // Cold：每輪重開連線
  let sqlite_cold_start = Instant::now();
  for _ in 0..iterations {
      let rows = sqlite_db::load_sqlite_rows(sqlite_path)?;
      sqlite_rows = rows.len();
      std::hint::black_box(sqlite_rows);
  }
  let sqlite_cold_total_ms = sqlite_cold_start.elapsed().as_millis();

  // Warm：共用單一連線
  let conn = sqlite_db::open_db(sqlite_path)?;
  let sqlite_warm_start = Instant::now();
  for _ in 0..iterations {
      let rows = sqlite_db::load_rows_from_conn(&conn)?;
      sqlite_rows = rows.len();
      std::hint::black_box(sqlite_rows);
  }
  let sqlite_warm_total_ms = sqlite_warm_start.elapsed().as_millis();
  ```

- [ ] 新增 open overhead 量測：

  ```rust
  let open_start = Instant::now();
  for _ in 0..iterations {
      let conn = sqlite_db::open_db(sqlite_path)?;
      std::hint::black_box(&conn);
  }
  let sqlite_open_overhead_ms = open_start.elapsed().as_millis();
  ```

- [ ] 拿掉舊的 `sqlite_total_ms` key
- [ ] `docs/tools-rs-sqlite-shadow-db.md` 的 `db-benchmark` 段落補一段：

  > **語意說明**：
  > - `json_total_ms`：JSON 每輪 cold-read + parse，這就是 JSON DB 的真實讀取成本
  > - `sqlite_cold_total_ms`：每輪重開連線 + load，模擬「短命 CLI 一次性查詢」情境
  > - `sqlite_warm_total_ms`：共用連線 + load，模擬「常駐 process 持續查詢」情境
  > - `sqlite_stats_total_ms`：共用連線 + stats query
  > - `sqlite_open_overhead_ms`：純 `open_db` × N，用來分離連線建立成本

**Acceptance criteria:**

- `cargo test` 全部通過
- 真實 `data.json` + `data\shadow.sqlite` 跑 `db-benchmark --iterations 10`，輸出包含全部 4 個新 SQLite key、不包含舊 `sqlite_total_ms`
- 改前 vs 改後的數字記錄在 commit message **與本 plan 的「實測結果」段落**（不設門檻）

---

### Task 8: `db-sync.ps1` 加 `-Quiet` + docs 提醒（不動 Go）

**Files:**
- Modify: `scripts/db-sync.ps1` (新增 `-Quiet` 參數)
- Modify: `docs/sqlite-shadow-db-commands.md` (流程段補手動同步提醒)

**問題定位：**

shadow DB 是衍生物，但目前**沒有任何地方會在 `data.json` 變動後提示使用者該重新同步**。流程文件裡寫「先 compact 再 db-sync」是約定，實際使用容易忘。如果 shadow DB 跟 `data.json` 不同步，`db-query.ps1` 查到的就是過期資料，會默默誤導使用者。

**決策（Path A，不動 Go）：**

- 本計畫**不改 Go classifier**，避免在這份 plan 把 Go-only 邊界與 Rust shadow tool 的責任揉在一起
- 只在 `scripts/db-sync.ps1` 加 `-Quiet` 旗標，方便將來整合到 wrapper script
- 在 `docs/sqlite-shadow-db-commands.md` 強化「compact 後應手動跑 `db-sync.ps1`」的提醒
- Go classifier 是否該在 compact 後印同步提示，**另開獨立 plan 評估**（不在本計畫範圍）

- [ ] `scripts/db-sync.ps1` 加 `[switch]$Quiet` 參數
- [ ] 套用到所有 `Write-Host`（不影響 `Write-Error`、`db-tool.exe` 自己的 stdout 仍照常輸出，呼叫端可自行 redirect）
- [ ] `docs/sqlite-shadow-db-commands.md` 的「同步 shadow SQLite」段落最前面加一段：

  > **重要**：`classifier db compact` **不會**自動同步 shadow DB。每次 compact 完成後，請手動執行 `scripts\db-sync.ps1` 重建 shadow SQLite。否則 `db-query.ps1` 查到的會是過期資料。
  >
  > `scripts\db-sync.ps1 -Quiet` 適合整合到自動化 wrapper（壓掉 `Write-Host`，但保留 `db-tool` 的 JSON 輸出與 `Write-Error`）。

**Acceptance criteria:**

- 手動跑 `scripts\db-sync.ps1 -Quiet`：除了 `db-tool.exe` 的 JSON 輸出之外，沒有任何 `Write-Host` 訊息
- 不用 `-Quiet` 的既有行為完全不變
- docs 變更包含明確的「不會自動同步」聲明

---

## 執行順序與相依性

依 review 拍板的順序（先正確性 → 再 schema → 最後效能）：

| 順序 | Task | 相依 | 預估範圍 |
|---|---|---|---|
| 1 | Task 1 dead code | — | 小（單檔 + 1 test） |
| 2 | Task 2 補 9 欄位比對 | — | 小 |
| 3 | Task 3 ordinal 驗證 | Task 2（同函式 `compare_rows`） | 中 |
| 4 | Task 5 拿掉 raw_json + schema v2 + v1 防護 | Task 1（dead code 先清掉） | 中（schema bump + 多檔 + 防護測試） |
| 5 | Task 4 prepare_cached + PRAGMA + restore | Task 5（共用同函式 `import_rows`） | 中 |
| 6 | Task 6 replace 跳 per-row delete | Task 4（共用 cached statement） | 小 |
| 7 | Task 7 benchmark cold/warm 拆分 | — | 小 |
| 8 | Task 8 docs + script `-Quiet` | — | 小（PowerShell + docs） |

**建議分成 5 個 commit：**

1. **Task 1**：dead code 修正（單獨 commit，方便 review）
2. **Task 2 + Task 3**：compare 補完整、ordinal 比對（同函式 `compare_rows` 一起改）
3. **Task 5**：schema v2 + raw_json 移除 + v1 防護（schema 變更獨立成一個 commit，方便 revert）
4. **Task 4 + Task 6**：import 效能 + replace 跳過（同函式 `import_rows` 一起改）
5. **Task 7 + Task 8**：benchmark 公平性 + docs/script（小修補一起出）

---

## 驗收清單（全部完成後逐項對照）

- [ ] `cargo fmt --manifest-path tools-rs/Cargo.toml --check` 無 diff
- [ ] `cargo clippy --manifest-path tools-rs/Cargo.toml -- -D warnings` 無 warning
- [ ] `cargo test --manifest-path tools-rs/Cargo.toml` 全部通過
- [ ] 刪除舊 `data\shadow.sqlite`，跑 `scripts\db-sync.ps1` 流程順利結束（compact → init → import → compare → 可選 benchmark）
- [ ] `db-stats` 輸出 `schema_version: 2`
- [ ] `db-stats` 輸出的 `actress_link_count` 與 import 時的 `actresses` 一致
- [ ] `db-compare-json` 對真實 `data.json` 回 `success: true`
- [ ] 故意改 SQLite 中某筆 `release_date`，compare 應該抓到 mismatch（驗證 Task 2）
- [ ] 故意改 SQLite 中某筆 actress 的 ordinal，compare 應該抓到 `field: "actress_items"` mismatch（驗證 Task 3）
- [ ] 手動測試 v1 schema 防呆四個情境（init/import × replace/無 replace），行為與 Task 5 對照表一致
- [ ] `data\shadow.sqlite` 體積改前/改後數字記錄於 Task 5 的 commit message **與本 plan「實測結果」段落**（**不設絕對門檻**）
- [ ] `db-import-json` 改前/改後耗時記錄於 Task 4 的 commit message **與本 plan「實測結果」段落**（**不設絕對門檻**；若明顯變慢需說明原因，無正當理由則 revert）
- [ ] `db-benchmark` 輸出包含 4 個新 SQLite key，不含舊 `sqlite_total_ms`
- [ ] `scripts\db-sync.ps1 -Quiet` 行為符合 Task 8 acceptance
- [ ] `docs/tools-rs-sqlite-shadow-db.md` 已同步：schema v2、`cargo clippy` 進入驗收順序、`db-benchmark` 語意說明
- [ ] `docs/sqlite-shadow-db-commands.md` 已同步：「先刪舊 shadow.sqlite」warning、`-Quiet` 用法、「compact 不會自動同步 shadow DB」聲明

---

## 實測結果

> 隨各 Task 完成後填入。同步寫入 commit message 是為了即時 review，寫入此段是為了 squash / rebase 後仍保留脈絡。
>
> 量測環境：worktree `C:\Users\cy5407\.codex\worktrees\72b7\PornActressDB-Golang-Migration`、`data\json_db\data.json` 約 2.3MB / 3363 筆 video。

### Task 4：`db-import-json` 耗時

| 量測 | 數字 | commit |
|---|---|---|
| 改前（baseline） | _待填_ | _待填_ |
| 改後（prepare-once + PRAGMA） | _待填_ | _待填_ |
| 結論 | _待填_ | — |

### Task 5：`data\shadow.sqlite` 體積

| 量測 | 數字 | commit |
|---|---|---|
| 改前（schema v1，含 `raw_json`） | _待填_ | _待填_ |
| 改後（schema v2，無 `raw_json`） | _待填_ | _待填_ |
| 結論 | _待填_ | — |

### Task 7：`db-benchmark` cold/warm 對比

| 量測（iterations = 10） | 改前 | 改後 |
|---|---|---|
| `json_total_ms` | _待填_ | _待填_ |
| `sqlite_total_ms`（舊 key，改後拿掉） | _待填_ | — |
| `sqlite_cold_total_ms` | — | _待填_ |
| `sqlite_warm_total_ms` | — | _待填_ |
| `sqlite_stats_total_ms` | _待填_ | _待填_ |
| `sqlite_open_overhead_ms` | — | _待填_ |
| commit | — | _待填_ |

---

## 不在本計畫範圍

明確排除（避免 scope creep），未來若要做需另開計畫：

- **Go classifier 在 `db compact` 後印同步提示**：本計畫已明確走 Path A，不動 Go。是否值得做另開獨立 plan 評估
- **CI / 自動 gate 化**：本計畫只做「手動驗證流程」。要把 `db-compare-json` 接 CI 或 wrapper 強制執行，是不同的決策
- **Bun 依賴整併**：`scripts/db-query.ps1` 改用 `db-tool query` 子命令取代 Bun。需要在 Rust 端設計 query subcommand 的 schema，工作量大，獨立評估
- **journal replay**：`tools-rs-sqlite-shadow-db.md:18` 標註為「第二階段」，不在本次
- **`db-export-json` 反向命令**：拿掉 `raw_json` 之後若需要從 SQLite 回推 JSON，再開計畫
- **整合到 `go_cli.py` / Wails backend**：shadow DB 維持衍生物定位，目前不需要被主流程呼叫
- **整合測試 fixture**：本計畫只補 unit test 與 commit message 內的手動驗收。完整 `tools-rs/tests/integration_db_tool.rs` 留待後續評估（fixture 體積、CI 跑時間等）
