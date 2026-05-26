---
status: archived
---

# SQLite 影子資料庫（歷史 / 已退役）

> 更新：2026-05-23（C3：runtime 已切換為 SQLite-only，本頁標歷史）

> ⚠️ **本頁描述的「shadow SQLite」第一版角色已退役。**
>
> - C2（2026-05-23）後，runtime source of truth 已從 JSON 切到 SQLite v3（`data/db.sqlite`）。
> - 「正式資料是 JSON、SQLite 是 shadow」的前提已不成立。
> - `tools-rs/db-tool` 的 `db-init` / `db-import-json` / `db-stats` / `db-compare-json` / `db-benchmark` / `query …` 仍可執行，但 schema 仍是 v2，**用途已退化為診斷 / 歷史比對**。`db-import-json` 跑時 stderr 會顯示 deprecated warning。
> - 新增的 `db-verify` / `db-migrate` 子命令對象是 v3 runtime SQLite，**不是這份 v2 shadow schema**。請改讀 [database.md](database.md) 對應段落。
>
> 本頁保留為歷史紀錄，方便理解第一版 shadow DB 的設計選擇與當時的邊界決策。

---

## 一句話（歷史背景）

Rust crate `db-tool`（位於 `tools-rs/`，Cargo package name `db-tool`、目錄就是 `tools-rs/` 本身，不是 `tools-rs/db-tool/`）原本是放在正式 JSON DB 旁邊的 SQLite 試驗場。

最初的設計目標：**不取代 `data.json` / `data.journal`，也不自動接進 Wails；只把 JSON DB 的資料整理成 SQLite 影子副本，安全地驗證「未來是否值得把主資料庫遷移到 SQLite」**。

→ 這個驗證已在 2026-05 完成；A1 ~ C2 把主資料庫真正搬到了 SQLite，本頁的 shadow 定位也就跟著退役。

---

## 第一版定位（歷史）

| 項目 | 狀態（當時） |
|------|------|
| 正式資料來源 | `data/json_db/data.json` + `data.journal` |
| SQLite 角色 | 可重建、可刪除的 shadow DB |
| 寫入主流程 | Go CLI / Go DB 維護 JSON DB |
| Wails 自動執行 | 不接入 |
| 主要用途 | import / stats / compare / benchmark / 人工檢視 |
| 固定 shadow DB 路徑 | `data/shadow.sqlite` |

當時的核心原則：**先證明 SQLite 影子資料與 JSON 等價，再談正式切換**。

---

## 為什麼不直接改成 SQLite 主資料庫

目前很多流程都假設 JSON DB 是 source of truth：

- Wails backend
- `classifier.exe db ...`
- Python 搜尋寫入委派
- backup / restore / compact
- journal replay
- 既有測試與資料維護工具

如果第一步就讓 Rust 直接寫 SQLite，會變成同時改資料庫格式、寫入流程、備份流程與 GUI 契約，風險太大。

因此第一版採用影子 DB：

```text
JSON DB 是正式來源
  ↓
Rust db-tool 匯入 SQLite
  ↓
SQLite 用於驗證、統計、比對與效能測試
```

---

## Journal 邊界

Go 的正式讀取視圖是：

```text
最新資料 = data.json + data.journal replay
```

因此 `data.journal` 非空時，單看 `data.json` 可能是落後快照。

`db-tool` 第一版不實作 journal replay，改採安全邊界：

- `data.journal` 不存在或 0 bytes：允許 import / compare
- `data.journal` 非空：預設 hard fail
- 加 `--allow-dirty-journal`：只供診斷，輸出 `source_consistent=false`

若要讓 `data.json` 成為乾淨快照，應由使用者明確執行：

```powershell
classifier.exe db compact
```

Rust 工具不會自動 compact，避免 sidecar 隱性修改 production DB。

---

## 版控慣例

`data/json_db/data.json` 可以作為共享資料主快照進版控；這份資料主要來自公開網路資料整理，容量也不大。

仍建議不要追蹤下列檔案：

| 檔案 | 原因 |
|------|------|
| `data/json_db/data.journal` | 執行期增量狀態，容易與 `data.json` 時點不一致 |
| `data/json_db/data.index` | dirty index / journal 統計，屬快取狀態 |
| `data/json_db/backup/` | 本機備份，數量與時點會快速膨脹 |
| `data/shadow.sqlite` | SQLite 影子 DB，可由 `data.json` 重建 |

若要提交 `data.json`，建議先執行 `classifier.exe db compact`，再跑 schema verify，確保提交的是乾淨主快照。

---

## Schema

底層仍採正規化結構：

| 表 / View | 用途 |
|-----------|------|
| `videos` | 影片本體：番號、標題、片商、狀態、原始 JSON |
| `video_actresses` | 影片與女優的對應關係 |
| `import_runs` | 每次匯入的來源、時間、筆數與一致性 |
| `videos_with_actresses` | 給人工檢視用的整合 view |

`videos_with_actresses` 把常看的欄位放在同一列：

```sql
SELECT code, title, studio, actresses
FROM videos_with_actresses
LIMIT 20;
```

這個 view 不複製資料，只是讓 terminal / GUI 檢視時比較直覺。

---

## CLI

### 建立 schema

```powershell
cargo run --manifest-path tools-rs\Cargo.toml -- db-init --sqlite data\shadow.sqlite --replace
```

### 匯入 JSON

```powershell
cargo run --manifest-path tools-rs\Cargo.toml -- db-import-json `
  --json "C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\data\json_db\data.json" `
  --sqlite data\shadow.sqlite `
  --replace
```

### 統計

```powershell
cargo run --manifest-path tools-rs\Cargo.toml -- db-stats --sqlite data\shadow.sqlite
```

### 比對 JSON / SQLite

```powershell
cargo run --manifest-path tools-rs\Cargo.toml -- db-compare-json `
  --json "C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\data\json_db\data.json" `
  --sqlite data\shadow.sqlite
```

### 效能測試

```powershell
cargo run --manifest-path tools-rs\Cargo.toml -- db-benchmark `
  --json "C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\data\json_db\data.json" `
  --sqlite data\shadow.sqlite `
  --iterations 10
```

`db-benchmark` 不會自動跑 compare。正確流程是先 compare 通過，再把 benchmark 結果視為有效。

---

## 實測結果

2026-04-27 在本機資料上匯入：

| 指標 | 數值 |
|------|------|
| 影片數 | 3363 |
| 女優關聯數 | 3698 |
| 無效記錄 | 0 |
| 重複女優 | 0 |
| 片商 distinct count | 332 |
| 空 title | 3323 |
| JSON / SQLite compare | success |
| source_consistent | true |
| import elapsed | 約 202 ms |

`empty_title_count` 高不是 import 錯誤；compare 已確認 SQLite 與 JSON 等價，代表原始 JSON 多數影片本來就沒有 title。

---

## 人工檢視 SQLite

如果沒有 `sqlite3.exe`，可以用 Bun 內建的 `bun:sqlite` 檢視：

```powershell
& 'C:\Users\cy5407\.bun\bin\bun.exe' -e 'import { Database } from "bun:sqlite"; const db = new Database("data/shadow.sqlite"); console.table(db.query("SELECT code, title, studio, actresses FROM videos_with_actresses WHERE actresses != '''' LIMIT 20").all()); db.close();'
```

大量輸出時不建議使用 `console.table`，可改成一筆一行或輸出到文字檔。

---

## 已踩到並修正的設計細節

- 討論匯出 MD 內包含舊草稿，實作時必須以最終收斂文件為準。
- `time` crate 必須啟用 `std` feature，才能穩定處理 `SystemTime`。
- `db-benchmark` 的 stats 測試不應把每輪開 SQLite 連線成本算進 query 計時。
- `duplicate_actresses` 是資料品質 warning，不應讓 compare 失敗。
- 人工檢視時需要 `videos_with_actresses` view，否則只看 `videos` 會誤以為沒有女優資料。

---

## 後續路線（歷史）

當時規劃分階段推進：

1. ~~Shadow SQLite：手動 import / compare / benchmark。~~ ✅ 已完成
2. ~~開發者 script：把 compact 檢查、import、compare 串成一個明確流程。~~ ✅ 由 Go CLI 接手
3. ~~Wails 診斷入口：提供手動按鈕或維護頁查看 shadow DB 狀態。~~ ⏸ 直接跳過
4. ~~SQLite 讀取快取：仍由 JSON 寫入，但可嘗試讀取加速。~~ ✅ B1 / B2
5. ~~SQLite 成為 source of truth：需重新設計 backup、restore、migration 與 Wails 寫入契約。~~ ✅ C1 / C2

→ 第 5 階段於 2026-05 完成（C2）；shadow DB 概念退役。後續以 v3 runtime SQLite 為準，請見 [database.md](database.md)。

---

## C3 之後的 db-tool 定位

| 子命令 | 對象 schema | 狀態 |
|--------|-------------|------|
| `db-init` / `db-import-json` / `db-stats` / `db-compare-json` / `db-benchmark` / `query …` | v2 shadow | **legacy**；`db-import-json` 有 deprecation warning |
| `db-verify` | v3 runtime | **新**（C3） |
| `db-migrate` | v3 runtime | **新**（C3）；目前只實作 v3 → v3 no-op |

`db-verify` / `db-migrate` 與本頁描述的「shadow DB」概念無關，它們對象是 [database.md](database.md) 中的 v3 runtime SQLite。

---

## 相關頁面

- [database.md](database.md) — **目前 SQLite-only 架構主頁**
- [go-cli.md](go-cli.md)
- [tech-stack-decisions.md](tech-stack-decisions.md)
