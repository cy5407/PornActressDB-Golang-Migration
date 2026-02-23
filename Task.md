# 📋 Task List — PornActressDB-Golang-Migration 修復清單

**來源**：Code Review 報告（Claude + Gemini）
**建立日期**：2026-02-23
**完成日期**：2026-02-23
**優先順序**：Critical → Warning → Suggestion

---

## 🔴 Critical（必須修復）

- [x] **C-1** `journal.go` — `appendJournalEntry` 寫入後補上 `f.Sync()`，防止斷電遺失 journal 記錄
- [x] **C-2** `jsondb.go` — 修復 `BatchUpdate`：補上 `dirtyVideos` 更新、`journalSize++` 及 `saveIndex()` 呼叫
- [x] **C-3** `jsondb.go` — 所有 `saveIndex()` 呼叫點（第 295、337、376、520 行）改為檢查並處理回傳的 error
- [x] **C-4** `mover.go` — `copyFile` 補上 `dstFile.Sync()`、明確處理 `Close()` 的 error，複製失敗時清理不完整的目標檔案
- [x] **C-5** 將 `config.ini` 加入 `.gitignore`，提供 `config.ini.example` 範本，移除已提交的本機路徑

---

## 🟡 Warning（強烈建議修改）

- [x] **W-1** `extractor.go` — 將 `cleanFilename` 與 `validateCode` 內的 `regexp.MustCompile` 移至 `CodeExtractor` struct 初始化，避免重複編譯
- [x] **W-2** `main.go` — 將第 153 行的 `ext` 重新命名為 `fileExt`，消除對 CodeExtractor 的變數遮蔽
- [x] **W-3** 為 `JSONDatabase.Load`、`Mover.BatchMove`、`CacheManager.AutoCleanup` 等 I/O 函式加入 `context.Context` 第一參數
- [x] **W-4** `cache.go` — 重構 `AutoCleanup`，將 `CleanupExpired` 與 `CleanupBySize` 合併為一次 index 讀取 + 一次寫入，解決 TOCTOU 問題
- [x] **W-5** `mover.go` — 重構 `loadOperationLog`，改用 glob/prefix 直接定位日誌檔，避免載入全部日誌線性搜尋
- [x] **W-6** `main.go` / `dbCmd` — 將 `historyCmd` 的 `-log-dir` 和 `dbCmd` 的 `-data-dir` 改用 `flag.FlagSet` 統一解析

---

## 🟢 Suggestion（可選優化）

- [x] **S-1** 將 `interface{}` 統一替換為 `any`（Go 1.18+ 慣例）
- [x] **S-2** 將 `types.go` 的 `TestField` 及相關處理移至 `_test.go` 或以 build tag 隔離（加入明確注記，說明為測試專用）
- [x] **S-3** 將 `cache.New()` 重新命名為 `cache.NewCacheManager()`，符合 Go 命名慣例（保留 Deprecated 別名向後相容）
- [x] **S-4** 將 `identifier.go` 中硬編碼的 `MajorStudios` 清單移至 `major_studios.json` 集中維護
- [x] **S-5** 合併 `main.go` 與 `extractor.go` 中重複定義的 `supportedFormats`，改為 `extractor.SupportedFormats` exported 變數
- [x] **S-6** `mover.go` — 為 `generateUniqueName` 的無限迴圈加上上限（10000），超出時回傳時間戳後綴名稱

---

## 🔧 工具與流程

- [x] 在 CI 中整合 `golangci-lint run`（已建立 `.github/workflows/go-lint.yml`）
- [x] 確認 `.golangci.yml` 已啟用 `govet`（shadow）、`errcheck`、`ineffassign` linter

---

## 📊 進度統計

| 類別 | 總數 | 已完成 | 待處理 |
|------|------|--------|--------|
| Critical | 5 | 5 | 0 |
| Warning | 6 | 6 | 0 |
| Suggestion | 6 | 6 | 0 |
| 工具/流程 | 2 | 2 | 0 |
| **合計** | **19** | **19** | **0** |

---

## 📄 測試計畫

詳見 [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md)

---

## ✅ 測試結果（go test ./pkg/...）

```
ok  actress-classifier/pkg/cache       ✅
ok  actress-classifier/pkg/database    ✅
ok  actress-classifier/pkg/extractor   ✅
ok  actress-classifier/pkg/mover       ✅
ok  actress-classifier/pkg/studio      ✅
```
