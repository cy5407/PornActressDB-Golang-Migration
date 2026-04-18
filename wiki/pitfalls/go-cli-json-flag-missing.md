---
category: Go
date: 2026-04-06
---
# Issue 15：Go CLI 未定義 -json flag → ExitOnError 靜默退出

**日期**：2026-04-06  
**嚴重度**：🔴 高（Go CLI 呼叫靜默失敗，Python 端收到空結果）

---

## 症狀

```text
❌ 修正失敗: flag provided but not defined: -json
```

或 Python 端收到空輸出、空 dict，但 Go CLI 不報任何 error——功能靜默失敗。

---

## 根本原因

### Python 端固定傳 `--json`

`GoCommandRunner.run_json()` 在所有 Go CLI 呼叫後面自動附加 `-json`：

```python
# go_runner.py
def run_json(self, args: list[str]) -> dict:
    full_args = args + ["-json"]   # ← 固定附加
    result = subprocess.run([self.exe_path] + full_args, ...)
    return json.loads(result.stdout)
```

### Go 的 `flag.ExitOnError` 遇未知 flag 直接退出

```go
// 新增子命令時的常見寫法（有問題）
fs := flag.NewFlagSet("fix-studios", flag.ExitOnError)
// 只宣告自己需要的 flag
dataDir := fs.String("data-dir", "", "資料目錄")
// 遺漏了 -json！
fs.Parse(args)  // 遇到 -json → 未定義 → os.Exit(2)
```

`flag.ExitOnError` 的行為：遇到未定義的 flag 時，**直接呼叫 `os.Exit(2)`**，不輸出任何 JSON，也不輸出 stderr 錯誤訊息（取決於實作）。Python 端只看到空 stdout，`json.loads("")` 拋出 JSONDecodeError 或返回空 dict。

---

## 修正

新增任何 Go CLI 子命令時，一律宣告 **no-op `-json` flag**：

```go
// ✅ 正確做法
fs := flag.NewFlagSet("fix-studios", flag.ExitOnError)
dataDir := fs.String("data-dir", "", "資料目錄")
_ = fs.Bool("json", false, "輸出 JSON 格式（相容性，no-op）")  // ← 必加
fs.Parse(args)
```

這個 flag 宣告後不需要使用（`_` 忽略），只是讓 `flag` 套件知道 `-json` 是合法參數。

---

## 對比：修正前後

| 狀況 | 修正前 | 修正後 |
|------|--------|--------|
| Python 傳入 `-json` | `os.Exit(2)`，靜默退出 | 正常解析，忽略 -json |
| Python 端回傳值 | `{}` 或 JSONDecodeError | 正確 JSON 結果 |
| 除錯難度 | 很難（無錯誤訊息） | 立即發現 |

---

## 預防

每個新 Go 子命令的 flag 宣告模板：

```go
fs := flag.NewFlagSet("子命令名", flag.ExitOnError)
// ... 宣告業務 flag
_ = fs.Bool("json", false, "輸出 JSON 格式（相容性，no-op）")  // 必加
fs.Parse(args)
```

→ 詳見 [patterns/add-go-cli-command.md](../patterns/add-go-cli-command.md)
