# Rust SQLite 影子資料庫設計

本文件是 `tools-rs` 第一版實作的唯一依據，用來取代討論匯出檔中混雜的早期草稿。若討論紀錄與本文件不同，以本文件為準。

## 目標

在不改變現有 Go/Wails 主線、Python 搜尋流程與 JSON DB 寫入契約的前提下，新增 Rust sidecar CLI，將 compact 後的 `data.json` 匯入 SQLite 影子資料庫，用於驗證、統計、比對與效能測試。

第一版 SQLite 是衍生物，不是 source of truth。

## 邊界

- 不取代 Go JSON DB 寫入路徑。
- 不修改 `data/json_db/data.json`、`data/json_db/data.journal`、`data/json_db/data.index`。
- 不自動執行 `classifier db compact`。
- import / compare 預設要求 journal 乾淨；若 `data.journal` 非空，直接 non-zero。
- `--allow-dirty-journal` 只供診斷使用，輸出 `source_consistent=false`。
- journal replay 留到第二階段，不在第一版範圍。

## 工具與依賴

建立 `tools-rs/` Cargo crate，binary 名稱為 `db-tool`。

固定慣例：shadow SQLite 檔案放在 `data/shadow.sqlite`。這個檔案是衍生物，仍由 `.gitignore` 的 `*.sqlite` 排除，不進版控。

主要依賴：

- `anyhow`
- `clap` with `derive`
- `rusqlite` with `bundled`
- `serde` / `serde_json`
- `time` with `formatting` and `std`

## CLI

### `db-init`

```powershell
cargo run --manifest-path tools-rs\Cargo.toml -- db-init --sqlite data\shadow.sqlite --replace
```

建立 SQLite schema，設定 `PRAGMA user_version = 2`。`--replace` 會刪除既有 shadow schema 後重建。

若偵測到 v1 shadow DB，工具不做 in-place migration；請用 `--replace` 重建，或刪除舊的 `data\shadow.sqlite` 後再執行。

### `db-import-json`

```powershell
cargo run --manifest-path tools-rs\Cargo.toml -- db-import-json --json data\json_db\data.json --sqlite data\shadow.sqlite --replace
```

行為：

- 使用整批 single transaction，transaction behavior 為 immediate。
- `--json` 檔名剛好是 `data.json` 時，自動推導同目錄 `data.journal`。
- 非標準檔名如 `export.json` 或 `data.json.bak` 若要 journal 一致性檢查，必須顯式傳 `--journal`。
- 單筆 video 沒有 `code` / `id` 時列入 invalid 並略過，不讓整批失敗。
- `actresses` 依 JSON ordinal 順序去重；`ordinal` 保留 JSON 陣列中第一次出現的位置。
- 重複女優計入 `duplicate_actresses`，只當 warning，不讓 compare 失敗。

輸出包含：

- `success`
- `videos`
- `actresses`
- `invalid`
- `duplicate_actresses`
- `source_consistent`
- `elapsed_ms`

### `db-stats`

```powershell
cargo run --manifest-path tools-rs\Cargo.toml -- db-stats --sqlite data\shadow.sqlite
```

只讀 SQLite，輸出 row counts、distinct studio count、empty title count 與最後一次 import metadata。

### `db-compare-json`

```powershell
cargo run --manifest-path tools-rs\Cargo.toml -- db-compare-json --json data\json_db\data.json --sqlite data\shadow.sqlite
```

比對：

- code 集合
- 所有 video 字串欄位：`title`、`studio`、`release_date`、`url`、`search_status`、`search_method`、`last_search_date`、`created_at`、`updated_at`、`original_filename`、`file_path`
- `actresses` ordinal 順序
- `actress_items` 的 `(name, ordinal)`

mismatch 預設輸出 JSON 後直接 exit 1，不額外污染 stderr。`duplicate_actresses` 是資料品質 warning，不納入 `success=false` 條件。

### `db-benchmark`

```powershell
cargo run --manifest-path tools-rs\Cargo.toml -- db-benchmark --json data\json_db\data.json --sqlite data\shadow.sqlite --iterations 10
```

benchmark 本身不強制執行 compare，compare 是流程 gate。

語意說明：

- `json_total_ms`：JSON 每輪 cold-read + parse，這就是 JSON DB 的真實讀取成本
- `sqlite_cold_total_ms`：每輪重開連線 + load，模擬「短命 CLI 一次性查詢」情境
- `sqlite_warm_total_ms`：共用連線 + load，模擬「常駐 process 持續查詢」情境
- `sqlite_stats_total_ms`：共用連線 + stats query
- `sqlite_open_overhead_ms`：純 `open_db` × N，用來分離連線建立成本

## Schema

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS videos (
  code TEXT PRIMARY KEY NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  studio TEXT NOT NULL DEFAULT '',
  release_date TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL DEFAULT '',
  search_status TEXT NOT NULL DEFAULT '',
  search_method TEXT NOT NULL DEFAULT '',
  last_search_date TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT '',
  original_filename TEXT NOT NULL DEFAULT '',
  file_path TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS video_actresses (
  video_code TEXT NOT NULL,
  actress_name TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  PRIMARY KEY (video_code, actress_name),
  FOREIGN KEY (video_code) REFERENCES videos(code) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_videos_studio ON videos(studio);
CREATE INDEX IF NOT EXISTS idx_video_actresses_name ON video_actresses(actress_name);

CREATE VIEW IF NOT EXISTS videos_with_actresses AS
SELECT
  v.code,
  v.title,
  v.studio,
  COALESCE((
    SELECT group_concat(ordered.actress_name, ', ')
    FROM (
      SELECT va.actress_name
      FROM video_actresses va
      WHERE va.video_code = v.code
      ORDER BY va.ordinal, va.actress_name
    ) ordered
  ), '') AS actresses,
  v.release_date,
  v.url,
  v.search_status,
  v.search_method,
  v.last_search_date,
  v.created_at,
  v.updated_at,
  v.original_filename,
  v.file_path
FROM videos v;

CREATE TABLE IF NOT EXISTS import_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_path TEXT NOT NULL,
  source_mtime TEXT NOT NULL DEFAULT '',
  source_size_bytes INTEGER NOT NULL DEFAULT 0,
  video_count INTEGER NOT NULL DEFAULT 0,
  actress_link_count INTEGER NOT NULL DEFAULT 0,
  invalid_count INTEGER NOT NULL DEFAULT 0,
  duplicate_actresses INTEGER NOT NULL DEFAULT 0,
  source_consistent INTEGER NOT NULL DEFAULT 1,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL
);
```

`schema_version` 不存進 `import_runs`，只使用 `PRAGMA user_version`。

`raw_json` 已於 v2 schema 移除，理由是沒有任何 reader 使用，且會讓 shadow DB 體積明顯膨脹。SQLite 仍是衍生物；需要原始完整資料時回讀 `data\json_db\data.json`。

`videos_with_actresses` 是給人工檢視與診斷用的整合 view，底層仍保留 `videos` / `video_actresses` 的正規化結構。若只想一眼看影片、片商與女優，查這個 view。

```sql
SELECT code, title, studio, actresses
FROM videos_with_actresses
LIMIT 20;
```

## 驗收順序

1. `cargo fmt --manifest-path tools-rs/Cargo.toml --check`
2. `cargo clippy --manifest-path tools-rs/Cargo.toml -- -D warnings`
3. `cargo test --manifest-path tools-rs/Cargo.toml`
4. `cargo run --manifest-path tools-rs/Cargo.toml -- db-init --sqlite <temp.sqlite> --replace`
5. `cargo run --manifest-path tools-rs/Cargo.toml -- db-import-json --json data/json_db/data.json --sqlite data/shadow.sqlite --replace`
6. `cargo run --manifest-path tools-rs/Cargo.toml -- db-compare-json --json data/json_db/data.json --sqlite data/shadow.sqlite`
7. compare pass 後再跑 `db-benchmark`
