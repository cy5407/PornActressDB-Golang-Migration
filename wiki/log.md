# Log

> append-only，每次 ingest / 重大更新 / 踩坑修復 後追加一筆。
> 格式：`## [YYYY-MM-DD] <類型> | <摘要>`
> 類型：`init` / `feature` / `fix` / `refactor` / `pitfall` / `lint`

---

## [2026-04-06] init | Wiki 初始建立

**內容**：
- 根據專案現況（v6.0.0）建立 wiki/ 初始結構
- 涵蓋架構總覽、5 個開發模式、5 個踩坑紀錄
- 來源：CLAUDE.md、AGENTS.md、茶包射手 Issue 1-15、本輪 session

**觸發原因**：
本次新增「DB 片商批次修正」功能期間，連續發生三個可預防的 Bug（Issue 13-15），根因都是缺乏明確的開發模式文件，AI 和開發者都沒有可查閱的快速參考。

---

## [2026-04-06] feature | DB 片商批次修正功能 (db fix-studios)

**涉及檔案**：
- `cmd/scanner/db_cmd.go` — 新增 `fix-studios` 子命令
- `src/services/go_api/db.py` — 新增 `db_fix_studios()`
- `src/services/go_api/__init__.py` — 匯出補齊
- `src/services/go_bridge.py` — 重匯出補齊
- `src/ui/main_gui.py` — 新增「🔧 修正片商資料」按鈕

**踩坑**：Issue 13、14、15（見 pitfalls/）

---

## [2026-04-06] fix | JAVDB False Positive

**涉及檔案**：`src/services/safe_javdb_searcher.py`
**踩坑**：Issue 12（見 pitfalls/javdb-false-positive.md）

---

## [2026-04-06] fix | PyInstaller 打包路徑修正

**涉及檔案**：`src/models/studio.py`
**踩坑**：PyInstaller 打包後 studios.json 應從 sys._MEIPASS 讀取（見 pitfalls/pyinstaller-path.md）
