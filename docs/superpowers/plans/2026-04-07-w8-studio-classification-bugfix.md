# W8 片商分類 Bugfix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修復 W7 片商分類功能的兩個 Bug，讓「🏢 片商分類」按鈕能正確依 major_studios.json 分類女優到對應片商資料夾。

**Architecture:** Bug A：`resolveMajorStudiosPath()` 只找 exe 同目錄，而 `wails-app\build\bin\` 沒有 `major_studios.json`，導致 `majorStudios` 是空 map，所有片商不匹配。Bug B：片商名稱比對是大小寫敏感完全比對，DB 存的是 `"SOD star"`，但 major_studios.json 有的是 `"SOD"`，導致即使找到 major_studios.json 仍然不匹配。修復方式：對齊 `resolveConfigPath()` 的多路徑搜尋策略 + 新增 `matchesMajorStudio()` helper 做大小寫不敏感前綴比對。

**Tech Stack:** Go 1.21+，`wails-app/backend/app.go`，`wails-app/backend/app_test.go`

---

## 根本原因分析

### Bug A：major_studios.json 找不到

`resolveMajorStudiosPath()` 只找 `exeDir/major_studios.json`。
exe 位於 `wails-app\build\bin\`，裡面只有 `studios.json`，沒有 `major_studios.json`。
→ `loadMajorStudios()` 讀檔失敗 → 返回 `map[string]bool{}` → `majorStudios` 空 map。
→ `a.majorStudios[studio]` 永遠 false → 全部進 `"單體企劃女優"`。

修復：同 `resolveConfigPath()` 加第二個搜尋路徑：`exeDir/../../../major_studios.json`（開發時為專案根目錄）。

### Bug B：片商名稱大小寫/後綴不匹配

DB journal 中 START-539 的 studio = `"SOD star"`（來自 AV-WIKI）。
major_studios.json 中是 `"SOD"`（大寫，無後綴）。
→ `"SOD star" ∈ majorStudios` = false → 進 `"單體企劃女優"`。

類似問題：
- `"Fitch"` vs `"FITCH"`（大小寫）
- `"S1 NO.1 STYLE"` vs `"S1"`（後綴）

修復：`loadMajorStudios()` 存 uppercase key；新增 `matchesMajorStudio()` 做大小寫不敏感比對，支援 prefix 比對（`"SOD STAR"` 有前綴 `"SOD "`）。

---

## Files

| 操作 | 檔案 | 說明 |
|------|------|------|
| Modify | `wails-app/backend/app.go` | `resolveMajorStudiosPath()`, `loadMajorStudios()`, 新增 `matchesMajorStudio()`, 更新 `GetActressPrimaryStudios()` |
| Modify | `wails-app/backend/app_test.go` | 新增 `TestMatchesMajorStudio_*` + `TestGetActressPrimaryStudios_*` 測試 |

---

## Task 1：修復 major_studios.json 路徑解析 + 片商名稱比對

**Files:**
- Modify: `wails-app/backend/app.go`
- Modify: `wails-app/backend/app_test.go`

### 1-1：寫 `matchesMajorStudio` 的失敗測試

- [ ] 在 `wails-app/backend/app_test.go` 末尾加入以下測試：

```go
// ============================================================================
// matchesMajorStudio
// ============================================================================

func TestMatchesMajorStudio(t *testing.T) {
    majors := map[string]bool{
        "S1":        true,
        "SOD":       true,
        "MOODYZ":    true,
        "FITCH":     true,
    }
    cases := []struct {
        studio string
        want   bool
    }{
        {"S1", true},           // exact match
        {"s1", true},           // case insensitive
        {"SOD", true},          // exact
        {"SOD star", true},     // prefix with space
        {"SOD CREATE", true},   // prefix with space
        {"Fitch", true},        // case insensitive exact
        {"FITCH", true},        // exact uppercase
        {"MOODYZ", true},       // exact
        {"LOCK-ON", false},     // unrelated
        {"", false},            // empty
        {"S10", false},         // should NOT match "S1" without space separator
    }
    for _, c := range cases {
        t.Run(c.studio, func(t *testing.T) {
            got := matchesMajorStudio(c.studio, majors)
            if got != c.want {
                t.Errorf("matchesMajorStudio(%q) = %v, want %v", c.studio, got, c.want)
            }
        })
    }
}
```

- [ ] 執行測試確認失敗（函式尚未存在）：

```powershell
cd wails-app
go test ./backend/... -run TestMatchesMajorStudio -v
```

期望：`FAIL — undefined: matchesMajorStudio`

### 1-2：實作 `matchesMajorStudio` 並修復 `loadMajorStudios`

- [ ] 在 `wails-app/backend/app.go` 的 `loadMajorStudios()` 函式（約 L656）中，將 keys 改為大寫：

```go
// loadMajorStudios 載入 major_studios.json，返回片商名稱 set（keys 大寫）。
// 若檔案不存在或解析失敗，返回空 map（不 fatal）。
func (a *App) loadMajorStudios() map[string]bool {
    path := resolveMajorStudiosPath()
    data, err := os.ReadFile(path)
    if err != nil {
        return map[string]bool{}
    }
    var names []string
    if err := json.Unmarshal(data, &names); err != nil {
        return map[string]bool{}
    }
    result := make(map[string]bool, len(names))
    for _, name := range names {
        result[strings.ToUpper(strings.TrimSpace(name))] = true
    }
    return result
}
```

- [ ] 在 `loadMajorStudios()` 函式之後新增 `matchesMajorStudio()` helper（注意 `strings` 已在 import 中）：

```go
// matchesMajorStudio 判斷 studio 是否屬於大片商，支援：
//   - 大小寫不敏感完全比對（"s1" → "S1"）
//   - 前綴比對（"SOD star" → "SOD"）
// majorStudios 的 key 必須已為大寫（由 loadMajorStudios 保證）。
func matchesMajorStudio(studio string, majorStudios map[string]bool) bool {
    upper := strings.ToUpper(strings.TrimSpace(studio))
    if upper == "" {
        return false
    }
    if majorStudios[upper] {
        return true
    }
    for major := range majorStudios {
        if strings.HasPrefix(upper, major+" ") {
            return true
        }
    }
    return false
}
```

- [ ] 執行測試確認通過：

```powershell
cd wails-app
go test ./backend/... -run TestMatchesMajorStudio -v
```

期望：`PASS — 11/11 subtests passed`

### 1-3：更新 `GetActressPrimaryStudios()` 使用新 helper

- [ ] 在 `wails-app/backend/app.go` 的 `GetActressPrimaryStudios()` 中（約 L580）：

舊：
```go
case a.majorStudios[studio]:
    result[name] = studio // 大片商
```

新（使用 `matchesMajorStudio`，並返回標準化片商名）：
```go
case matchesMajorStudio(studio, a.majorStudios):
    // 返回 major_studios.json 中對應的標準名稱（大寫）
    upper := strings.ToUpper(strings.TrimSpace(studio))
    canonical := upper
    for major := range a.majorStudios {
        if upper == major || strings.HasPrefix(upper, major+" ") {
            canonical = major
            break
        }
    }
    result[name] = canonical // 大片商，使用標準名（如 "SOD"、"S1"）
```

> **注意**：片商資料夾名稱改為 `canonical`（大寫標準名），而非原始 DB 值，確保一致性。

### 1-4：修復 `resolveMajorStudiosPath()` 搜尋範圍

- [ ] 在 `wails-app/backend/app.go` 中找到 `resolveMajorStudiosPath()`（約 L644），改為：

```go
// resolveMajorStudiosPath 尋找 major_studios.json：exe 同目錄 → 專案根目錄 → CWD。
func resolveMajorStudiosPath() string {
    exe, err := os.Executable()
    if err == nil {
        exeDir := filepath.Dir(exe)
        candidates := []string{
            filepath.Join(exeDir, "major_studios.json"),
            filepath.Join(exeDir, "..", "..", "..", "major_studios.json"), // wails-app/build/bin → project root
        }
        for _, c := range candidates {
            if abs, err2 := filepath.Abs(c); err2 == nil {
                if _, err3 := os.Stat(abs); err3 == nil {
                    return abs
                }
            }
        }
    }
    return "major_studios.json"
}
```

### 1-5：寫 `GetActressPrimaryStudios` 的整合測試

- [ ] 在 `wails-app/backend/app_test.go` 末尾新增：

```go
// ============================================================================
// GetActressPrimaryStudios
// ============================================================================

func TestGetActressPrimaryStudios_MajorStudio(t *testing.T) {
    app := newTestApp(t)

    // 設定 majorStudios（模擬 major_studios.json）
    app.majorStudios = map[string]bool{
        "SOD":    true,
        "S1":     true,
        "FITCH":  true,
    }

    // 在測試 DB 中插入一筆 SOD star 的影片
    app.ensureDB()
    ctx := context.Background()
    _ = app.db.AddOrUpdateVideo(ctx, map[string]interface{}{
        "code":     "START-539",
        "studio":   "SOD star",
        "actresses": []string{"神木麗"},
    })

    result := app.GetActressPrimaryStudios([]string{"神木麗"})

    got, ok := result["神木麗"]
    if !ok {
        t.Fatal("expected key 神木麗 in result")
    }
    if got != "SOD" {
        t.Errorf("expected SOD, got %q", got)
    }
}

func TestGetActressPrimaryStudios_NonMajor(t *testing.T) {
    app := newTestApp(t)
    app.majorStudios = map[string]bool{
        "SOD": true,
    }

    app.ensureDB()
    ctx := context.Background()
    _ = app.db.AddOrUpdateVideo(ctx, map[string]interface{}{
        "code":     "LOCK-006",
        "studio":   "LOCK-ON",
        "actresses": []string{"糸井瑠花"},
    })

    result := app.GetActressPrimaryStudios([]string{"糸井瑠花"})
    got := result["糸井瑠花"]
    if got != "單體企劃女優" {
        t.Errorf("expected 單體企劃女優, got %q", got)
    }
}

func TestGetActressPrimaryStudios_NoData(t *testing.T) {
    app := newTestApp(t)
    app.majorStudios = map[string]bool{"SOD": true}
    app.ensureDB()

    result := app.GetActressPrimaryStudios([]string{"不存在的女優"})
    got := result["不存在的女優"]
    if got != "" {
        t.Errorf("expected empty string, got %q", got)
    }
}
```

> **注意**：若 `app.db.AddOrUpdateVideo` 函式簽名不同，請先執行 `grep -n "AddOrUpdateVideo\|AddVideo\|UpsertVideo" pkg/database/jsondb.go` 確認實際函式名，並調整測試程式碼。

- [ ] 執行所有 backend 測試確認通過：

```powershell
cd wails-app
go test ./backend/... -v -timeout 30s
```

期望：所有測試（含新增的 `TestMatchesMajorStudio` 和 `TestGetActressPrimaryStudios_*`）通過。

### 1-6：Commit

- [ ] 提交修改：

```powershell
cd ..
git add wails-app/backend/app.go wails-app/backend/app_test.go
git commit -m "fix(backend): fix major_studios.json path resolution and studio name matching

- resolveMajorStudiosPath: add project root as fallback (same as resolveConfigPath)
- loadMajorStudios: store keys as uppercase for case-insensitive matching
- add matchesMajorStudio(): case-insensitive + prefix match (SOD star → SOD)
- GetActressPrimaryStudios: use matchesMajorStudio, return canonical studio name

Fixes: all actresses going to 単体企劃女優 when major_studios.json not in exe dir

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2：建置驗證 + 推送

**Files:**
- Build: `wails-app/build/bin/actress-classifier.exe`

### 2-1：執行 Go 全套測試

- [ ] 在專案根目錄執行所有 Go 測試：

```powershell
go test ./pkg/... -v -timeout 60s
```

期望：所有 `pkg/` 套件測試通過（PASS）。

- [ ] 執行 backend 測試：

```powershell
cd wails-app
go test ./backend/... -timeout 30s
```

期望：PASS，無失敗。

### 2-2：Wails Build

- [ ] 在 `wails-app/` 目錄執行：

```powershell
wails build
```

期望：
```
Build successful
```
產出 `wails-app/build/bin/actress-classifier.exe`。

### 2-3：驗證 major_studios.json 可被找到

- [ ] 確認 build 目錄與專案根目錄的相對路徑正確：

```powershell
# 從 build/bin 往上三層應到達專案根目錄
$root = "C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration"
Test-Path (Join-Path $root "major_studios.json")
```

期望：`True`（表示 `exeDir/../../../major_studios.json` = 專案根目錄的檔案）。

- [ ] 如果已有 `major_studios.json` 需要複製到 exe dir（Release 情境）：

```powershell
Copy-Item .\major_studios.json .\wails-app\build\bin\major_studios.json -Force
```

> **Release 注意事項**：若發布給其他使用者，`major_studios.json` 必須與 `actress-classifier.exe` 放在同一目錄。考慮在 wails build 後加入此 Copy-Item 步驟到發布流程。

### 2-4：Commit + Push

- [ ] 推送到遠端：

```powershell
git push origin feature/w7-studio-classification
```

---

## 注意事項

### DB 函式名確認

在 Task 1-5 的測試中，需確認 `db.AddOrUpdateVideo` 的實際簽名。執行：

```powershell
Select-String -Path "pkg\database\jsondb.go" -Pattern "func.*AddOrUpdate|func.*AddVideo|func.*Upsert" | Select-Object Line
```

若函式名不同，依實際名稱調整測試。

### 現有錯誤分類的檔案

用戶的 `C:\Users\cy5407\Downloads\AV\単体企劃女優` 裡已有錯誤分類的檔案。修復 Bug 後重新執行片商分類不會自動修復已移動的檔案。用戶需手動或透過「操作歷史→回滾」處理。

### 片商資料夾名稱標準化

修復後，片商資料夾名稱統一為 `major_studios.json` 中的大寫標準名（如 `"SOD"`、`"S1"`），而非 DB 原始值（如 `"SOD star"`）。這確保即使 AV-WIKI 回傳不同後綴，都歸到同一個資料夾。
