# Issue 14：go_api 匯出遺漏 → AttributeError

**日期**：2026-04-06
**症狀**：`module 'services.go_api' has no attribute 'db_fix_studios'`
**根因**：新增函式到 `go_api/db.py` 後，未在 `__init__.py` 和 `go_bridge.py` 補上匯出

## 正確做法

見 [patterns/add-go-api-function.md](../patterns/add-go-api-function.md)
