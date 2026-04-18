---
category: Wails
date: 2026-04-09
---
# Wails 片商名稱正規化與路徑解析錯誤

**日期**：2026-04-09（W8 任務）  
**嚴重度**：🟠 高（片商分類歸錯資料夾，影響大量檔案）

---

## 問題 A：`canonicalMajorStudio()` 大小寫不敏感匹配缺失

### 症狀

片商分類時，「SOD star」系列的影片被歸入 `単体企劃女優\` 而非 `SOD\` 資料夾，
即使 `major_studios.json` 中明確列有 `"SOD"` 條目。

### 根本原因

`canonicalMajorStudio()` 使用 `strings.HasPrefix` 進行精確匹配：

```go
// ❌ 修復前：大小寫敏感，前綴空格干擾
for _, major := range majors {
    if strings.HasPrefix(studio, major) {
        return major
    }
}
```

`studio` 值可能為 `"SOD star"`，而 `major` 為 `"SOD"`，
若 `studio` 有前綴空格（` SOD star`）或大小寫不同（`Sod`），比對直接失敗。

### 修復

```go
// ✅ 修復後：大小寫不敏感 + 前綴空格修剪 + longest-match-wins
func canonicalMajorStudio(studio string, majors []string) string {
    studio = strings.TrimSpace(studio)
    studioLower := strings.ToLower(studio)
    best := ""
    for _, major := range majors {
        majorLower := strings.ToLower(major)
        if strings.HasPrefix(studioLower, majorLower) {
            if len(major) > len(best) {
                best = major  // longest match wins
            }
        }
    }
    return best
}
```

**教訓**：片商名稱比對必須使用 `strings.ToLower` 正規化雙方，並用 longest-match-wins 避免 `"SOD"` 比 `"SOD Create"` 短而優先匹配的問題。

---

## 問題 B：`resolveMajorStudiosPath()` 找不到專案根目錄

### 症狀

Wails app 執行時找不到 `major_studios.json`，即使檔案已存在於專案根目錄，
導致所有影片都無法套用 major studio 分類。

### 根本原因

`resolveMajorStudiosPath()` 搜尋順序未涵蓋「從 EXE 往上三層到專案根目錄」：

```
wails-app/build/bin/actress-classifier.exe
                 ↑ EXE 位置
../../../major_studios.json  ← 需要往上三層才能到達
```

原本的搜尋路徑只查了：
1. EXE 同目錄（`build/bin/`）→ ❌ 沒有
2. 當前工作目錄 → ❌ 依啟動方式不同

### 修復

加入 `exe/../../../` 的搜尋路徑：

```go
func resolveMajorStudiosPath() string {
    candidates := []string{}
    
    if exePath, err := os.Executable(); err == nil {
        exeDir := filepath.Dir(exePath)
        candidates = append(candidates,
            filepath.Join(exeDir, "major_studios.json"),                   // build/bin/
            filepath.Join(exeDir, "..", "..", "..", "major_studios.json"), // 專案根目錄 ← 新增
        )
    }
    // ... cwd, 硬式路徑等 fallback
}
```

**教訓**：Wails build 產生的 EXE 在 `wails-app/build/bin/`，距離專案根目錄三層。路徑解析函式必須明確處理這個相對關係，尤其是開發期（`go run`）和 build 後（`*.exe`）的工作目錄不同。

---

## 副作用警告

W8 修復後，原本被誤分到 `単体企劃女優\` 的 63 個檔案需要手動處理：
- 方案 A（推薦）：使用「操作歷史 → 回滾」還原移動操作
- 方案 B：手動將檔案移回輸入目錄，再重新點「片商分類」

---

## 相關檔案

- `wails-app/backend/app.go` — `canonicalMajorStudio()`、`resolveMajorStudiosPath()`
- `major_studios.json` — 大片商名稱清單
