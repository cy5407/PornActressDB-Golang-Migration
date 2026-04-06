# Issue 13：GUI Bridge 取法錯誤 → Go CLI 不可用警告

**日期**：2026-04-06  
**嚴重度**：🟡 中（功能不可用，但程式不崩潰）

---

## 症狀

點擊 GUI 按鈕後立即跳出警告：

```text
警告：Go CLI 不可用，無法執行此操作
```

但 `classifier.exe` 確實存在於專案根目錄，手動執行也正常。

---

## 根本原因

在 GUI 事件處理器中使用了不存在的屬性：

```python
# ❌ 錯誤寫法（常見誤解）
bridge = self.core.go_bridge   # AttributeError 或 None
if not bridge:                 # 永遠為 True → 進入「不可用」分支
    messagebox.showwarning(...)
```

`UnifiedClassifierCore` **沒有** `go_bridge` 屬性。`self.core` 是業務邏輯核心，不暴露底層 CLI bridge。

---

## 正確做法

`GoBridge` 是**模組層級單例**，應透過 `get_bridge()` 取得：

```python
# ✅ 正確寫法
from services.go_bridge import get_bridge

def _on_button_click(self):
    bridge = get_bridge()
    if not bridge.is_available:
        messagebox.showwarning("警告", "Go CLI 不可用")
        return
    # 正常呼叫 bridge.xxx()
```

---

## 對比表

| 取法 | 結果 | 說明 |
|------|------|------|
| `self.core.go_bridge` | `AttributeError` 或 `None` | ❌ 屬性不存在 |
| `self.go_bridge` | `AttributeError` | ❌ GUI class 也沒有此屬性 |
| `get_bridge()` | 正確的 `GoBridge` 單例 | ✅ 唯一正確取法 |

---

## 診斷方法

懷疑 bridge 取法有問題時，在 Python REPL 確認：

```python
from services.go_bridge import get_bridge
bridge = get_bridge()
print(bridge.is_available)     # 應為 True
print(bridge.exe_path)         # 應顯示 classifier.exe 的完整路徑
```

若 `is_available = False`，確認 `classifier.exe` 是否存在於專案根目錄：

```powershell
dir classifier.exe
```

---

## 預防

GUI 事件處理器中，永遠使用：

```python
from services.go_bridge import get_bridge
```

不要嘗試從 `self.core`、`self.classifier`、`self.db` 等業務物件取 bridge。

→ 詳見 [patterns/add-gui-button.md](../patterns/add-gui-button.md)
