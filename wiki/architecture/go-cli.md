# Go CLI 命令參考

> 來源：`cmd/scanner/main.go`、`go.mod`  
> 更新：2026-04-24

---

## 基本資訊

- **Go module**：`actress-classifier`
- **二進位名稱**：`classifier.exe`
- **建置指令**：`go build -o classifier.exe ./cmd/scanner`
  > ⚠️ 不要用 `go build cmd/scanner/main.go`，會漏掉 `colors.go` 等同套件檔案

---

## 命令樹

```
classifier.exe <命令> [選項]

├── scan       掃描目錄中的影片檔案，提取番號
├── move       移動檔案（單檔或批次）
├── history    查看操作歷史或回滾
├── db         資料庫操作（get / update / delete / list / stats / compact / merge / fix-studios / actress-get / actress-update / actress-delete / actress-list / clean-actresses / backup-create / backup-restore / backup-list / backup-cleanup / migrate-from-json / verify-sync / resync-from-json / export-json）
├── identify   識別番號所屬片商
├── cache      快取管理（stats/prune/clear/get/set/delete）
└── help       顯示說明
```

**向後相容**：第一個參數為 `-dir` 或 `-workers` 時，自動進入 scan 模式。

---

## scan 命令

```bash
classifier.exe scan [選項]
```

| 旗標 | 預設 | 說明 |
|------|------|------|
| `-dir` | `.` | 要掃描的目錄 |
| `-workers` | `10` | 並行工作數 |
| `-recursive` | `true` | 是否遞迴掃描子目錄 |
| `-progress` | `false` | 顯示掃描進度條（輸出至 stderr） |
| `-extract` | `""` | 從單一檔名提取番號 |

**範例**：
```bash
classifier.exe scan -dir "D:\Videos" -workers 10 -recursive=true
classifier.exe scan -extract "STARS-707.mp4"
classifier.exe scan -extract "200GANA-3376.mp4"
```

### 番號提取契約

`scan` 與 `scan -extract` 共用 `pkg/extractor.CodeExtractor`。目前支援的主要格式：

| 格式 | 範例 | 輸出 |
|------|------|------|
| 標準片商格式 | `STARS-707.mp4` | `STARS-707` |
| 無橫槓格式 | `STARS707.mp4` | `STARS-707` |
| 點/底線分隔 | `CAWD.456.mp4` / `IPX_123.mp4` | `CAWD-456` / `IPX-123` |
| 技術尾碼 | `SONE-240-60FPS.mp4` | `SONE-240` |
| 網站前綴 | `489155.com@MIMK-273.mp4` | `MIMK-273` |
| 括號番號 | `[SKMJ-310] title.mp4` | `SKMJ-310` |
| MGS 數字前綴 | `200GANA-3376.mp4` | `200GANA-3376` |

MGS / 素人系的 `數字 + 字母前綴 + - + 數字` 是有效番號本體，不能被正規化成 `GANA-3376` / `LUXU-1880` / `MIUM-1357`。對應測試位於 `pkg/extractor/extractor_test.go`。

已知仍需另案評估的邊界：
- 單字母前綴如 `G-487`、`Y-091`
- 尾碼字母保留如 `IBW-1006Z`

---

## move 命令

```bash
classifier.exe move [選項]
```

| 旗標 | 說明 |
|------|------|
| `-src` | 來源路徑 |
| `-dst` | 目標路徑 |
| `-kind` | `file`（預設）或 `dir` |
| `-strategy` | `skip`/`overwrite`/`rename` |
| `-batch` | 批次移動 JSON 檔案路徑 |

**範例**：
```bash
classifier.exe move -src "A.mp4" -dst "dest/A.mp4" -strategy skip
classifier.exe move -kind dir -src "A" -dst "B/A"
classifier.exe move -batch moves.json
```

---

## history 命令

```bash
classifier.exe history <子命令> [選項]
```

| 子命令 | 說明 |
|--------|------|
| `list` | 列出所有操作歷史 |
| `show <id>` | 顯示指定操作詳細記錄 |
| `rollback <id>` | 回滾指定操作 |
| `rollback --last` | 回滾最近一次 |

---

## db 命令

```bash
classifier.exe db <子命令> [選項]
```

| 子命令 | 說明 |
|--------|------|
| `get <code>` | 取得影片資料 |
| `update <code> <json>` | 更新影片資料 |
| `delete <code>` | 刪除影片記錄 |
| `list [--full]` | 列出所有影片番號（`--full` 含完整資料） |
| `stats [--actress] [--studio]` | 顯示資料庫統計；`--actress` 按女優、`--studio` 按片商 |
| `merge -source <path>` | 合併外部 JSON 資料庫 |
| `fix-studios` | 批次修正片商資料 |
| `actress-get <id>` | 取得女優資料 |
| `actress-update <id> <json>` | 新增/更新女優 |
| `actress-delete <id>` | 刪除女優 |
| `actress-list` | 列出所有女優 ID |
| `clean-actresses [-write]` | 清洗影片 `actresses` 欄位中的高信心污染名稱；預設 dry-run，加 `-write` 才寫回 DB |
| `backup-create` | 建立時間戳雙重備份（SQLite 備份 `backup_<ts>.sqlite` + 從 SQLite 匯出的 JSON 快照 `backup_<ts>.json`） |
| `backup-restore -backup-path <path>` | 從備份還原 |
| `backup-list` | 列出所有備份檔 |
| `backup-cleanup [-days N] [-max-count N]` | 清理過期/超量備份（預設 30 天、50 個） |

### `clean-actresses` 行為

- 真正實作位於：`pkg/database/actress_cleaner.go`
- CLI 入口位於：`cmd/scanner/db_cmd.go::runDBCleanActresses()`
- 預設為 dry-run：只回傳 JSON 報告，不改 DB
- 加 `-write` 後才會：
  1. 先建立 backup
  2. 套用清洗規則到所有影片
  3. 若有變更，逐筆透過 `UpdateVideo` 寫回 SQLite 資料庫

輸出 JSON 欄位：
- `success`
- `dry_run`
- `backup_path`（只有 `-write` 時會有）
- `scanned_videos`
- `changed_videos`
- `removed_actresses`
- `changes[]`（每筆包含 `code`、`before`、`after`、`removed`）

目前規則屬於「高信心清洗」而非通用 NLP 正規化，包含：
- 精準黑名單污染字串移除
- 已知合法女優名保留
- `三田` 只有在同一筆同時存在 `三田真鈴` 時才移除
- `蒼乃美月蒼乃美月` 這類重複拼接名稱，只有基底名已存在時才移除

**通用 db 旗標**：
| 旗標 | 說明 |
|------|------|
| `-data-dir` | 資料庫目錄（預設 `data/json_db`） |
| `-json` | 以 JSON 格式輸出 |
| `-write` | 真正寫入資料庫（`clean-actresses` 預設為 dry-run） |
| `-backup-path` | 指定還原備份路徑（用於 `backup-restore`） |
| `-days` | 備份保留天數（用於 `backup-cleanup`） |
| `-max-count` | 最大備份數量（用於 `backup-cleanup`） |

**fix-studios 專用旗標**：
| 旗標 | 說明 |
|------|------|
| `-data-dir` | 資料庫目錄（預設 `data/json_db`） |
| `-studios` | 片商規則檔（預設 `studios.json`） |
| `-force` | 強制覆蓋已有片商（非 UNKNOWN） |
| `--json` | no-op，相容性保留 |

---

## identify 命令

```bash
classifier.exe identify [選項] <番號>
classifier.exe identify -batch codes.txt
```

---

## cache 命令

```bash
classifier.exe cache <子命令> [選項]
```

| 子命令 | 說明 |
|--------|------|
| `stats` | 顯示快取統計 |
| `prune -ttl-days 7` | 清除過期快取 |
| `clear -confirm` | 清除所有快取 |
| `get <key>` | 取得快取值（base64） |
| `set <key> <value>` | 寫入快取 |
| `delete <key>` | 刪除快取鍵 |

---

## 輸出格式

所有命令輸出 **JSON 格式**（stdout），便於 Python 解析。  
錯誤訊息輸出到 **stderr**。

---

## 重要規範

### JSON stdout 規則

所有正式子命令都應讓 stdout 輸出 JSON，錯誤訊息輸出 stderr 並使用非零 exit code。

現行 Python 委派層 `src/services/go_cli.py::run()` 不會自動附加 `-json`；它直接解析 stdout JSON。因此新增子命令時，核心要求是穩定 JSON 契約，而不是一律宣告 `-json`。

`-json` no-op flag 只在下列情況需要保留：

- 既有子命令已公開支援，移除會破壞相容性。
- 某個現存 Python helper 或測試仍明確傳入 `-json`。
- 需要和舊 `go_api/go_runner` 時期的命令格式相容。

歷史背景可參考：[go-cli-json-flag-missing.md](../pitfalls/go-cli-json-flag-missing.md)。

### 新增子命令 Checklist
→ 詳見 [patterns/add-go-cli-command.md](../patterns/add-go-cli-command.md)

---

## 相關頁面

- [wiki/architecture/go-bridge.md](go-bridge.md)
- [wiki/patterns/add-go-cli-command.md](../patterns/add-go-cli-command.md)

## 相關踩坑

| 踩坑 | 觸發點 |
|------|--------|
| [go-extractor-bracket-format](../pitfalls/go-extractor-bracket-format.md) | `[CODE]` 格式被清空、PPV 位數、MGS 數字前綴等番號提取邊界 |
| [go-cli-json-flag-missing](../pitfalls/go-cli-json-flag-missing.md) 📦 | 歷史：舊 `go_runner` 架構自動附加 `-json`，新子命令未宣告就 ExitOnError |
| [go-api-export-missing](../pitfalls/go-api-export-missing.md) 📦 | 歷史：舊 `go_api/` 三層匯出架構，新增函式漏更新導致 AttributeError |
