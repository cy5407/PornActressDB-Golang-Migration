# 區塊 6：測試與工具腳本評估

## 本次檢閱範圍

已檢閱：

- `tests/test_go_accelerated_db.py`
- `tests/test_scanner_integration.py`
- `tests/test_incremental_db.py`
- `tests/test_studio_integration.py`
- `test_go_db_bridge.py`
- `tools/integration/benchmark.py`
- `tools/integration/go_integration.py`
- `tools/diagnostics/normalize_json_db_schema.py`
- `tools/verify/verify_json_db_schema.py`

## 這個區塊在做什麼

- Python 端整合測試
- Go bridge 驗證
- schema 驗證與清理工具
- benchmark 與診斷腳本

## 現況判斷

這一區塊不是主要產品邏輯，但它會直接影響遷移速度。

目前很多測試的價值在於：

- 驗證 Python / Go fallback 是否一致
- 驗證資料庫 schema 與 bridge 行為
- 驗證 CLI 與 Python 呼叫端整合

因此它們不應該被獨立看待，而應跟著主模組一起遷移。

## 是否適合重構成 Golang

**判定：部分適合**

適合搬到 Go 的：

- 資料層測試
- CLI 整合測試
- extractor / mover / database 的 golden tests
- benchmark

暫時保留 Python 的：

- GUI 整合測試
- bridge 相容性測試
- 針對既有 Python shell 的 smoke tests

## 是否適合重構成 Rust

**判定：不建議**

除非主模組真的開始用 Rust，否則測試與工具沒有單獨導入 Rust 的價值。

## 建議結論

測試與工具不應該自己先搬，而應該跟著主路線走：

1. 核心搬到 Go
2. 對應測試一起搬到 Go
3. Python 端只保留 GUI 與相容層測試

## 建議遷移策略

- DB 相關測試改成 Go 為主，Python 留相容性測試
- CLI 測試直接用 Go 測試與 fixture
- schema 工具若未來由 Go DB 全權管理，可逐步把 verify / normalize 工具搬到 Go

## 建議優先度

**優先度：P2**

它不是第一批要降低 Python 比例的區塊，但必須跟著主模組同步調整，否則遷移風險會變高。

