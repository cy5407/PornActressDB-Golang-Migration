# SQLite 主資料庫遷移設計

> 建立：2026-05-23
> 範圍：把 `data/json_db/data.json` (+ journal + index) 為 source of truth 的現況，遷移為 `data/db.sqlite` 為 source of truth；shadow DB 同時退役。
> 終點：`wiki/architecture/sqlite-shadow-db.md` 路線圖階段 5。

---

## 1. 終點架構

```
┌─────────────────────────────────────────────────────────┐
│   Python 搜尋管線 (run_search / run_batch_search)        │
└──────────────────────┬──────────────────────────────────┘
                       │ subprocess（CLI 介面不變）
                       ▼
┌─────────────────────────────────────────────────────────┐
│   classifier.exe (Go) — pkg/database (SQLiteStore)       │
│   modernc.org/sqlite + database/sql                      │
│   WAL mode, foreign_keys = ON                            │
└──────────────────────┬──────────────────────────────────┘
                       │ direct Go import
                       ▼
┌─────────────────────────────────────────────────────────┐
│   Wails backend (actress-classifier.exe) — 同一 pkg     │
└─────────────────────────────────────────────────────────┘

                       ▼
              ┌────────────────────┐
              │  data/db.sqlite    │  ← 唯一 source of truth
              └────────────────────┘
                       ▲
                       │ 離線
              ┌──────────────────────────────────────┐
              │  Rust db-tool (tools-rs/)            │
              │  verify / benchmark / cross-version  │
              │  migration / backup-restore CLI      │
              └──────────────────────────────────────┘
```

**Owner**：Go (`modernc.org/sqlite`) 負責 runtime 讀寫；Rust db-tool 退為離線維護工具。

**選 modernc 不選 mattn 的理由**：保留現有純 Go build pipeline（`go build` / `wails build` 無需 CGo），規模 < 10K 影片下效能差距無感。介面用 `database/sql` 標準介面包裝，未來想換 mattn 只需換 import。

**退役 / 改角色**：

| 項目 | 結局 |
|------|------|
| `data/json_db/data.json` | Phase C 起退役；變為手動匯出快照（`db export-json`）與備份格式 |
| `data.journal`、`data.index` | Phase C 起不再產生 |
| `classifier.exe db compact` | Phase C 起變 no-op（保留指令以維持 CLI 相容） |
| Rust `db-tool db-import-json` 主路徑 | Phase C 起退役，保留以 deprecation warning 顯示 |
| `pkg/database` JSONStore | Phase C 起移除 |
| Python `src/services/go_cli.py` 與 `IncrementalJSONDB` 委派層 | 完全不動，CLI 介面契約保留 |

---

## 2. Schema

### 2.1 `db_meta`（key-value 形式，singleton 表）

```sql
CREATE TABLE db_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

**初始 key 與值**：

| key | 值 | 對應 JSON 端 |
|-----|----|------------|
| `schema_version` | `"1.0.0"` | JSON 端 `SCHEMA_VERSION` 字串（業務語意） |
| `description` | `"Python 女優分類系統 JSON 資料庫"` | `metadata.description` |
| `encoding` | `"UTF-8"` | `metadata.encoding` |
| `data_hash` | **永遠空字串**（reserved 欄位）；export 時即時計算寫入 JSON 輸出，不回填 SQLite。verify-sync 忽略此 key（見 § 4.2） | `data_hash` |
| `created_at` | RFC3339 | `created_at` |
| `updated_at` | RFC3339，每次寫入更新 | `updated_at` |

**`PRAGMA user_version`** 另外維護**結構版本**：整數，這次設為 `3`（與現有 shadow DB v2 區隔；給 db-tool / migration 工具識別）。**`db_meta.schema_version` 與 `PRAGMA user_version` 是兩個獨立概念**：
- `db_meta.schema_version` = JSON schema 語意版本，export 時填回 `data.json`
- `PRAGMA user_version` = SQLite 結構版本，未來 schema 升級時遞增

### 2.2 `videos`

```sql
CREATE TABLE videos (
    code TEXT PRIMARY KEY,
    id TEXT NOT NULL DEFAULT '',                       -- 舊版相容
    title TEXT NOT NULL DEFAULT '',
    studio TEXT NOT NULL DEFAULT '',
    studio_code TEXT NOT NULL DEFAULT '',
    release_date TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    search_status TEXT NOT NULL DEFAULT '',
    search_method TEXT NOT NULL DEFAULT '',
    last_search_date TEXT NOT NULL DEFAULT '',
    avwiki_actress_status TEXT NOT NULL DEFAULT '',
    avwiki_last_search_date TEXT NOT NULL DEFAULT '',
    javdb_actress_status TEXT NOT NULL DEFAULT '',
    javdb_last_search_date TEXT NOT NULL DEFAULT '',
    metadata_source TEXT NOT NULL DEFAULT '',
    metadata_confidence REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    original_filename TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    error_kind TEXT NOT NULL DEFAULT ''
);

CREATE INDEX idx_videos_studio ON videos(studio);
```

### 2.3 `actresses` + `actress_aliases`

```sql
CREATE TABLE actresses (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
    -- video_count 移除：改為 derived（view），export 時計算填回
    -- name 不加 UNIQUE：現有 JSON DB 尚未 audit 過 name 唯一性
);

CREATE INDEX idx_actresses_name ON actresses(name);  -- 查詢用，非唯一

CREATE TABLE actress_aliases (
    actress_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    PRIMARY KEY (actress_id, alias),
    FOREIGN KEY (actress_id) REFERENCES actresses(id) ON DELETE CASCADE
);
```

### 2.4 `video_actress_links`

```sql
CREATE TABLE video_actress_links (
    video_code TEXT NOT NULL,
    actress_id TEXT NOT NULL,
    role_type TEXT NOT NULL DEFAULT '主演',
    ordinal INTEGER NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',  -- 原 videos[].actresses 上的拼寫；與 actresses.name 同則空字串
    timestamp TEXT NOT NULL DEFAULT '',

    PRIMARY KEY (video_code, ordinal),
    UNIQUE (video_code, actress_id, role_type),
    FOREIGN KEY (video_code) REFERENCES videos(code) ON DELETE CASCADE,
    FOREIGN KEY (actress_id) REFERENCES actresses(id) ON DELETE CASCADE
);

CREATE INDEX idx_links_actress ON video_actress_links(actress_id);
```

**主鍵選擇**：`PRIMARY KEY(video_code, ordinal)` 完整保留 `videos[].actresses` 原始順序；`UNIQUE(video_code, actress_id, role_type)` 防止同影片同女優同角色重複（migration 遇此情境 fail loudly，不 silent drop）。

### 2.5 Statistics view（derived，非 canonical）

```sql
-- 內部用：actresses[].video_count export 時的來源
CREATE VIEW actress_video_counts AS
    SELECT a.id, a.name, COUNT(l.video_code) AS video_count
    FROM actresses a
    LEFT JOIN video_actress_links l ON l.actress_id = a.id
    GROUP BY a.id, a.name;

-- JSON statistics.studio_statistics 對應
CREATE VIEW studio_statistics AS
    SELECT v.studio, COUNT(*) AS video_count
    FROM videos v
    WHERE v.studio <> ''
    GROUP BY v.studio;

-- JSON statistics.enhanced_actress_studio_statistics 對應
CREATE VIEW enhanced_actress_studio_statistics AS
    SELECT a.id AS actress_id, a.name AS actress_name,
           v.studio, COUNT(*) AS video_count
    FROM actresses a
    JOIN video_actress_links l ON l.actress_id = a.id
    JOIN videos v ON v.code = l.video_code
    WHERE v.studio <> ''
    GROUP BY a.id, a.name, v.studio;
```

`statistics.actress_statistics` export 時直接 SELECT 自 `actress_video_counts`（不另立 view，避免兩份等價定義漂移）。

匯出回 JSON 時：
- `actresses[].video_count` ← `actress_video_counts.video_count`
- `statistics.actress_statistics` ← `SELECT * FROM actress_video_counts`
- `statistics.studio_statistics` ← `SELECT * FROM studio_statistics`
- `statistics.enhanced_actress_studio_statistics` ← `SELECT * FROM enhanced_actress_studio_statistics`
- `statistics.computed_at` ← 當前 RFC3339 timestamp（不持久化）

statistics 不在表中持久化，每次 export 動態算。

---

## 3. `VideoData.Actresses` ↔ `ActressData` / Link 映射策略（Migration）

JSON DB：`videos[code].actresses` 是名稱清單（`string[]`）；`actresses{id}` 是女優實體 map。
SQLite：actress 是獨立實體，link 透過 `actress_id` 關聯。Migration 需要把名稱清單轉成 `(actress_id, ordinal)` link。

### 3.1 三階段 migration（在 `db migrate-from-json` 內執行）

```
Pass 1: JSON.actresses{} → SQLite actresses 表
        直接搬：id, name, created_at, updated_at
        aliases[] → actress_aliases 表（每個 alias 一 row）

Pass 2: JSON.videos[code].actresses → video_actress_links
        for video in videos:
          for ordinal, display in enumerate(video.actresses):
            actress_id = resolve_actress_id(display)
            if actress_id is None:
              if --auto-create-missing-actresses:
                actress_id = stable_id_from_name(display)
                INSERT actresses(id=actress_id, name=display, ...)
                migration_report.auto_created.append(display)
              else:
                migration_report.unresolved.append((video_code, display))
                continue   -- 收集完畢再 fail loudly
            INSERT video_actress_links(
              video_code, actress_id,
              role_type = '主演',
              ordinal = ordinal,
              display_name = (display if display != actress.name else ''),
              timestamp = video.updated_at
            )

        若 migration_report.unresolved 非空：
          列出全部 (video_code, display) 對；exit 非 0；不留半成品

Pass 3: JSON.links[] (若存在) → 覆寫 / 補充 video_actress_links
        以 JSON.links 的 role_type / timestamp 為 canonical
        若 (video_code, actress_id, role_type) 已由 Pass 2 建立但 role_type 不同 → 新增一筆
        若完全相同 → UPDATE timestamp 為 JSON.links 內的值
```

### 3.2 `resolve_actress_id(display)` 規則

```
1. 完全相符：SELECT id FROM actresses WHERE name = display  → 用該 id
2. 別名相符：SELECT actress_id FROM actress_aliases WHERE alias = display  → 用該 actress_id
3. 都沒有 → 回傳 None（觸發 fail loudly 或 auto-create）
```

### 3.3 `stable_id_from_name(name)` 規格

```
auto_<sha1(strings.TrimSpace(name))[:16]>

例：
  name = "  田中美奈実 "  → trim 後 "田中美奈実"
  sha1("田中美奈実")[:16] → "a3f29d8c5e6b1742"
  id → "auto_a3f29d8c5e6b1742"
```

**Normalization 規則明確只做 `strings.TrimSpace`**：
- **不**做 Unicode NFC/NFD 規範化（避免不可逆等價合併真實不同的條目）
- **不**做大小寫轉換、不做半形/全形轉換
- 前綴 `auto_` 讓 ID 一眼可辨「migration 自動產生」與「JSON 原生 id」
- 同名字串多次 migration 產生同 ID（idempotent），可重跑

### 3.4 預設策略

**嚴格 fail loudly**：未對齊的 actress 直接終止 migration，列出全部缺項；使用者需先跑 `db clean-actresses` 或人工處理 JSON 後重試。
**`--auto-create-missing-actresses`** flag 給 migration script / CI 用，建立的 entity 會記在 migration report 內供後續審查。

### 3.5 同 video 重複 actress 處理

若 `videos[code].actresses = ["A", "B", "A"]`（同名重複），Pass 2 會嘗試 INSERT 兩筆相同 `actress_id`：
- `PRIMARY KEY(video_code, ordinal)` 不擋（ordinal 不同）
- `UNIQUE(video_code, actress_id, role_type)` 會擋 → fail loudly + 列出 `(video_code, actress_name, [ordinals])`
- 使用者用 `db clean-actresses` 處理或人工修 JSON 後重試

---

## 4. 三階段過渡

```
┌─────────────────────────────────────────────────────────┐
│  Phase A：雙寫上線                                       │
├─────────────────────────────────────────────────────────┤
│  • 抽 DatabaseStore interface                            │
│  • 新增 SQLiteStore（WAL、foreign_keys=ON）              │
│  • DualWriteStore: JSON 寫成功 → SQLite 寫              │
│  • 讀路徑：仍 JSON                                       │
│  • 新 CLI: db migrate-from-json / verify-sync /          │
│           resync-from-json                              │
│  • CI 每次 release gate 跑 verify-sync                   │
└─────────────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  Phase B：讀路徑反轉                                     │
├─────────────────────────────────────────────────────────┤
│  • feature flag USE_SQLITE_READS                        │
│  • 讀路徑：SQLite，失敗 fallback 到 JSON                 │
│  • 寫入仍雙寫（JSON 留作迴退）                            │
│  • 監測 sqlite_read_fallback_total                      │
└─────────────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  Phase C：JSON 退役                                       │
├─────────────────────────────────────────────────────────┤
│  • 移除 JSONStore / DualWriteStore                       │
│  • 寫入只走 SQLite                                       │
│  • db compact 變 no-op                                   │
│  • backup/restore 改 SQLite backup strategy（見 § 6.2）  │
│  • 新 CLI: db export-json                                │
│  • Rust db-tool 重定位（移除 import-json 主路徑，        │
│    保留 verify / benchmark / cross-version migration）   │
└─────────────────────────────────────────────────────────┘
```

### 4.1 雙寫失敗策略

JSON 與 SQLite 跨檔案無共同 transaction，必須明確定義不一致時的行為。

**寫入順序與失敗語意（Phase A/B）**：

```
DualWriteStore.UpdateVideo(code, data):
  1. JSONStore.UpdateVideo(code, data)
     失敗 → 整筆操作 fail，回傳 error
            （JSON 在 A/B 是 source of truth，必須成功）
  2. SQLiteStore.UpdateVideo(code, data)
     成功 → return nil
     失敗 → 寫入 data/sync_degraded.jsonl 一行：
            {"ts":"...","code":"STARS-707","op":"UPDATE","error":"...","json_ok":true}
            log.Warn(...)
            metrics.sync_degraded_total++
            **回傳 nil**（不 fail 整筆操作；JSON 已是 source of truth）
```

**Degraded log 重試（非阻塞）**：

| 時機 | 行為 |
|------|------|
| **DualWriteStore 啟動時** | `replayDegradedLog()` 同步跑一次（阻塞啟動，但只在啟動時一次）。每筆讀 JSON 對應 code 的目前狀態 → 寫 SQLite。成功則從 log 移除；失敗則保留。 |
| **每次寫入後** | 背景 goroutine `go tryReplayPending()` 嘗試把當下 degraded log 中與本次 code 相關的 entry 重試（不阻塞主寫入路徑） |
| **寫入前** | 只 `os.Stat(sync_degraded.jsonl)`；檔案大小 > threshold（例 32 KiB）時 `log.Warn("sync degraded backlog growing, consider db resync-from-json")`，**不 block** |
| **手動全量** | `classifier.exe db resync-from-json`：DROP rows + bulk INSERT in 1 transaction，從 JSON 重灌 SQLite |

`sync_degraded.jsonl` 為空時自動刪除檔案。

### 4.2 `db verify-sync` 設計

```
classifier.exe db verify-sync

對照範圍：
  - videos: 全部 code 與所有持久化欄位
  - actresses: 全部 id 與欄位
  - links: 整個集合
  - db_meta: 對照 schema_version / description / encoding / created_at
             updated_at 允許秒級差異
             data_hash 完全忽略（見下）

回傳：
  一致 → exit 0, JSON {"consistent":true,"video_count":N,...}
  不一致 → exit 非 0, JSON {"consistent":false,"diffs":[{kind,id,json_value,sqlite_value},...]}
         列出全部不一致 entry

不嘗試自動修復；修復走 db resync-from-json（明確使用者意圖）
```

**`db_meta.data_hash` 規則**（與 § 2.1 定義一致）：

- `data_hash` 是 export-time 欄位，**只在 `db export-json` 流程中即時計算並寫入 JSON 輸出**，不在 SQLite `db_meta` 表中持久化非空值
- 寫入路徑**不維護** `data_hash`（避免每次寫入額外 hash 全量資料的成本與雙寫分歧風險）
- `verify-sync` **完全忽略** `data_hash`（兩邊都可能是空字串，比對無意義）
- 若未來需要完整性檢查，走 `db export-json` → 取得當下 hash → 與舊 export 比對；不要把它塞回 verify-sync

```
Phase A release gate：CI 必須 verify-sync 通過
Phase B release gate：除 verify-sync 通過外，sqlite_read_fallback_total = 0
```

### 4.3 Phase B 讀路徑 fallback

```
SQLiteReadStore.GetVideo(code):
  if !USE_SQLITE_READS:
    return JSONStore.GetVideo(code)

  v, err := SQLiteStore.GetVideo(code)
  if err == nil:
    return v, nil

  // fallback 觸發條件（限 SQLite 整體錯誤）:
  //   - SQLite 開啟失敗（檔案損毀 / 權限）
  //   - 查詢例外（schema mismatch、I/O error、driver panic）
  //   - 統一以 errors.Is(err, ErrSQLiteUnavailable) 判別
  log.Error("sqlite read fallback to json", "code", code, "err", err)
  metrics.sqlite_read_fallback_total++
  return JSONStore.GetVideo(code)
```

**重要**：「資料不一致」**不**觸發 fallback — 那是雙寫分歧，要靠 verify-sync 發現並由 `db resync-from-json` 修復。Fallback 只是「SQLite 整體掛掉」時的安全網。`sqlite_read_fallback_total > 0` 時 release 不能進 Phase C。

### 4.4 每階段 Rollback 條件

| 從 | 觀察到 | Rollback 動作 |
|----|--------|--------------|
| Phase A | DualWriteStore 寫 SQLite 失敗率高 / verify-sync 大量 diff | 停雙寫；只跑 JSONStore；事後分析 |
| Phase B | sqlite_read_fallback_total 持續累加 | feature flag USE_SQLITE_READS=false；讀回 JSON |
| Phase C | SQLite 損毀且無法 restore | `db backup-restore -from-json <file>` 從最近 export-json 快照重建（前提：進入 C 前必須產生雙快照） |

---

## 5. CLI 變更

### 5.1 新增

| 指令 | 用途 | 階段 |
|------|------|------|
| `classifier.exe db migrate-from-json [-source PATH] [-auto-create-missing-actresses]` | 一次性把 JSON DB 全量 import 到 SQLite。預設嚴格（缺 actress entity 直接 fail loudly + 列出全部缺項）。flag 開啟才自動建 `auto_<sha1>` entity 並寫進 migration report | Phase A 上線時跑 |
| `classifier.exe db verify-sync` | 對照 JSON ↔ SQLite。退出碼非 0 視為失敗、列出全部不一致 code。不嘗試自動修復 | Phase A/B |
| `classifier.exe db resync-from-json` | 強制把 JSON 全量覆寫 SQLite（DROP rows + bulk INSERT in 1 transaction） | Phase A/B |
| `classifier.exe db export-json [-output PATH]` | SQLite → JSON 匯出，產出與舊 `data.json` 同 schema 的快照。`actresses[].video_count` 從 `actress_video_counts` view 填回；根層 metadata 從 `db_meta` 填回 | Phase C 起 |

### 5.2 維持，介面不變（**沿用既有名稱，不新增 alias 取代**）

下列指令名稱沿用 `src/services/go_cli.py` 與 `cmd/scanner` 既有契約，**禁止取代**：

- `db get` / `db update` / `db list` / `db stats`
- `db backup-create`（不是 `db backup`）
- `db backup-list`
- `db backup-restore -backup-path <file>`（不是 `db restore`）
- `db backup-cleanup`
- `db clean-actresses`

所有指令同時保留 `-data-dir <path>` 旗標（既有預設 `data/json_db`，見 § 7.1 相容條款）。JSON 回傳格式保持原樣，Python 端與 Wails backend 對它們的呼叫**完全不需要動**。

### 5.3 廢除 / no-op

| 指令 / 概念 | 退役行為 |
|-----------|---------|
| `db compact -json` | Phase C 起 no-op，回 `{"success":true,"noop":true,"reason":"sqlite has no journal to compact","journal_size":0,"needs_compact":false}` — 多帶 `journal_size` / `needs_compact` 是給 Python `IncrementalJSONDB` 解析時不爆（見 § 7.1） |
| `data.journal` / `data.index` | Phase C 起不再產生 |
| Rust `db-tool db-import-json` 主路徑 | Phase C 起 deprecation warning |

---

## 6. Backup / Restore

### 6.1 Phase A / B

沿用既有 `pkg/database` backup（JSON 壓縮 + 時戳檔名），SQLite 不另外備份（source of truth 仍 JSON）。`db verify-sync` 可隨時驗證 SQLite 副本健康度，`db resync-from-json` 可重建。

### 6.2 Phase C（沿用既有 CLI 名稱）

```
classifier.exe db backup-create
  1. 建立 data/backup/db_YYYYMMDD_HHMMSS.sqlite
  2. 複製策略（優先序，採可用第一個）：
     a) sqlite3_backup_init/_step/_finish API（小步複製，可被中斷）
        - 預期非阻塞，但仍可能在 page lock 階段短暫互斥
     b) VACUUM INTO 'backup/db_*.sqlite'
        - 完整一致快照，會持有 reserved/exclusive lock
        - 預期數秒內完成，會延遲並發寫入
     c) WAL checkpoint(TRUNCATE) + 控制鎖時間的 file copy
        - 最後保底；複製期間禁寫
     實作於背景 goroutine；總鎖定時間上限 5 秒（超時 abort + 回傳 error）
  3. PRAGMA integrity_check + PRAGMA quick_check 驗證
  4. 同時呼叫 db export-json 產出 data/backup/db_YYYYMMDD_HHMMSS.json
     （雙保險：SQLite 檔損毀時可從 JSON 重建）
  5. 失敗 → 刪部分備份檔，回傳 error

classifier.exe db backup-restore -backup-path data/backup/db_*.sqlite
  1. 取得 data/db.sqlite 的 exclusive write lock
  2. rename 現檔為 data/db.sqlite.pre_restore_<timestamp>
  3. 複製 backup 進來
  4. PRAGMA integrity_check
  5. 失敗 → rollback rename；成功 → 解鎖

classifier.exe db backup-restore -from-json data/backup/db_*.json
  = 內部呼叫 resync-from-json 流程（新旗標 -from-json 加進既有 backup-restore）

classifier.exe db backup-list     # 沿用既有
classifier.exe db backup-cleanup  # 沿用既有
```

**Backup 鎖定語意明示**：不承諾「永遠非阻塞」。Phase C 設計為**優先非阻塞 + 必要時短暫阻塞 + 鎖定時間上限**。GUI 顯示備份進度時應假設可能短暫互斥。

### 6.3 Rust db-tool 在 Phase C 的角色

```powershell
# verify：跑 PRAGMA integrity_check + schema_version + 業務邏輯檢查
cargo run --manifest-path tools-rs\Cargo.toml -- db-verify --sqlite data\db.sqlite

# benchmark：query 效能基準（與 Go modernc 對照）
cargo run --manifest-path tools-rs\Cargo.toml -- db-benchmark --sqlite data\db.sqlite

# cross-version-migrate：未來 schema v3 → v4 升級
cargo run --manifest-path tools-rs\Cargo.toml -- db-migrate --from v3 --to v4 --sqlite data\db.sqlite
```

db-tool **不**接 runtime 讀寫，只跑離線維護任務。`db-import-json` 主路徑退役，避免兩語言對 source of truth 並寫的競態。

---

## 7. Python / Wails / `pkg/database` 整合影響

### 7.1 Python（零變更 — 但有明確的相容條款）

**目標**：`src/services/go_cli.py`、`src/models/json_database.py`、`src/models/incremental_json_database.py`、`run_search.py`、`run_batch_search.py`、`web_searcher.py` 全部不需要改。

**為達成零變更，下列契約 Go 端必須維持**：

| 契約點 | 既有行為（`src/services/go_cli.py` 觀測） | Phase C 後 SQLite-only 對應 |
|--------|-------------------------------------|---------------------------|
| `-data-dir <path>` 旗標 | 預設 `data/json_db`；所有 `db *` 指令都接 | **保留旗標、保留預設值；採 compatibility lookup**。Go 端在 SQLite-only 階段以下列規則解析（**禁止**忽略旗標）：<br>1. 旗標值正規化後 = `data/json_db`（預設值，或顯式傳同樣路徑）→ 對映到 `data/db.sqlite`<br>2. 旗標值為其他自訂目錄 `<path>` → 解讀為 `<path>/db.sqlite`<br>3. **不**在 `data/json_db/` 下建立 `db.sqlite`<br>4. lookup 規則寫死在 Go 端，不需 config 檔；正規化採 `filepath.Clean` 後比對絕對路徑 |
| `db compact -json` 回傳 | Python 端 `IncrementalJSONDB` 預期看到 `success`、`journal_size`、`needs_compact` 等欄位 | no-op 回傳必須含 `{"success":true,"noop":true,"journal_size":0,"needs_compact":false,"reason":"..."}`，缺欄位會讓 Python 端 KeyError |
| `db stats` 回傳的 `Stats` 結構 | Python 端會讀 `journal_size` / `journal_age_seconds` / `dirty_videos` / `deleted_videos` / `dirty_actresses` / `dirty_links` / `needs_compact` / `total_videos` 等欄位 | SQLite-only 階段這些欄位**保留**：`journal_*` / `dirty_*` 一律回 0；`needs_compact = false`；`total_videos` 從 SQLite 算 |
| Backup 指令名稱 | `db backup-create` / `db backup-list` / `db backup-restore -backup-path X` / `db backup-cleanup` | 全部沿用，**不改名**（見 § 5.2） |
| Backup JSON 回傳 | `backup-create` 既有回傳含 `backup_path`（見 wiki/architecture/database.md 內 `clean-actresses -write` 流程） | 沿用該欄位；Phase C 後 `backup_path` 指向 .sqlite，**新增** `json_export_path` 指向同時產出的 JSON 快照 |
| `db backup-restore` 旗標 | 既有 `-backup-path` | 沿用；**新增** `-from-json` 旗標走 resync 流程（非取代） |
| Exit code | 成功 0、失敗非 0；degraded 不視為失敗 | 沿用 |

**任何違反上述契約的 Go 端變更，都會破壞 Python 零變更目標**。Phase A 結束的 release gate 應包含跑一輪既有 Python 整合測試（`tests/test_go_cli_contracts.py`）驗證上述契約。

### 7.2 Wails backend

- 直接 `import "actress-classifier/pkg/database"` 的部分：升級後自動換到新 store；介面契約保留
- 透過 subprocess 呼叫 `classifier.exe` 的部分：完全不變
- 新增 maintenance UI（optional）：診斷頁顯示 `db verify-sync` 結果、`sync_degraded_total` 計數、最近一次 backup 時間

### 7.3 `pkg/database` — DatabaseStore interface（**草案，實作期再定稿**）

下列簽名為 Phase A 實作起點，**不是最終契約**。實作 SQLiteStore 時，會基於下列考量定稿：
- 全量回傳 map 在大資料庫會吃光記憶體；目前 3K 規模可接受，但介面要預留 streaming / filter
- `ListVideoCodes` 給「只想列番號」場景；`GetVideos(codes)` 給「批次取多筆」；`QueryVideos(filter)` 給未來複雜查詢
- 取代既有 `JSONStore.GetAllVideos() map[string]*VideoData` 行為時，必須保證 Python helper（`json_database.py:570`、`incremental_json_database.py:242`）透過 `classifier.exe db list` 取到的 JSON 格式不變

```go
// pkg/database/store.go (draft)
type DatabaseStore interface {
    // 影片：單筆
    GetVideo(code string) (*VideoData, error)
    UpdateVideo(code string, data *VideoData) error
    DeleteVideo(code string) error

    // 影片：批次 / 列舉（拆三個動詞，避免一次性 map）
    ListVideoCodes() ([]string, error)              // 只回 code list
    GetVideos(codes []string) ([]*VideoData, error) // 批次取
    GetAllVideos() (map[string]*VideoData, error)   // 全量；CLI `db list` 與 Python helper 走這個
    QueryVideos(filter VideoFilter) ([]*VideoData, error) // 未來擴充，Phase A 可先回 ErrNotImplemented

    // 女優
    GetActress(id string) (*ActressData, error)
    UpdateActress(id string, data *ActressData) error
    ListActresses() (map[string]*ActressData, error)

    // 關聯
    AddLink(link *VideoActressLink) error
    ListLinks() ([]VideoActressLink, error)

    // 統計與維護
    GetStats() (*Stats, error)
    Backup(destPath string) error  // 對應 db backup-create；策略見 § 6.2
    Close() error
}

type VideoFilter struct {
    Studio        string   // 為空忽略
    SearchStatus  string
    ActressIDs    []string // 任一匹配
    UpdatedAfter  string   // RFC3339
    Limit         int
    Offset        int
}

// 三個實作：
//   JSONStore         (現有實作，Phase C 移除)
//   SQLiteStore       (新增，modernc.org/sqlite + database/sql)
//   DualWriteStore    (Phase A/B；wraps JSON + SQLite，協調雙寫)

type StoreMode int
const (
    ModeJSONOnly   StoreMode = iota
    ModeDualWrite
    ModeSQLiteOnly
)

type StoreConfig struct {
    Mode             StoreMode
    JSONPath         string
    SQLitePath       string
    UseSQLiteReads   bool   // Phase B feature flag
    SyncDegradedLog  string // 預設 data/sync_degraded.jsonl
}

func NewStore(cfg StoreConfig) (DatabaseStore, error)
```

**Journal / compact 觀念限定於 JSONStore**，SQLiteStore 不感知。`Stats.JournalSize` / `Stats.JournalAgeSeconds` 在 SQLiteStore 一律回 0、`NeedsCompact = false`（保留欄位讓 CLI JSON 回傳格式與 Python `IncrementalJSONDB` 相容）。

---

## 8. 風險與緩解

| 風險 | 影響 | 緩解 |
|------|------|------|
| modernc.org/sqlite 純 Go 效能比 mattn 慢 5–20% | 大量 query 時略慢 | 規模 < 10K 影片無感；保留換 mattn 退路（介面相同，只換 driver import） |
| 雙寫期 SQLite 失敗、JSON 成功 → 短期分歧 | 兩邊資料不同步 | degraded log 記錄、啟動與背景 replay、verify-sync 偵測；GUI 紅字提示使用者跑 resync |
| Migration 遇同 video 重複 actress（fail loudly） | 阻擋一次性 import | migration report 列出完整重複清單；提供 `db clean-actresses` 流程；緊急用 `--auto-create-missing-actresses` 跳過（但留報告） |
| Phase C 後使用者誤刪 `data/db.sqlite` | 主資料庫掉了 | `db backup-create` 同步產 .sqlite + .json 雙快照；`db backup-restore -from-json <file>` 可重建 |
| SQLite 檔損毀（斷電 / 磁碟壞） | DB 無法開啟 | WAL mode crash recovery；啟動時 `PRAGMA integrity_check`；損毀時 fallback 最近 backup |
| Rust db-tool 與 Go 端 schema 漂移 | 兩邊驗證不一致 | 抽 `schema.sql` 為 single source；Go 與 Rust 都 embed 同一份 |
| Phase A/B 寫入路徑效能下降（兩次磁碟寫） | GUI 寫入回應變慢 | SQLite 用 WAL + `synchronous=NORMAL`；實測預期 +20–50ms / 寫入 |
| Phase B fallback 計數 > 0 卻誤進 Phase C | 失去資料安全網 | release gate：`sqlite_read_fallback_total = 0` ≥ 1-2 releases 才能進 Phase C |
| Python 端透過 classifier.exe 寫 SQLite 時 CLI exit code 處理錯誤 | 寫入失敗被 Python 端誤判 | 維持現有 CLI exit code 慣例；degraded 不算寫入失敗（exit 0），JSON 寫失敗才 exit non-zero |
| `actresses.name` 無 UNIQUE，可能多筆同名 entity | 查詢結果不確定 | Phase A 結束前用 audit 工具 dump 同名清單；若全部審查過、用 `db clean-actresses` 合併後，未來 schema 升級可考慮加 UNIQUE |

---

## 9. 工程量估算（粗）

| Phase | 任務 | 估計 | Release gate |
|-------|------|------|--------------|
| **A** | 抽 `DatabaseStore` interface；SQLiteStore（schema、CRUD、stats、backup）；DualWriteStore；`db migrate-from-json` / `db verify-sync` / `db resync-from-json`；degraded log + 背景 replay；單元測試覆蓋；CI 跑 verify-sync | **2–3 週** | CI verify-sync 全綠 ≥ 1 release、`sync_degraded_total = 0`、在使用者真實資料上跑過 migration |
| **B** | `USE_SQLITE_READS` flag；讀路徑切 SQLite + fallback；Wails backend 切過去；端對端測試覆蓋；fallback 計數監測 | **1 週** | `sqlite_read_fallback_total = 0` ≥ 1-2 releases、verify-sync 全綠 |
| **C** | 移除 JSONStore / DualWriteStore；`db export-json`；`db backup-create` / `db backup-restore` 切 SQLite backup strategy（見 § 6.2）；`db compact -json` 改 no-op；Rust db-tool 重定位；wiki / pitfalls 更新 | **1 週** | 進入前必須有最近一次 `db backup-create` 產出的 .sqlite + .json 雙快照 |
| **總計** | | **4–5 週** | |

不含：使用者真實資料的 acceptance test 時間；Phase A/B 各自 1–2 週的 dogfood 觀察期。

---

## 10. 開放問題（待 implementation 時討論）

- **degraded log threshold 的具體值**：32 KiB 是初始建議，實際應依 user 寫入頻率調整
- **背景 replay goroutine 的退避策略**：失敗連續 N 次後是否退至下次啟動才重試？
- **`actresses.name` 是否未來加 UNIQUE**：Phase A 完成後可基於 audit 結果決定
- **Wails maintenance UI 是否在 Phase A 即提供**：可延後到 B 或 C
- **Python 端 `IncrementalJSONDB` 的 stats 欄位**：journal_size / dirty_videos 在 SQLite-only 階段一律 0，需確認 GUI 端不依賴非零值

---

## 11. 相關文件

- 現況：`wiki/architecture/sqlite-shadow-db.md`、`wiki/architecture/database.md`
- 程式碼基準：`pkg/database/types.go`、`tools-rs/src/sqlite_db.rs`
- 既有踩坑：`wiki/pitfalls/wails-db-format-migration.md`、`wails-db-json-never-updated.md`、`wails-db-path-wrong-dir.md`
