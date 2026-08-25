# Task.md — Rust 原生重寫架構任務書

> 建立：2026-06-02  
> 位置：`rust-rewrite/`  
> 來源參考：`docs/ARCHITECTURE.md`、`wiki/architecture/database.md`、現有 Python 爬蟲入口  
> 目標：依照既有系統的業務邏輯與 Python 爬蟲契約，建立一個乾淨的 Rust-first 新架構。不是逐檔翻譯既有實作；Rust CLI 由本 Task 重新定義。

---

## 0. 核心假設

本任務預設要建立的是**新專案骨架**。新資料夾只複製 Python 爬蟲層，其餘 runtime、CLI、SQLite、掃描、搬移、history 全部由 Rust 從 0 建立。既有非 Python 程式只作為業務需求參考，不作相容目標、不搬移、不包裝。

Rust 新架構要原生支援 SQLite，SQLite 從第一天就是 runtime source of truth。**程式碼可以從 0 開始，資料不能從 0 開始**：現有 `data/db.sqlite` 的 SQLite v3 表、欄位與語意是資料銜接契約。JSON 只允許作為匯入來源、匯出快照或備援格式，不允許成為主要轉錄路徑，也不允許形成第二套 runtime DB、journal、shadow DB 或 compatibility fallback。

Python 只保留爬蟲層。Rust 透過 subprocess 呼叫既有 `src/scrapers/run_search.py` 與 `src/scrapers/run_batch_search.py`，解析其 stdout JSON / JSON Lines，然後由 Rust 寫入 SQLite。Python 不直接寫 Rust DB，也不再透過 Python wrapper 委派 DB/scan/move/history。

本重寫追求**業務邏輯一致**與**Python 爬蟲契約一致**。Rust CLI、資料夾命名、錯誤文字都可以重新設計；未被本 Task 寫成 contract 的舊行為不繼承。

---

## 1. 目標架構

目標系統分成四層：

```text
rust-rewrite/
  crates/
    domain/       # 核心型別、DTO、業務規則，不碰 IO
    db/           # SQLite schema、migration、repository
    scanner/      # 番號提取、檔案掃描
    mover/        # 檔案移動、衝突策略、操作歷史
    scraper/      # Python subprocess adapter，只接爬蟲 stdout
    app/          # use-case orchestration
    cli/          # 對外 CLI binary
  migrations/     # SQLite migration SQL
  tests/          # contract / integration tests
```

第一版 binary 名稱暫定為 `actress-rs.exe`。若後續要接 GUI，GUI 只能呼叫 `crates/app` 或 CLI，不得直接打 SQLite 私有表。

邏輯資料流固定為：

```text
使用者 / GUI / CLI
  -> Rust app service
  -> scanner / scraper / mover / db repository
  -> SQLite data/db.sqlite

Python crawler
  <- Rust subprocess 呼叫 run_search.py / run_batch_search.py
  -> stdout JSON / JSON Lines
  -> Rust scraper adapter parse
  -> Rust db repository 寫 SQLite
```

---

## 2. 不可違反的硬性規則

H1. Runtime source of truth 只有 SQLite：預設位置 `data/db.sqlite`，schema 由 Rust migration 管理。

H2. DB 資料銜接以現有 SQLite v3 contract 為基準。Rust 第一版必須能讀取或無損遷移現有 `data/db.sqlite`，不得要求使用者先把資料匯出成 JSON 再重新匯入。

H3. 不建立 Python DB fallback，不建立 JSON runtime store，不建立舊 runtime bridge。即使複製 Python 目錄，Rust runtime 也不得呼叫 `JSONDatabase` / `IncrementalJSONDB` / `go_cli.py` 的非爬蟲職責。

H4. Python 只允許執行爬蟲：`run_search.py`、`run_batch_search.py`、`src/services/web_searcher.py` 及其依賴。Rust 不呼叫 Python 的 DB、掃描、搬移、cache、history wrapper。

H5. Rust 端只有一套對外 DTO。不得為 CLI、DB、GUI、mover 各自建立 byte-identical 的平行 struct，再靠手寫轉換維持同步。

H6. SQLite schema 只能有一個 canonical 來源。第一版建議用 `migrations/0001_existing_v3.sql` 固定目前資料 contract，再用 `migrations/0002_rust_additions.sql` 做 Rust 需要的 additive 變更；不得同時維護一份 embedded schema 與另一份 migration schema。

H7. Python 爬蟲輸出 contract 必須由 Rust 測試鎖住：單筆 JSON 支援 `search_method` 與舊 `method`；批次 stdout 每行一筆 JSON；錯誤結果不得讓整批失敗。

H8. 所有 DB 寫入都要經 repository/use-case API。禁止在 CLI handler、GUI handler 或 scraper adapter 內拼 SQL 直接寫表。

H9. 不做歷史包袱式的死碼保留。若不是新 Rust runtime 或資料銜接需要，就不要建。

---

## 3. 契約邊界

### 3.1 Rust CLI contract

第一版 CLI 是全新的 Rust 介面，只需要支援新架構的穩定入口。命令名稱與旗標以 Rust app use case 為準。

必備命令：

```powershell
actress-rs.exe db init
actress-rs.exe db verify-schema
actress-rs.exe db migrate
actress-rs.exe db stats
actress-rs.exe db get <code>
actress-rs.exe db upsert --json <path>
actress-rs.exe db delete <code>
actress-rs.exe db export-json --output <path>
actress-rs.exe db import-json --input <path> --replace
actress-rs.exe scan <dir>
actress-rs.exe search <code> [--source cascade|avwiki|javdb]
actress-rs.exe search-batch --input <codes.json> [--workers 20] [--source cascade|avwiki|javdb]
actress-rs.exe move --src <path> --dst <path> [--strategy skip|overwrite|rename]
actress-rs.exe history list
actress-rs.exe history rollback <operation_id>
```

成功輸出統一為 stdout JSON。錯誤訊息走 stderr，exit code 非零。是否使用 pretty JSON 不是業務契約；測試只鎖 key 與語意，不鎖空白格式。

### 3.2 Python scraper contract

單筆搜尋：

```powershell
python -X utf8 src\scrapers\run_search.py <code> [source_mode]
```

Rust 端必須接受：

```json
{
  "code": "ABC-123",
  "title": "",
  "studio": "",
  "release_date": "",
  "url": "",
  "actresses": [],
  "search_method": "AV-WIKI",
  "method": "AV-WIKI",
  "error": "",
  "error_kind": ""
}
```

`search_method` 優先，`method` 只作為 Python 爬蟲輸出的相容 fallback。`actresses` 若是字串，adapter 可以接受並正規化成陣列，但 Rust 端寫入 SQLite 前必須固定為 `Vec<String>`。

批次搜尋：

```powershell
python -X utf8 src\scrapers\run_batch_search.py
```

stdin：

```json
{
  "codes": ["ABC-123", "DEF-456"],
  "workers": 20,
  "source_mode": "cascade"
}
```

stdout 是 JSON Lines，每行一筆 `SearchResult`。Rust 端必須逐行解析、逐筆 persist、逐筆回報；單行 parse error 只能標記該筆失敗，不得丟掉已成功項目。

### 3.3 SQLite data contract

Rust 第一版的 DB contract 以現有 SQLite v3 為基準。這是**資料契約**，不是舊程式碼相容。Rust 不需要複製任何既有 runtime 程式碼，但必須保護現有資料結構與欄位語意。

Baseline schema 必須能識別並讀取：

```text
db_meta
videos
actresses
actress_aliases
video_actress_links
legacy_video_actress_links
actress_video_counts
studio_statistics
enhanced_actress_studio_statistics
```

`videos` 欄位 contract：

```text
code, id, title, studio, studio_code, release_date, url,
search_status, search_method, last_search_date,
avwiki_actress_status, avwiki_last_search_date,
javdb_actress_status, javdb_last_search_date,
metadata_source, metadata_confidence,
original_filename, file_path,
error, error_kind,
created_at, updated_at
```

`legacy_video_actress_links` 必須保留為資料保全 contract，至少在舊資料銜接與 JSON export 時不可丟失。它不必成為新 runtime 的主要 business path，但不能在 migration 中被刪除或忽略。

Rust 需要的新表，例如 `operation_logs` / `operation_items`，只能透過 additive migration 新增。禁止在第一版為了「乾淨」而改名、拆欄、刪欄或重建現有表，除非同一個 phase 內提供逐欄驗證與 rollback。

資料銜接優先順序：

1. 直接開啟既有 SQLite v3，執行 Rust additive migration。
2. 若必須重建 DB，從既有 SQLite 讀取後寫入新 SQLite，並用 row count、欄位 checksum、抽樣逐欄比對驗證。
3. JSON import 僅作備援或災難復原，不作主要遷移路徑。

---

## 4. Phase Plan

## P0 — 契約盤點與測試 oracle

目標：先把「邏輯一致」變成可驗證的 contract，而不是靠印象重寫。

任務：

1. 從現有 `docs/ARCHITECTURE.md` 抽出必保留契約：搜尋結果欄位、SQLite 欄位、掃描結果、搬移結果、操作歷史、source-specific status。
2. 從 `pkg/database/sqlite_schema.sql` 建立 Rust baseline schema contract，存成 `rust-rewrite/contracts/sqlite_v3_schema.sql` 或等價 fixture。
3. 建立 `rust-rewrite/contracts/`，放入最小 JSON 範例：
   - `search_single_success.json`
   - `search_single_not_found.json`
   - `search_batch_mixed.jsonl`
   - `video_minimal.json`
   - `move_result_success.json`
4. 建立「資料契約對照表」：哪些 DB 表/欄位必保留、哪些只允許 additive、哪些新功能表由 Rust 自行新增。
5. 建立「行為對照表」：哪些保留、哪些刻意不保留。

驗證：

```powershell
cargo test -p domain contract_fixtures_parse
cargo test -p db sqlite_v3_schema_contract_parse
```

完成條件：所有 contract fixture 都可被 Rust 型別解析；SQLite v3 baseline schema 已被測試鎖住；Task 內明確標出不繼承的舊 runtime 殘留。

## P1 — Rust workspace 與 domain model

目標：建立乾淨 Rust workspace 與唯一 DTO 來源。

任務：

1. 建立 Cargo workspace。
2. 建立 `domain` crate，定義：
   - `Video`
   - `Actress`
   - `VideoActressLink`
   - `SearchResult`
   - `ScanResult`
   - `MoveRequest`
   - `MoveResult`
   - `OperationLog`
3. 所有 DTO 都用同一組 struct，同時服務 DB repository、CLI JSON、GUI binding。
4. 補 serde round-trip tests，鎖定 JSON key。

驗證：

```powershell
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test -p domain
```

完成條件：沒有第二套 contracts crate；沒有 `*ToContract` 類轉換層。

## P2 — SQLite 原生資料層

目標：Rust 直接管理 SQLite，不透過任何舊 runtime 或 Python DB helper。

建議技術選型：`sqlx` + SQLite + compile-time checked query；若 Windows 靜態部署有阻礙，才改 `rusqlite`。選型結果要寫入 `rust-rewrite/decisions.md`。

任務：

1. 建立 `migrations/0001_existing_v3.sql`，內容對齊目前 SQLite v3 資料 contract。
2. 建立 `migrations/0002_rust_additions.sql`，只放 Rust 新 runtime 必要的 additive table/index，例如 operation log。
3. 建立 `db` crate：
   - `Database::open(path)`
   - `migrate()`
   - `verify_schema_contract()`
   - `upsert_video()`
   - `get_video()`
   - `delete_video()`
   - `list_videos()`
   - `upsert_actresses_for_video()`
   - `stats()`
4. 啟用 WAL、foreign keys、busy timeout。
5. 建立 transaction boundary：影片 + 女優 + link 必須同 transaction 寫入。
6. 對既有 SQLite fixture 做 open + schema verify + read tests。
7. 補 `db import-json` / `db export-json` 的 repository 層能力，但不得把 JSON 變成 runtime store，也不得把 JSON 當主要 SQLite 遷移媒介。

驗證：

```powershell
cargo test -p db
cargo test -p db sqlite_round_trip
cargo test -p db opens_existing_sqlite_v3_contract
cargo test -p db additive_migration_preserves_existing_rows
```

完成條件：空 DB 可初始化；既有 SQLite v3 可被 Rust 開啟並保留資料；同一筆搜尋結果重複 upsert 不產生重複 link；foreign key 開啟且測試可證明。

## P3 — Python 爬蟲 adapter

目標：Rust 接上現有 Python 爬蟲，但把 DB 寫入責任留在 Rust。

任務：

1. 建立 `scraper` crate，提供：
   - `search_one(code, source_mode) -> SearchResult`
   - `search_batch(codes, workers, source_mode) -> impl Stream<Item = SearchResult>`
2. subprocess 一律使用 `python -X utf8`，env 設定 `PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1`。
3. script path 必須可設定，預設指向現有 repo 的 `src/scrapers/`；release 時再決定複製策略。
4. adapter 只 parse stdout/stderr，不 import Python module。
5. 單筆與批次都要支援 `cascade` / `avwiki` / `javdb`。
6. 批次 JSON Lines 逐行解析，允許 partial success。

驗證：

```powershell
cargo test -p scraper
cargo test -p scraper parses_search_method_and_legacy_method
cargo test -p scraper keeps_partial_batch_results
```

完成條件：用 fake Python script 可以完整測試 adapter；真實 Python 爬蟲只放在 integration smoke，不讓 unit test 依賴網路。

## P4 — 搜尋 use-case 與 SQLite persist

目標：把「Python 找資料、Rust 寫 SQLite」變成正式流程。

任務：

1. `app` crate 建立 `SearchService`。
2. `SearchService::search_one_and_persist(code, source)`：
   - 呼叫 scraper adapter
   - 正規化 `SearchResult`
   - 寫入 `videos`、`actresses`、`video_actress_links`
   - 更新 source-specific status
3. `SearchService::search_batch_and_persist(codes, workers, source)`：
   - 逐筆 persist
   - 回傳 successes / failures / per-code result
4. 保留現有語意：
   - `source = cascade` 成功時更新整體 `search_status=searched_found`
   - `source = avwiki` 只更新 `avwiki_actress_status` 與整體成功欄位
   - `source = javdb` 只更新 `javdb_actress_status` 與整體成功欄位
   - not_found 不覆蓋既有成功 metadata

驗證：

```powershell
cargo test -p app search_persist_contract
cargo test -p app source_specific_not_found_preserves_existing_success
```

完成條件：批次搜尋混合成功、not_found、error 時，DB 狀態與本 Task 定義的 source-specific status 語意一致。

## P5 — 掃描、番號提取、片商分類

目標：重建非爬蟲核心能力，避免 Python fallback。

任務：

1. 建立 `scanner` crate：
   - 檔案遍歷
   - 影片副檔名過濾
   - 番號提取
   - 同番號去重策略
2. 建立 studio classifier：
   - 載入 `studios.json` / `major_studios.json`
   - 支援 code prefix 與 name matching
3. 將掃描結果 DTO 鎖成單一 JSON shape。

驗證：

```powershell
cargo test -p scanner
cargo test -p app scan_then_search_contract
```

完成條件：同一批新 Rust contract fixture 檔名，Rust 能穩定提取預期番號；不需要逐 regex 對齊任何舊實作。

## P6 — 搬移與操作歷史

目標：重建檔案移動、資料夾移動、rollback，並把操作歷史放進 SQLite。

任務：

1. 建立 `mover` crate：
   - file move
   - dir move
   - batch move
   - conflict strategy：`skip` / `overwrite` / `rename`
2. 建立 operation log：
   - operation id
   - source path
   - destination path
   - moved / skipped / failed
   - rollback metadata
3. 所有實際檔案操作需先產生 plan，再執行。
4. rollback 根據 SQLite operation log 執行，不依賴外部 journal。

驗證：

```powershell
cargo test -p mover
cargo test -p app move_and_rollback_round_trip
```

完成條件：搬移失敗可回報 partial result；rollback 對不存在檔案有明確錯誤，不靜默假成功。

## P7 — CLI 組裝

目標：提供可操作的 Rust binary。

任務：

1. 用 `clap` 建立 CLI。
2. 所有命令走 `app` crate，不直接呼叫 repository 私有函式。
3. stdout 統一 JSON；stderr 統一人類可讀錯誤。
4. 補 CLI contract integration tests。

驗證：

```powershell
cargo test -p cli
cargo run -p cli -- db init --db .\tmp\new-empty.sqlite
cargo run -p cli -- search ABC-123 --db .\tmp\new-empty.sqlite --source avwiki
```

完成條件：CLI 可完成 init → scan → search → db get → move → history list 的 happy path。

## P8 — 既有 SQLite 銜接與資料保全

目標：讓 Rust runtime 能承接現有 `data/db.sqlite`，並在需要 schema 演進時做可驗證的無損 migration。JSON 只作備援，不作主要資料轉錄路徑。

任務：

1. `db verify-schema --db data/db.sqlite`：確認必要表、欄位、index/view、`PRAGMA user_version` 與 foreign key 狀態。
2. `db migrate --db data/db.sqlite`：對既有 SQLite 執行 Rust additive migration，例如 operation log tables。
3. `db backup-create --db data/db.sqlite`：migration 前建立 SQLite 檔案備份；不得只匯出 JSON。
4. `db export-json --output <path>`：保留成外部交換與人工檢查用途，但不得作為主要 migration step。
5. `db import-json --input data/json_db/data.json --replace`：只作沒有可用 SQLite 時的備援恢復路徑。
6. 建立 migration report：
   - schema_from
   - schema_to
   - videos_before / videos_after
   - actresses_before / actresses_after
   - links_before / links_after
   - legacy_links_before / legacy_links_after
   - tables_added
   - columns_added
   - checksum_before / checksum_after
7. 所有 destructive-looking migration 必須 all-or-nothing transaction，且預設拒絕對未備份 DB 執行。

驗證：

```powershell
cargo test -p app sqlite_v3_handoff_report_shape
cargo test -p app migrate_existing_sqlite_preserves_row_counts
cargo test -p app migrate_existing_sqlite_preserves_field_checksums
cargo test -p app export_json_preserves_legacy_links
```

完成條件：現有 SQLite 可直接被 Rust runtime 接手；migration 後 row counts、必要欄位 checksum、抽樣逐欄比對都通過；JSON 只保留為 export/import 備援。

## P9 — GUI 對接準備

目標：建立 Tauri 桌面 GUI 的正式選型、視覺規格與 API 邊界。

正式選型：

```text
Desktop shell: Tauri v2
Frontend: React + TypeScript + Vite
Styling: Tailwind CSS
Component base: shadcn/ui
Tables: TanStack Table
Icons: lucide-react
```

視覺方向固定為 **Quiet Operations Console**：本機資料工作台，不做 landing page、不做裝飾性大卡片、不做高彩度娛樂風格。第一版主題：

```text
Mode: Light-first, Dark optional
Style: Vega
Base Color: Neutral
Theme / Accent: Teal
Icon Library: Lucide
Menu Color: Default / Solid
Menu Accent: Subtle
Radius: 8px 以下
```

狀態色語意：

```text
Primary/action: Teal
Info: Blue
Success: Emerald
Warning: Amber
Danger/error: Red
Muted/structure: Neutral/Zinc scale
```

主要佈局：

```text
左側 sidebar：掃描 / 搜尋 / 資料庫 / 搬移 / 歷史 / 設定
上方 command bar：目前目錄、搜尋來源、workers、主要動作
中央主表格：影片清單 / 搜尋結果 / 操作歷史
右側 detail drawer：單筆影片、女優、來源狀態、錯誤詳情
底部 status strip：任務進度、最後錯誤、DB 狀態
```

若後續沿用既有 UI 概念，也必須先定義新的 frontend service layer，不沿用舊 binding 概念。

任務：

1. 建立 Tauri v2 + React + TypeScript + Vite frontend shell。
2. 建立 Tailwind + shadcn/ui theme tokens，鎖定 Neutral + Teal、light-first、dark optional。
3. 建立 Quiet Operations Console 佈局骨架，優先支援表格、toolbar、drawer、status strip。
4. 定義 GUI-facing command list：
   - scan_directory
   - search_batch
   - db_get_video
   - move_batch
   - history_list
   - rollback_operation
   - identify_studio
5. GUI commands 回傳 `domain` DTO，不建立 GUI 專用 duplicate DTO。
6. event contract：
   - `search:result`
   - `search:progress`
   - `search:done`
   - `operation:progress`
   - `error`

驗證：

```powershell
cargo test -p app gui_contract_shapes
npm run typecheck
npm run test
```

完成條件：GUI 可在不碰 DB schema 的前提下接上 app service；主題與 layout 符合 Quiet Operations Console，不回退到紫色預設主題或 marketing-style 首頁。

---

## 5. Stop Gate

S1. 如果某任務需要複製舊 runtime helper、Python DB wrapper、JSON journal 或 shadow DB，立刻停止，重新拆 task。這代表架構開始污染。

S2. 如果發現 Python 爬蟲不能在不寫 DB 的情況下回傳完整結果，先修 Python 爬蟲 stdout contract，不要在 Rust 端加 DB callback workaround。

S3. 如果 SQLite schema 需要同時維護兩份 SQL，立刻停止，回到 P2 決定單一來源。

S4. 如果 DTO 需要兩套以上平行 struct 才能串接 CLI / DB / GUI，立刻停止，回到 P1 修 domain model。

S5. 如果額外操作習慣導致新 Rust CLI 變得複雜，先把該需求放到獨立 adapter phase，不要污染核心 app service。

S6. 如果 migration 設計需要先把 SQLite 匯出 JSON、再用 JSON 匯入新 DB，立刻停止。這是高風險二次轉錄，除非原 SQLite 已不可讀，否則不能作為主要路徑。

S7. 如果 schema 演進需要刪欄、改欄名、重建核心表或丟棄 `legacy_video_actress_links`，立刻停止，先補資料保全計畫、備份流程、逐欄驗證與 rollback。

---

## 6. 驗證矩陣

最低驗證：

```powershell
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

Python adapter smoke：

```powershell
python -m pytest tests\test_run_search_contract.py -q -p no:cacheprovider
cargo test -p scraper real_python_script_smoke -- --ignored
```

端到端 smoke：

```powershell
New-Item -ItemType Directory -Force -Path .\tmp | Out-Null
Copy-Item ..\data\db.sqlite .\tmp\db.sqlite
cargo run -p cli -- db verify-schema --db .\tmp\db.sqlite
cargo run -p cli -- db backup-create --db .\tmp\db.sqlite --output-dir .\tmp\backups
cargo run -p cli -- db migrate --db .\tmp\db.sqlite
cargo run -p cli -- db stats --db .\tmp\db.sqlite
cargo run -p cli -- search ABC-123 --db .\tmp\db.sqlite --source avwiki
cargo run -p cli -- db get ABC-123 --db .\tmp\db.sqlite
```

---

## 7. Definition of Done

DoD1. `rust-rewrite/` 是獨立 Rust workspace；除了 Python 爬蟲層之外，不依賴、不匯入、不包裝既有 runtime 程式碼或 build artifact。

DoD2. SQLite 是 runtime 唯一 source of truth；Rust 可讀取或無損遷移現有 SQLite v3；JSON 僅能 import/export 或災難復原。

DoD3. Rust 可呼叫現有 Python 爬蟲，解析單筆與批次輸出，並由 Rust 寫入 SQLite。

DoD4. 核心 DTO 只有一套，CLI / DB / GUI-facing API 共用 `domain` 型別或明確 newtype，不存在平行 byte-identical struct。

DoD5. 搜尋、掃描、搬移、history、SQLite handoff、import/export 都有 contract tests。

DoD6. 所有測試可在沒有網路時通過；需要真爬蟲的測試標成 ignored / smoke。

DoD7. 新架構文件明確列出「不繼承」項目：舊 runtime bridge、Python DB fallback、JSON runtime store、journal replay、shadow DB、legacy v2 tools。

DoD8. P8 已證明資料銜接不靠 JSON round-trip：migration report 包含 row counts、checksums、legacy links 保全與抽樣逐欄比對。

---

## 8. 明確不做

第一版不建立 compatibility layer；先完成 Rust 原生流程。

第一版 CLI 旗標只以本 Task 定義的 Rust use case 為準。

第一版不把 Python 爬蟲改寫成 Rust。先保留既有 Python 爬蟲，等 Rust runtime 穩定後再評估是否重寫爬蟲。

第一版不任意重設 schema。現有 SQLite v3 是資料契約；只有 additive migration 或已驗證無損遷移可以進入第一版。

第一版不把現有非 Python 測試 fixture 原封不動搬到 Rust；只建立新的 contract fixture 與必要業務案例。
