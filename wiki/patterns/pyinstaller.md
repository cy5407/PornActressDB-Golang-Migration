> [!NOTE]
> 此文件為歷史存檔。PyInstaller 打包流程已於 W1~W6 重構中移除。
> 目前發行版由 Wails 建置（`wails build`），產出 actress-classifier.exe。
> 本頁內容僅供參考舊版相容性，請勿作為目前的重建指引。

# PyInstaller 打包指南

> 來源：`女優分類系統_修復版.spec`  
> 更新：2026-04-06

---

## 概述

本專案使用 PyInstaller 打包為單一 Windows EXE。**主要使用的 spec 是 `女優分類系統_修復版.spec`**（另有一個舊版 `actress_classifier.spec` 較精簡）。

---

## 建置步驟

```powershell
# 1. 建置 Go CLI（必須先做，因為 spec 會打包 classifier.exe）
go build -o classifier.exe .\cmd\scanner

# 2. 打包 GUI
python -m PyInstaller --clean --noconfirm "女優分類系統_修復版.spec"

# 3. 手動同步 classifier.exe（spec 不會自動放進 dist）
Copy-Item .\classifier.exe .\dist\classifier.exe -Force
```

> ⚠️ **重要**：`spec` 打包時會把 `classifier.exe` 包進 EXE 內（MEIPASS）。  
> 但 `dist\classifier.exe` 需要手動同步，因為這個是 **EXE 外的 Go CLI**（用於直接呼叫）。

---

## spec 設定說明（女優分類系統_修復版.spec）

```python
datas = [
    ('src', 'src'),              # Python 模組
    ('config.ini', '.'),         # 設定檔
    ('major_studios.json', '.'), # 大片商清單
    ('studios.json', '.'),       # 片商規則（db fix-studios 用）
]

binaries = [
    ('classifier.exe', '.'),     # Go CLI 打包進 EXE
]

hiddenimports = ['queue']

# ttkbootstrap 全量收集（含主題資源）
tmp_ret = collect_all('ttkbootstrap')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
```

**輸出名稱**：`女優分類系統_修復版.exe`

---

## exe 執行時的路徑問題

### 打包後 CWD

PyInstaller EXE 執行時，CWD 通常是 EXE 所在的 `dist\` 目錄。

**Go CLI 從 CWD 搜尋 `studios.json`**，因此需確保 `dist\studios.json` 存在：

```powershell
Copy-Item .\studios.json .\dist\studios.json -Force
```

### `_MEIPASS` 路徑

打包進 EXE 的檔案在執行時會解壓到 `sys._MEIPASS`。  
GoBridge 的 `_find_exe()` 會優先搜尋 `sys._MEIPASS / classifier.exe`。

### 資料庫路徑

EXE 執行時，若使用相對路徑 `data/json_db`，實際路徑會是 `dist\data\json_db\`。  
建議在 `config.ini` 中使用絕對路徑，或確保 `data/` 存在於 `dist\` 下。

---

## 兩版 spec 對比

| 項目 | `女優分類系統_修復版.spec` | `actress_classifier.spec` |
|------|---------------------------|--------------------------|
| 輸出名稱 | `女優分類系統_修復版.exe` | `actress_classifier.exe` |
| classifier.exe | ✅ 打包進去 | ✅ 打包進去 |
| ttkbootstrap | ✅ `collect_all` 全量 | ✅ 相同 |
| 主要使用 | ✅ 現行版本 | ⚠️ 舊版 |

---

## 常見問題

### 問題：EXE 執行時 Go CLI 不可用

**原因**：`classifier.exe` 未正確打包或路徑偵測失敗  
**排查**：
```python
from services.go_bridge import get_bridge
print(get_bridge().exe_path)
print(get_bridge().is_available)
```

### 問題：片商識別功能報錯（找不到 studios.json）

**原因**：`dist\studios.json` 不存在  
**解法**：`Copy-Item .\studios.json .\dist\studios.json`

### 問題：ttkbootstrap 主題不顯示

**原因**：spec 中 `collect_all('ttkbootstrap')` 漏掉  
**解法**：確認 spec 中有此行

---

## 相關頁面

- [wiki/pitfalls/pyinstaller-path.md](../pitfalls/pyinstaller-path.md)
- [wiki/architecture/go-bridge.md](go-bridge.md)
