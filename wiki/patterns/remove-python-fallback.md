# Python Fallback 移除策略（Phase 6）

> 來源：Phase 6A–6D 執行記錄（2026-04-06）  
> 適用：已完成 Go 委派後，要清理剩餘 Python fallback 的情境

---

## 概述

完成 Go 委派（Phase 1–5）後，每個公開方法同時存在兩條路徑：

```
if go_available:
    go_cli_call()
else:
    python_fallback()    ← 要刪除的目標
```

Phase 6 的目標是刪除所有 `_*_python()` 方法，讓程式碼只剩 Go 委派路徑。

---

## 核心決策：寫入 vs. 讀取 fallback 不同處理

| 操作類型 | Go 不可用時的正確行為 | 原因 |
|---------|--------------------|----|
| **寫入**（update/add/delete） | `raise RuntimeError` | 寫入必須有持久化保證，不能靜默失敗 |
| **讀取**（get/list） | 從記憶體 cache 返回 | 記憶體已有資料，降級讀取仍有意義 |

```python
# 寫入：Go 不可用 → RuntimeError（不接受降級）
def update_video(self, code, updates):
    if self._GO_DB_AVAILABLE:
        ...go call...
    raise RuntimeError(f"Go CLI 不可用，無法更新影片: {code}")

# 讀取：Go 不可用 → 從記憶體返回
def get_video_info(self, code):
    if self._GO_DB_AVAILABLE:
        ...go call...
    return self.data.get("videos", {}).get(code)   # memory fallback OK
```

---

## 刪除流程

### Step 1 — 確認依賴

刪除方法前必須確認「有沒有其他地方呼叫這個私有方法」：

```bash
# 搜尋所有直接引用
grep -r "_add_or_update_video_python\|_get_video_info_python" src/ tests/
```

> ⚠️ 踩坑：`code_to_studio` 雖然是 `_identify_studio_python()` 的內部資料，  
> 但 `normalize_studio_name()` 直接使用 `self.code_to_studio[...]`，  
> **不能一起刪除**。只刪邏輯方法，保留資料屬性。

### Step 2 — 修改公開方法

把公開方法的最後一行從「呼叫 Python fallback」改成「RuntimeError 或 memory 讀取」：

```python
# 改前
return self._add_or_update_video_python(code, info)

# 改後（寫入操作）
raise RuntimeError(f"Go CLI 不可用，無法新增/更新影片: {code}")

# 改後（讀取操作）
return self.data.get("videos", {}).get(code)
```

### Step 3 — 刪除方法體

整個刪除 `def _*_python(...)` 方法定義（含 docstring）。

### Step 4 — 更新測試

| 測試種類 | 修改方式 |
|---------|---------|
| `test_falls_back_to_python_when_go_unavailable`（寫入） | 改預期 `pytest.raises(RuntimeError)` |
| `test_falls_back_to_python_when_go_unavailable`（讀取） | 保留，行為不變（從記憶體返回） |
| `test_falls_back_on_go_exception`（寫入） | 改預期 `pytest.raises(RuntimeError)` |
| `test_python_fallback_method_exists` | **整個刪除**（方法已不存在） |

### Step 5 — 跑測試確認

```bash
python -m pytest tests/ --tb=short -q
```

---

## 整刪整個類別（Phase 6C 模式）

若某個類別只是包裝層（如 `GoAcceleratedDB`），且沒有業務程式碼直接引用，可整個刪除：

1. 確認引用：`grep -r "GoAcceleratedDB\|GoAcceleratedStudioIdentifier" src/ tests/`
2. 若只有測試在用 → 連測試一起刪
3. 刪除原始檔案
4. 跑測試確認

---

## 重要觀察：`_get_video_info_python` ≠ IO Fallback

`IncrementalJSONDB._get_video_info_python()` 的內容：

```python
def _get_video_info_python(self, code):
    return self.base_db.get_video_info(code)  # 只是記憶體查詢！
```

這不是真正的 IO fallback，而是記憶體讀取。Phase 6D-1 直接 inline：

```python
# 改前（呼叫多餘包裝）
return self._get_video_info_python(code)

# 改後（直接讀記憶體）
return self.base_db.get_video_info(code)
```

相比之下，`_update_video_python()` 才是真正的 IO fallback（寫 journal 檔案），應 raise RuntimeError 取代。

---

## Phase 6 刪減統計

| Phase | 目標 | 刪除行數 |
|-------|------|---------|
| 6A-1 | `extractor.py` Python 方法 | ~180 行 |
| 6A-2 | `studio.py` `_identify_studio_python` | ~30 行 |
| 6A-3 | `scanner.py` rglob fallback | ~20 行 |
| 6A-4 | `file_mover.py` shutil fallback | ~15 行 |
| 6B-1 | `cache_manager.py` 3 個 Python 方法 | ~175 行 |
| 6C-1/2 | `GoAcceleratedDB` + `GoAcceleratedStudioIdentifier` 整刪 | ~600 行 |
| 6D-1 | `incremental_json_database.py` 2 個 Python 方法 | ~35 行 |
| 6D-2 | `json_database.py` 4 個 Python 方法 | ~280 行 |
| **合計** | | **~1,335 行（純刪除）** |

**整體 git diff**：+526 / -1966（淨刪除 **-1,440 行**）

> 新增的 +526 主要是 `studios.json` 重組（+230）和工具腳本（+168），非核心程式碼。

---

## 測試速度提升

| 狀態 | 執行時間 |
|------|---------|
| Phase 5 完成後（含整合測試） | ~167 秒 |
| Phase 6C 刪除整合測試後 | ~1.9 秒 |
| **提升倍數** | **~88x** |

整合測試（啟動真實 Go CLI）是測試慢的根因。移除包裝類別時也一起移除這類測試。

---

## 相關頁面

- [go-bridge.md](../architecture/go-bridge.md) — 委派架構整體設計
- [add-go-api-function.md](add-go-api-function.md) — 新增 Go API 函式標準流程
