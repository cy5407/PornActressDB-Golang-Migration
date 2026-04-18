# 新增 Go CLI 子命令

---

## 標準範本

```go
// cmd/scanner/db_cmd.go（或對應 cmd 檔）

func myNewCmd(args []string) {
    fs := flag.NewFlagSet("db my-new", flag.ExitOnError)
    dataDir := fs.String("data-dir", "data/json_db", "資料庫目錄")
    _ = fs.Bool("json", false, "輸出 JSON 格式（相容性，no-op）")  // ← 必須宣告
    parseFlagsOrExit(fs, args)

    // ... 邏輯 ...

    outputJSON(result)  // 輸出統一用 outputJSON
}
```

---

## ⚠️ 必須宣告 `-json` flag

Python `go_api/` 的慣例是**固定在命令末尾加 `--json`**：

```python
cmd = ["db", "my-new", "--data-dir", data_dir, "--json"]
```

Go 的 `flag.ExitOnError` 遇到未定義的 flag 會直接退出，不輸出任何 JSON，Python 端看到空輸出會報錯。

**即使子命令輸出本來就是 JSON（使用 outputJSON）**，也要宣告：

```go
_ = fs.Bool("json", false, "輸出 JSON 格式（相容性，no-op）")
```

---

## 路由：在父命令加入 case

```go
// cmd/scanner/db_cmd.go 的 switch subCmd
case "my-new":
    myNewCmd(args[1:])
```

或是獨立函式提前攔截（參考 `fix-studios` 的寫法）：

```go
if subCmd == "my-new" {
    myNewCmd(args[1:])
    return
}
```

---

## outputJSON 函式

定義在 `cmd/scanner/main.go`，不需 import：

```go
func outputJSON(v any) {
    b, _ := json.MarshalIndent(v, "", "  ")
    fmt.Println(string(b))
}
```

---

## 相關踩坑

- [Go CLI 未定義 -json](../pitfalls/go-cli-json-flag-missing.md)（Issue 15）
