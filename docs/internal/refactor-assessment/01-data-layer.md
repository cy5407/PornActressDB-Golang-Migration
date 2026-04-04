# 區塊 1：資料層評估

## 本次檢閱範圍

已檢閱：

- `src/models/json_database.py`
- `src/models/incremental_json_database.py`
- `src/models/go_accelerated_db.py`
- `src/models/studio.py`
- `src/models/json_types.py`
- `pkg/database/jsondb.go`
- `pkg/database/journal.go`
- `pkg/database/types.go`
- `pkg/studio/identifier.go`
- `studios.json`
- `major_studios.json`

## 這個區塊在做什麼

- JSON 資料庫讀寫
- journal 增量寫入與 compact
- schema 正規化與相容性處理
- 片商識別與片商名稱標準化
- Python / Go fallback 包裝

## 現況判斷

這個區塊已經不是「適不適合 Go」的問題，而是**其實已經在做 Go 版，只是 Python 還保留了大量相容層與雙軌實作**。

特徵非常明顯：

- Python 有 `JSONDBManager`、`IncrementalJSONDB`
- Go 有 `pkg/database/jsondb.go`
- Python 又加了一層 `GoAcceleratedDB` 做 fallback
- 片商識別同時存在 Python 與 Go 版本

這代表資料層已具備 Go 遷移條件，而且有現成基礎。

## 是否適合重構成 Golang

**判定：非常適合**

理由：

1. 資料層是純本機 I/O、schema 驗證、map 操作、journal 管理，和 Go 的能力非常對齊。
2. 專案內已經有 Go 資料庫實作，不是從零開始。
3. Python 目前保留的很多程式碼，實際上是在補 Go fallback 與舊介面相容，屬於可收斂的重複邏輯。
4. 這個區塊和 GUI 耦合低，適合先抽。

## 是否適合重構成 Rust

**判定：技術上適合，但專案上不划算**

理由：

1. Rust 很適合做安全的本機資料層與原子寫入。
2. 但目前已經有 Go 版本在運作，若改成 Rust，等於要重新建立一套 CLI / bridge / 測試鏈。
3. 這會讓專案從「Python + Go」變成「Python + Go + Rust」，語言面反而更碎。

## 建議結論

這一區塊應該明確選 **Go**，不要再開 Rust 支線。

## 建議遷移邊界

優先搬或收斂到 Go 的內容：

- `data.json` / `data.journal` / `data.index` 的完整生命週期
- schema 正規化
- dirty tracking
- compact 判斷與執行
- 片商規則載入
- 片商名稱標準化
- 資料庫查詢與更新 API

Python 端建議只保留：

- 極薄的 adapter
- 例外轉換
- GUI 需要的資料格式轉接

## 遷移風險

- Python 與 Go 對舊 schema 的相容邏輯必須完全對齊
- `GoAcceleratedDB` 每次成功寫入後重建 Python DB state，代表目前仍有雙快取語義，要先定義單一真相來源
- `studio.py` 與 `pkg/studio/identifier.go` 的規則與 alias 可能已經有細節差異，收斂前要比對

## 建議優先度

**優先度：P1**

這是最值得先減掉 Python 的區塊之一。

