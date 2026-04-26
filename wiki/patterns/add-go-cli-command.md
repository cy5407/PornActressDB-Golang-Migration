# 新增 Go CLI 子命令

> 更新：2026-04-27
> 現行 Python 委派層是 `src/services/go_cli.py::run()`，它不會自動附加 `-json`。新增子命令的重點是「stdout 穩定輸出 JSON」與「呼叫端契約測試」，不是一律宣告 no-op `-json`。

---

## 標準範本

```go
// cmd/scanner/db_cmd.go（或對應 cmd 檔）

func myNewCmd(args []string) {
    fs := flag.NewFlagSet("db my-new", flag.ExitOnError)
    dataDir := fs.String("data-dir", "data/json_db", "資料庫目錄")
    _ = fs.Bool("json", false, "輸出 JSON 格式（相容性，no-op）")  // 若既有呼叫端會傳 -json 才需要
    parseFlagsOrExit(fs, args)

    // ... 邏輯 ...

    outputJSON(result)  // 輸出統一用 outputJSON
}
```

---

## JSON 輸出契約

所有正式子命令都應讓 stdout 輸出可解析的 JSON，方便 Python / Wails / 測試穩定串接。

現行 `src/services/go_cli.py::run()` 行為：

- 直接執行 `classifier(.exe)`。
- 讀取 stdout。
- 用 `json.loads(stdout)` 解析回 dict / list。
- 不會自動附加 `-json`。

因此新增子命令時，優先確認：

- 成功時 stdout 是 JSON。
- 失敗時 exit code 非 0，錯誤寫到 stderr。
- Python helper 若新增，應在 `tests/test_go_cli_contracts.py` 或對應測試中固定參數順序與回傳語意。

`-json` no-op flag 現在不是新命令的必要條件；只有在你需要相容舊呼叫端、舊測試或既有命令已公開支援 `-json` 時才保留。

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

- [Go CLI 未定義 -json](../pitfalls/go-cli-json-flag-missing.md)（Issue 15，舊 `go_api/go_runner` 架構問題）
