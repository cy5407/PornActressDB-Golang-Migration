# 使用 session_cleaner 壓縮 Copilot CLI Session

## 背景

Copilot CLI 的 `/share` 指令可以匯出目前 session 的完整記錄（markdown 格式）。
當 session 過長或要把歷史脈絡帶入新 session 時，原始匯出檔案通常有數 MB，
大量夾帶 AI 推理過程和成功工具的完整輸出，不適合直接傳入。

`tools/session/session_cleaner.py` 是專為此設計的壓縮工具，典型壓縮率 **67–70%**。

---

## 用法

```powershell
# 基本（輸出 input.cleaned.md）
python tools\session\session_cleaner.py copilot-session-XXXX.md

# 指定輸出
python tools\session\session_cleaner.py copilot-session-XXXX.md -o context.md
```

---

## 保留策略

| Section | 行為 | 原因 |
|---------|------|------|
| `### 👤 User` | ✅ 完整保留 | 使用者需求 |
| `### 💬 Copilot` | ✅ 完整保留 | AI 決策與結論 |
| `### ✅ tool`（成功） | ⚡ 保留標題+參數，刪 `<details>` | 工具輸出通常很長且不必要 |
| `### ❌ tool`（失敗） | ✅ **完整保留** | 含 stderr/stack trace，是診斷撞牆的關鍵 |
| `### 💭 Reasoning` | ❌ 完全刪除 | AI 內部推理，context 用途不大 |
| `### ℹ️ Info` | ❌ 完全刪除 | 環境樣板資訊 |

> **為什麼保留 `❌` 失敗呼叫？**  
> 失敗訊息體積通常 < 2KB，對壓縮率影響微乎其微（< 1%），
> 但對下一個 session 的 AI 理解「上次為什麼失敗」至關重要。

---

## 工作流程

```
1. 結束工作前執行 /share
2. python tools\session\session_cleaner.py copilot-session-XXXX.md
3. 新 session 開始時，把 .cleaned.md 拖入對話視窗作為上下文
```

---

## 限制

- 僅適用於 **Copilot CLI** `/share` 的輸出格式
- 其他 AI CLI 工具的 session 格式不同，不適用
- 工具在 `tools/session/` 目錄，詳細說明見 `tools/session/README.md`
