# 新增 GUI 按鈕

---

## 完整範本

### 1. row3_frame 加按鈕

```python
# src/ui/main_gui.py

# 若 row3 原本是 2 欄，改為 3 欄
row3_frame.columnconfigure((0, 1, 2), weight=1)

self.my_btn = ttk.Button(
    row3_frame, text="🔧 功能名稱", command=self.start_my_feature
)
self.my_btn.grid(row=0, column=2, padx=(2, 0), sticky="ew", ipady=5)
```

### 2. `_toggle_buttons` 加入新按鈕

```python
def _toggle_buttons(self, is_task_running: bool):
    buttons = [
        ...
        self.my_btn,   # ← 加入
    ]
```

### 3. 觸發方法（確認 bridge 可用，再啟動背景執行緒）

```python
def start_my_feature(self):
    from services.go_bridge import get_bridge   # ← 正確取法
    bridge = get_bridge()
    if not bridge.is_available:
        messagebox.showwarning("警告", "Go CLI 不可用")
        return

    self.clear_results()
    self.update_progress("🔧 功能名稱\n" + "=" * 60 + "\n")

    threading.Thread(
        target=self._run_task,
        args=(self._my_feature_worker,),
        daemon=True,
    ).start()
```

### 4. Worker 方法（背景執行緒）

```python
def _my_feature_worker(self):
    from services.go_bridge import get_bridge
    self.status_var.set("執行中：功能名稱...")
    try:
        bridge = get_bridge()

        # 取得資料庫路徑（正確方式）
        data_dir = str(getattr(self.core.db_manager, "data_dir", "data/json_db"))

        result = bridge.some_api(data_dir=data_dir)

        if not self.is_running:
            return

        # 更新結果...
        self.status_var.set("完成")

    except Exception as e:
        if self.is_running:
            self.update_progress(f"\n💥 未預期錯誤: {e}\n")
            self.status_var.set(f"錯誤: {e}")
```

---

## ❌ 常見錯誤

| 錯誤寫法 | 正確寫法 |
|---------|---------|
| `self.core.go_bridge` | `get_bridge()` from go_bridge |
| `getattr(self.core, "db_path", ...)` | `self.core.db_manager.data_dir` |
| 直接在主執行緒呼叫耗時操作 | 用 `threading.Thread` + `_run_task` |
| `root.update()` 在 worker 中更新 UI | `self.update_progress(msg)` （已有 throttle 機制） |

---

## GUI 執行緒規則

- **主執行緒**：只做 UI 操作（按鈕、標籤、對話框）
- **背景執行緒**：所有 I/O、Go CLI 呼叫、爬蟲
- `update_progress()` 內部已透過 `root.after()` 安全回主執行緒

---

## 相關踩坑

- [GUI Bridge 取法錯誤](../pitfalls/gui-bridge-wrong-access.md)（Issue 13）
