# Go CLI 命令參考

> 來源：`cmd/scanner/main.go`、`go.mod`  
> 更新：2026-04-06

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
├── db         資料庫操作（get/update/delete/list/stats/merge/fix-studios）
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
```

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
| `backup-create` | 建立時間戳備份（data.json → backup/backup_YYYY-MM-DD_HH-MM-SS.json） |
| `backup-restore -backup-path <path>` | 從備份還原 |
| `backup-list` | 列出所有備份檔 |
| `backup-cleanup [-days N] [-max-count N]` | 清理過期/超量備份（預設 30 天、50 個） |

**fix-studios 旗標**：
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

### `-json` Flag 規則
**每個新增的子命令必須宣告 `-json` no-op flag**：

```go
fs := flag.NewFlagSet("子命令名", flag.ExitOnError)
_ = fs.Bool("json", false, "輸出 JSON 格式（預設即為 JSON，保留相容性）")
```

原因：Python 呼叫慣例固定傳 `--json`，若未宣告，`flag.ExitOnError` 會因未知 flag 退出。  
→ 相關 pitfall：[go-cli-json-flag-missing.md](../pitfalls/go-cli-json-flag-missing.md)

### 新增子命令 Checklist
→ 詳見 [patterns/add-go-cli-command.md](../patterns/add-go-cli-command.md)

---

## 相關頁面

- [wiki/architecture/go-bridge.md](go-bridge.md)
- [wiki/patterns/add-go-cli-command.md](../patterns/add-go-cli-command.md)
