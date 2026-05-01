# SQLite shadow DB 指令速查

> 更新：2026-04-27

這份文件整理目前 `codex/rust-adn-db-branch` 上新增的 SQLite shadow DB、查詢腳本與女優欄位清洗工具。

## 分支與遠端狀態

目前相關更動都在：

```text
codex/rust-adn-db-branch
```

已推到遠端：

```powershell
git fetch origin
git switch codex/rust-adn-db-branch
git pull --ff-only
```

若你在 worktree 測試，路徑是：

```powershell
cd "C:\Users\cy5407\.codex\worktrees\72b7\PornActressDB-Golang-Migration"
```

## 需要先建置的工具

Go CLI：

```powershell
go build -o classifier.exe .\cmd\scanner
```

Rust SQLite 工具：

```powershell
cargo build --release --manifest-path tools-rs\Cargo.toml
```

`scripts\db-query.ps1` 使用 Bun 讀 SQLite。若 `bun` 還沒有進 PATH，可先重開 terminal；安裝位置通常是：

```text
C:\Users\cy5407\.bun\bin\bun.exe
```

## 同步 shadow SQLite

> **重要**：升級到 v2 schema 後，舊的 `data\shadow.sqlite` 必須刪除或用 `--replace` rebuild。工具會在偵測到 v1 DB 時直接 error，不做 in-place migration。

從 `data\json_db\data.json` 重建 `data\shadow.sqlite`：

```powershell
scripts\db-sync.ps1
```

會依序執行：

1. `classifier.exe db compact`
2. `db-tool db-init`
3. `db-tool db-import-json`
4. `db-tool db-compare-json`

加 benchmark：

```powershell
scripts\db-sync.ps1 -Benchmark
```

跳過 compact：

```powershell
scripts\db-sync.ps1 -SkipCompact
```

## 查詢 SQLite

列出表與 view：

```powershell
scripts\db-query.ps1 tables
```

看統計：

```powershell
scripts\db-query.ps1 stats
```

查番號：

```powershell
scripts\db-query.ps1 code -Text ABF-056
```

查女優：

```powershell
scripts\db-query.ps1 actress -Text "瀧本雫葉" -Limit 20
```

查片商：

```powershell
scripts\db-query.ps1 studio -Text PRESTIGE -Limit 20
```

模糊搜尋：

```powershell
scripts\db-query.ps1 search -Text ABF -Limit 20
```

執行只讀 SQL：

```powershell
scripts\db-query.ps1 sql -Sql "SELECT code, studio, actresses FROM videos_with_actresses WHERE actresses != '' LIMIT 10"
```

`sql` 模式只允許 `SELECT` / `WITH` / `PRAGMA`。

## 找可疑女優欄位

列出所有長度超過 10 字的 distinct 女優欄位：

```powershell
scripts\db-query.ps1 long-actresses -MinLength 10 -All
```

只看前 20 筆並顯示總數：

```powershell
scripts\db-query.ps1 long-actresses -MinLength 10 -Limit 20
```

只看含 `#` 的共演串：

```powershell
scripts\db-query.ps1 hash-actresses -All
```

這類通常代表多個共演女優被塞在同一欄，例如：

```text
五十嵐美月 #内田すみれ #千石もなか
```

後續適合做「拆分」，不是刪除。

只看不含 `#`、但超過 10 字的疑似標題污染：

```powershell
scripts\db-query.ps1 long-title-fragments -MinLength 10 -All
```

輸出會多一欄 `known_name_hits`，用來提示污染字串中是否包含既有短女優名。

## 清洗女優欄位

先 dry-run，不寫入：

```powershell
.\classifier.exe db clean-actresses -data-dir "C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\data\json_db"
```

確認報告後正式寫入：

```powershell
.\classifier.exe db clean-actresses -data-dir "C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\data\json_db" -write
```

`-write` 會先建立備份，再修改資料。寫入後建議重建 shadow SQLite：

```powershell
scripts\db-sync.ps1
```

再確認長標題污染是否歸零：

```powershell
scripts\db-query.ps1 long-title-fragments -MinLength 10 -All
```

## 目前已處理的污染類型

目前 `clean-actresses` 已能處理：

- 明確標題片段誤入女優欄位
- `瀧本雫葉汁` 這類「正確女優名 + 標題字尾」
- `石川澪とラブラブでハメまくる` 這類可替換為既有女優名的片段
- 全形 / 半形星號垃圾值
- 重複女優名

目前尚未自動處理：

- `#` 串接的共演女優名單拆分

這類要另外實作拆分規則，避免誤刪共演名單。
