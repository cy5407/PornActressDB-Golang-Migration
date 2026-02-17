---
name: gui-development
description: GUI 開發指引 - 用於新增 Tkinter 按鈕、背景執行緒處理、進度條更新、對話框設計和執行緒安全
argument-hint: "[component-name]"
---

# GUI 開發 Skill

## 何時使用此 Skill

當需要：
1. **新增 GUI 元件**（按鈕、對話框、進度條）
2. **處理背景執行緒**（避免 UI 凍結）
3. **更新進度顯示**（執行緒安全）
4. **修復 GUI 問題**（響應速度、錯誤處理）

## 核心原則

### ⚠️ 執行緒安全規則

1. **長時間操作必須在背景執行緒**
2. **GUI 更新必須回主執行緒** (`root.after()`)
3. **共用資料使用 threading.Lock**

## GUI 元件範例

### 新增按鈕

```python
def create_my_button(self):
    """建立新按鈕"""
    btn = ttk.Button(
        self.button_frame,
        text="🚀 執行操作",
        command=self.on_button_click,
        style='primary.TButton'
    )
    btn.pack(side='left', padx=5)

def on_button_click(self):
    """按鈕點擊處理"""
    # 啟動背景執行緒
    thread = threading.Thread(
        target=self._worker_function,
        daemon=True
    )
    thread.start()
```

### 背景執行緒模式

```python
def _worker_function(self):
    """背景執行緒（長時間操作）"""
    try:
        # 執行耗時操作
        result = do_long_task()
        
        # 回到主執行緒更新 UI
        self.root.after(0, lambda: self.show_result(result))
        
    except Exception as e:
        # 錯誤處理（也要回主執行緒）
        self.root.after(0, lambda: self.show_error(str(e)))
```

### 進度更新

```python
def update_progress(self, message: str):
    """更新進度（執行緒安全）"""
    # 確保在主執行緒執行
    self.root.after(0, lambda: self._update_progress_ui(message))

def _update_progress_ui(self, message: str):
    """實際更新 UI（主執行緒）"""
    self.progress_label.config(text=message)
    self.progress_bar.step()
```

## 常見錯誤與解決

### 錯誤 1: UI 凍結

```python
# ❌ 錯誤：在主執行緒執行耗時操作
def on_click(self):
    result = long_task()  # UI 凍結！
    self.show_result(result)

# ✅ 正確：使用背景執行緒
def on_click(self):
    threading.Thread(target=self._worker, daemon=True).start()

def _worker(self):
    result = long_task()
    self.root.after(0, lambda: self.show_result(result))
```

### 錯誤 2: 跨執行緒 UI 更新

```python
# ❌ 錯誤：直接在背景執行緒更新 UI
def _worker(self):
    self.label.config(text="完成")  # 可能崩潰！

# ✅ 正確：使用 root.after()
def _worker(self):
    self.root.after(0, lambda: self.label.config(text="完成"))
```

## 相關檔案

- `src/ui/main_gui.py` - 主介面
- `src/ui/preferences_dialog.py` - 偏好設定對話框
- `src/ui/search_result_dialog.py` - 搜尋結果對話框
