---
category: Wails
date: 2026-04-08
---
# Wails DB 路徑寫入錯誤目錄

> 歸檔日期：2026-04-07

---

## 症狀

搜尋完成後，資料寫入到：

```
wails-app/build/bin/data/json_db/data.json   ← 錯誤
```

而非專案根目錄：

```
data/json_db/data.json   ← 正確
```

導致重啟 app 後資料消失（快取失效）、Python 版與 Wails 版 DB 互不相通。

---

## 根本原因

`resolveConfigPath()` 只查找 **exe 同目錄**的 `config.ini`：

```go
// 修復前（錯誤）
func resolveConfigPath() string {
    exe, _ := os.Executable()
    candidate := filepath.Join(filepath.Dir(exe), "config.ini")
    if _, err := os.Stat(candidate); err == nil {
        return candidate  // 找不到就 fallback
    }
    return "config.ini"  // CWD 相對路徑
}
```

開發模式下 exe 在 `wails-app/build/bin/actress-classifier.exe`，同目錄沒有 `config.ini`，fallback 到 `"config.ini"`（CWD 相對路徑）。

`resolveDataDir()` 讀到 config 預設值 `"data/json_db"`（相對路徑），相對於 exe 的 CWD 而非專案根目錄，因此 DB 落到 `build/bin/data/json_db/`。

---

## 修正做法

`resolveConfigPath()` 增加往上查找專案根目錄（dev 模式：exe 往上 3 層）：

```go
// 修復後
func resolveConfigPath() string {
    exe, err := os.Executable()
    if err == nil {
        exeDir := filepath.Dir(exe)
        candidates := []string{
            filepath.Join(exeDir, "config.ini"),
            filepath.Join(exeDir, "..", "..", "..", "config.ini"), // build/bin → 專案根
        }
        for _, c := range candidates {
            if abs, err2 := filepath.Abs(c); err2 == nil {
                if _, err3 := os.Stat(abs); err3 == nil {
                    return abs
                }
            }
        }
    }
    return "config.ini"
}
```

`resolveDataDir()` 相對路徑時，相對於 **config.ini 所在目錄**解析（而非 CWD）：

```go
func resolveDataDir(cfgPath string) string {
    cfgSvc := services.NewConfigService(cfgPath)
    prefs, _ := cfgSvc.Load()
    dir := prefs.JSONDataDir
    if filepath.IsAbs(dir) {
        return dir
    }
    // 相對路徑相對 config 檔位置解析
    if cfgPath != "" && cfgPath != "config.ini" {
        if abs, err := filepath.Abs(filepath.Join(filepath.Dir(cfgPath), dir)); err == nil {
            return abs
        }
    }
    return dir
}
```

---

## 路徑解析結果（修復後）

| 執行情境 | config.ini 位置 | DB 路徑 |
|---------|----------------|---------|
| 開發（build/bin） | 專案根目錄（往上 3 層找到） | `專案根/data/json_db` ✅ |
| 發行（exe 同目錄有 config.ini） | exe 同目錄 | `config.ini 所在目錄/data/json_db` ✅ |

---

## 涉及檔案

- `wails-app/backend/app.go`：`resolveConfigPath()`、`resolveDataDir()`、`resolveLogDir()`
