# Supervisor Worktree Check

本文件是對 worktree `C:\Users\cy5407\.codex\worktrees\4238\PornActressDB-Golang-Migration`
做的唯讀盤點。**未修改任何原始碼、設定檔或依賴檔**；不做 commit / push / reset /
checkout / clean / revert。

## 1. Git 狀態

- **目前 branch**：`codex/shadow-db-sqlite`
- **HEAD**：`ebdb3b3 fix: keep multi-part scan entries and document SQLite session`
- **working tree**：clean（`git status --short` 無輸出）
- **與主線關係**：CLAUDE.md 指出主分支為 `main`；本 worktree 在 codex 工作分支上。

## 2. 主要語言 / 框架判斷

這是 **多語言混合 repo**，根據根目錄 manifest 與檔案分佈：

| 層 | 語言 / 工具 | 證據 |
|----|-------------|------|
| 桌面 GUI 後端 | Go 1.25（Wails v2） | `wails-app/go.mod:3` 宣告 `go 1.25.0`；`require github.com/wailsapp/wails/v2 v2.12.0`（`wails-app/go.mod:7`）；`wails-app/wails.json:1` 為 wails config v2 |
| 桌面 GUI 前端 | TypeScript + React 18 + Vite 5 + Tailwind 3 + Zustand | `wails-app/frontend/package.json:8-32`（`vite`/`tsc`/`@vitejs/plugin-react`/`tailwindcss`/`zustand`） |
| CLI / DB runtime | Go 1.25，`modernc.org/sqlite v1.34.5`（純 Go SQLite 驅動） | `go.mod:3,7`；`pkg/database/sqlite_store.go` 等 30+ Go 測試檔 |
| 診斷工具 | Rust 2021，`rusqlite 0.31` bundled，`clap 4` | `Cargo.toml`（workspace）；`tools-rs/Cargo.toml:1-13` |
| 搜尋管線 / 測試 | Python ≥ 3.11，`pytest`、`ruff` | `pyproject.toml:4`（`requires-python = ">=3.11"`）；`requirements.txt:20-24`（pytest 套件） |
| 啟動器 | Python `run.py`、PowerShell `Start-ActressClassifier.bat` / `setup.ps1` | `run.py`、`setup.ps1` |

**架構判斷**：與 `CLAUDE.md` 第 13–18 行所述一致 — Wails GUI（`actress-classifier.exe`）
＋ Go CLI（`classifier.exe`）＋ Python 搜尋子程序 ＋ Rust `db-tool`。Runtime DB
為 SQLite v3（`data/db.sqlite`），JSON DB 退役為匯入 / 匯出 / 備份用。

## 3. 可能的測試命令

以下命令來自 `CLAUDE.md` 「建置與測試」段、CI workflow 設定與實際存在的測試檔案。
**未實際執行**，僅為對應入口的盤點。

### Go（runtime + CLI + Wails backend）

```powershell
# 核心 pkg 全套
go test .\pkg\... -v

# CLI 入口
go test .\cmd\scanner -v

# 單一 Go 測試
go test .\pkg\database -run TestNewStore_BootstrapFailureReturnsError -v

# Wails 後端（注意：wails-app/ 是獨立 module，須切目錄）
Set-Location wails-app
go test .\backend -v
```

### Rust（`db-tool` crate）

```powershell
Set-Location tools-rs
cargo test
```

> 根 `Cargo.toml` 為 workspace（`members = ["tools-rs"]`），所以亦可在根目錄
> `cargo test -p db-tool`。

### Python（搜尋管線 + 契約測試 + 整合測試）

```powershell
# 安裝相依（若尚未安裝）
pip install -r requirements.txt

# 全套
python -m pytest tests\ -q -p no:cacheprovider

# 僅整合測試（呼叫真實 classifier.exe / Python subprocess）
python -m pytest tests\integration\ -v --tb=short -p no:cacheprovider

# Go CLI 契約鎖（單檔）
python -m pytest tests\test_go_cli_contracts.py -q -p no:cacheprovider
```

### Wails 前端（型別檢查 / 建置）

```powershell
Set-Location wails-app\frontend
npm run build   # = tsc && vite build
npm run dev     # 本機 dev server
```

> 前端未發現專屬測試 runner（無 vitest / jest config）；驗證僅靠 `tsc` 與
> `vite build` 的型別與打包檢查。

### 端到端建置（驗證 release artefact）

```powershell
# 1) Go CLI
go build -o classifier.exe .\cmd\scanner

# 2) Wails GUI
Set-Location wails-app
wails build

# 3) Portable zip（含兩支 exe + 設定 + Python 依賴）
.\setup.ps1
```

## 4. 實際檢查到的檔案證據

### 4.1 根目錄

- `go.mod`、`go.sum` — Go module `actress-classifier`（`go.mod:1`），Go 1.25
- `Cargo.toml`、`Cargo.lock` — Rust workspace，唯一成員 `tools-rs`
- `pyproject.toml` — Python 專案 `pornactressdb` v6.0.0，requires Python ≥ 3.11
- `requirements.txt` — 含 pytest 系列（pytest / pytest-asyncio / pytest-cov / pytest-mock / pytest-timeout）
- `run.py`、`setup.ps1`、`Setup-SearchRuntime.ps1`、`Start-ActressClassifier.bat` — 啟動 / 打包入口
- `actress-classifier.exe`（15.7 MB，5/25 build）、`classifier.exe`（10.8 MB，5/25 build）— **已建置的二進位存在於 worktree**
- `CLAUDE.md`、`AGENTS.md`、`CODING_STANDARDS.md`、`README.md`、`implementation-notes.md` — 規範與設計紀錄
- `studios.json`、`major_studios.json`、`config.ini`、`config.ini.example` — runtime 設定資源

### 4.2 Go 測試檔（共 28 個 `_test.go`）

關鍵：

- `pkg/database/*_test.go` — 14 個，涵蓋 SQLite store、bootstrap、backup、migrate-from-json、verify-sync、export-json、resync、actress cleaner、legacy links、data dir lookup
- `pkg/mover/*_test.go` — 6 個，含 Windows recycle 行為
- `pkg/cache`、`pkg/extractor`、`pkg/studio`、`pkg/pathutil`、`pkg/safefile`、`pkg/app` 皆有對應測試
- `cmd/scanner/main_test.go` — CLI 入口
- `wails-app/backend/app_test.go` + `integration_test.go` — Wails backend

### 4.3 Rust 測試

- `tools-rs/src/v3_schema.rs::tests` — 內嵌單元測試（含 schema 漂移檢查）
- `tools-rs/tests/integration_db_tool.rs` — 整合測試（schema 漂移 + `db-verify` 多 case）

### 4.4 Python 測試（`tests/` 共 50+ 檔）

- 契約鎖：`tests/test_go_cli_contracts.py`、`tests/test_split_search_entrypoints.py`
- 整合（呼叫真實子程序）：
  - `tests/integration/test_classifier_scan_subprocess_smoke.py`
  - `tests/integration/test_go_cli_scan_subprocess_smoke.py`
  - `tests/integration/test_go_cli_smoke.py`
  - `tests/integration/test_scanner_go_cli_smoke.py`
  - `tests/integration/test_search_entrypoint_subprocess_smoke.py`
  - `tests/integration/test_db_cli_contract.py`
- 爬蟲：`tests/test_avwiki_scraper.py`、`test_javdb_scraper.py`、`test_shiroutowiki_scraper.py`、`test_safe_javdb_searcher.py`、`test_safe_searcher.py`
- DB / utils：`test_json_database.py`、`test_incremental_db.py`、`test_json_utils.py`、`test_log_sanitizer.py`、`test_retry_utils.py`
- Coverage 系列：大量 `test_coverage_*.py`
- 共用 fixture：`tests/conftest.py`、`tests/fixtures/json_db_minimal/data.json`（CI release gate 用）

### 4.5 CI workflows（`.github/workflows/`，共 8 個）

- `go-lint.yml`、`python-test.yml`、`rust.yml`、`integration-test.yml`
- `sqlite-verify-sync.yml` — Phase A 釋出閘：build `classifier` → `db migrate-from-json` → `db verify-sync`（觸發路徑見 `.github/workflows/sqlite-verify-sync.yml:11-27`）
- `portable-release.yml`、`sonar.yml`、`copilot-refactor-go.yml`

### 4.6 已有文件

- `docs/build-test.md` — 保守 release smoke checklist（已存在，本次未動）
- `implementation-notes.md` — SQLite 遷移 C1 / C2 / C3 設計紀錄（41 KB）
- `wiki/` — 架構與 pitfall 知識庫（`wiki/architecture/database.md` 為權威 DB 參考）

### 4.7 Lint / Quality 設定（僅盤點）

- `.golangci.yml` — Go lint 規則
- `pyproject.toml [tool.ruff]` — Python lint 規則
- `.codecov.yml`、`sonar-project.properties` — 覆蓋率 / 靜態分析整合
- `.editorconfig`、`.gitattributes`、`.gitignore`、`.gitleaksignore`

## 5. 下一步建議

依風險高低排序，**全部為建議，未自動執行**：

1. **先跑 SQLite verify-sync release gate**（與 CI 同一條路徑），確認本地 build
   能通過 Phase A 閘：
   ```powershell
   go build -o classifier.exe .\cmd\scanner
   .\classifier.exe db migrate-from-json -data-dir tests\fixtures\json_db_minimal
   .\classifier.exe db verify-sync     -data-dir tests\fixtures\json_db_minimal
   ```
   這條鏈直接對映 `.github/workflows/sqlite-verify-sync.yml` step 1 / 3 / 4，
   失敗即代表 PR 會被擋。

2. **再跑 Go 核心測試**：`go test .\pkg\... -v`、`go test .\cmd\scanner -v`，
   以及 `Set-Location wails-app; go test .\backend -v`。`pkg/database/`
   有 14 個測試檔且本分支名為 `codex/shadow-db-sqlite`，相關回歸風險最高。

3. **schema 漂移檢查**：本 repo 用 `//go:embed sqlite_schema.sql`（Go）＋
   `include_str!`（Rust）共用 canonical schema，有四道測試固定（見 `CLAUDE.md`
   「Schema 共用」段）。改 SQLite schema 前後都要跑：
   ```powershell
   go test .\pkg\database -run TestSQLiteSchemaSQL_MatchesCanonicalFile -v
   Set-Location tools-rs; cargo test
   ```

4. **Python 契約測試**：`python -m pytest tests\test_go_cli_contracts.py -q
   -p no:cacheprovider`。這是 GUI / 搜尋層呼叫 `classifier.exe` 的契約鎖；
   Go CLI 任何 flag / JSON 欄位變動都會在這裡爆。

5. **整合 smoke**：`python -m pytest tests\integration\ -v --tb=short
   -p no:cacheprovider`。會實際 spawn `classifier.exe` 與 Python subprocess，
   能抓到 binary 路徑 / 環境變數類問題。

6. **如要驗 GUI**：跑 `cd wails-app\frontend; npm run build` 確保 TS / Vite
   不破，再 `cd ..; wails build` 重生 `actress-classifier.exe`。前端無單元
   測試 runner，主要靠 `tsc` 把關。

7. **不建議** 自動：
   - 不要直接編 `cmd\scanner\main.go`（會漏掉同 package 其他 `.go` 檔），
     一律 `go build -o classifier.exe .\cmd\scanner`（`CLAUDE.md` 已警告）。
   - 不要手改 `data\db.sqlite` 或 `data\json_db\data.json`，走 CLI / API。
   - 不要把 `sqlite_schema.sql` 搬到別處（`//go:embed` 拒絕 `..` 路徑）。

## 6. 實際驗證結果（2026-05-26）

承接第 5 節「下一步建議」第 1–2 點，本次實際執行 SQLite verify-sync release
gate 與 Go 核心測試。所有命令在 worktree 根目錄、PowerShell 7 下執行。

### 6.1 命令總覽

| # | 命令 | 結果 | 備註 |
|---|------|------|------|
| 1 | `go build -o classifier.exe .\cmd\scanner` | **PASS** (exit 0) | 重新建置 `classifier.exe` |
| 2 | `.\classifier.exe db migrate-from-json -data-dir tests\fixtures\json_db_minimal` | **PASS** (exit 0) | 匯入 3 videos / 3 actresses / 4 links |
| 3 | `.\classifier.exe db verify-sync -data-dir tests\fixtures\json_db_minimal` | **PASS** (exit 0) | `consistent: true`，計數與匯入一致 |
| 4 | `go test .\pkg\... -v` | **PASS** | 8 packages 全綠（共 321 個 `--- PASS`） |
| 5 | `go test .\cmd\scanner -v` | **PASS** (exit 0) | 19 個 `--- PASS`，無 `--- FAIL` |

### 6.2 重點輸出

**(2) `db migrate-from-json`**
```json
{
  "success": true,
  "source_path": "tests\\fixtures\\json_db_minimal\\data.json",
  "sqlite_path": "tests\\fixtures\\json_db_minimal\\db.sqlite",
  "videos_imported": 3,
  "actresses_imported": 3,
  "links_imported": 4,
  "elapsed_ms": 0
}
```

**(3) `db verify-sync`**
```json
{
  "consistent": true,
  "video_count": 3,
  "actress_count": 3,
  "link_count": 4
}
```

**(4) `go test .\pkg\... -v` 各 package 結果**
```
ok  	actress-classifier/pkg/app	(cached)
ok  	actress-classifier/pkg/cache	(cached)
ok  	actress-classifier/pkg/database	4.252s
ok  	actress-classifier/pkg/extractor	(cached)
ok  	actress-classifier/pkg/mover	(cached)
ok  	actress-classifier/pkg/pathutil	(cached)
ok  	actress-classifier/pkg/safefile	(cached)
ok  	actress-classifier/pkg/studio	0.237s
```
> `pkg/database` 為唯一非 cached、耗時 4.25 s 的 package（含
> `TestNewStore_BootstrapFailureReturnsError` 等 SQLite-only 測試）。
> log 中出現的「FAIL」字串均屬測試名稱（如
> `TestBootstrapFailureReturnsError`、`TestBatchMove_PartialFailure`、
> `TestBackup_AutoStrategy_ReportsBothErrorsWhenBothStrategiesFail`），
> 非 `--- FAIL` 結果列。

**(5) `go test .\cmd\scanner -v` 結尾**
```
ok  	actress-classifier/cmd/scanner	0.447s
```

### 6.3 驗證結論

- Phase A 釋出閘（`.github/workflows/sqlite-verify-sync.yml` step 1 / 3 / 4）
  在本 worktree 可在本地 reproduces，且全綠 — 等同於 PR 不會被該 workflow 擋。
- Go runtime + CLI 核心測試（`pkg/...` + `cmd/scanner`）全綠，沒有回歸。
- 本次未跑 Wails backend 測試、Rust `cargo test`、Python pytest 與 Wails
  前端建置；如要完整對齊第 5 節清單剩餘項目，請再行執行。

## 7. 本文件未涵蓋

- 跨 commit 的差異（與 `main` 的 diff、PR scope）— 未在本文件範圍內。
- 安全 / lint 工具掃描結果（ruff / gitleaks / clippy 等）— 未跑；如需請改用
  `tool-scan` skill。
- Wails backend / Rust / Python 測試實際結果 — 本次未執行（見 6.3）。
