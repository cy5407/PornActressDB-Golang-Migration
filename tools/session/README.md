# session_cleaner.py — Copilot CLI Session 清洗工具

## 用途

將 Copilot CLI 匯出的 session markdown 壓縮，移除雜訊，保留對 AI 有診斷價值的內容，以便在新 session 中傳入作為上下文參考。

## 保留 / 刪除規則

| Section 類型 | 行為 |
|-------------|------|
| `### 👤 User` | ✅ 完整保留 |
| `### 💬 Copilot` | ✅ 完整保留 |
| `### ✅ tool`（成功工具呼叫） | ⚡ 保留標題與參數，刪除 `<details>` 輸出 |
| `### ❌ tool`（失敗工具呼叫） | ✅ **完整保留**（含 stderr / stack trace） |
| `### 💭 Reasoning` | ❌ 完全刪除 |
| `### ℹ️ Info` | ❌ 完全刪除 |

> `❌` 失敗的工具呼叫會完整保留，因為它們包含診斷用的 stderr / stack trace，
> 是理解「為什麼撞牆」的關鍵資訊，且體積通常很小（< 2KB），幾乎不影響壓縮率。

## 壓縮效果

以典型 session（~5 MB）為例：

- 縮減率：約 **67–70%**
- 失敗工具呼叫的保留額外增加約 **< 1%** 體積

## 用法

```bash
# 基本用法（輸出 input.cleaned.md）
python tools/session/session_cleaner.py session.md

# 指定輸出路徑
python tools/session/session_cleaner.py session.md -o output.md
```

輸出會顯示：

```
✅ 完成：session.md
   原始：5364.5 KB  →  清洗後：1676.6 KB  (縮減 68.7%)
   輸出：session.cleaned.md
```

## 使用情境

1. 長時間工作的 session 快要超出 context window 時，匯出並清洗後重新傳入
2. 把舊 session 的脈絡帶進新 session 時，減少 token 用量
3. 分享 session 記錄給人工審閱時，過濾掉 AI 內部推理過程
