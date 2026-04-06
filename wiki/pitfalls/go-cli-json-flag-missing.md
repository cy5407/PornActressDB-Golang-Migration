# Issue 15：Go CLI 未定義 -json flag → ExitOnError 靜默退出

**日期**：2026-04-06
**症狀**：`❌ 修正失敗: flag provided but not defined: -json`
**根因**：Python 端固定傳 `--json`，Go 的 `flag.ExitOnError` 遇未知 flag 直接退出

## 正確做法

新增任何 Go CLI 子命令時，一律宣告 no-op -json flag：

```go
_ = fs.Bool("json", false, "輸出 JSON 格式（相容性，no-op）")
```

見 [patterns/add-go-cli-command.md](../patterns/add-go-cli-command.md)
