---
status: resolved
---

# Schema 共用：Go //go:embed vs Rust include_str! 的方向不對稱

> 觸發：C3 計畫原本要把 SQLite v3 schema 搬到 `schemas/sqlite/v3.sql`（repo root），讓 Go 與 Rust 雙方共用。
> 落地：2026-05-23（C3）

---

## 一句話

`//go:embed` 不接受 package 目錄外的相對路徑；`include_str!` 接受。所以把共用檔放在 Go package 內、讓 Rust 反過來 include，是唯一不引入 build pipeline 複雜度的選項。

---

## 症狀

Plan 原本寫：

```text
schemas/sqlite/v3.sql       ← 新位置
pkg/database/sqlite_store.go     //go:embed ../../schemas/sqlite/v3.sql
tools-rs/src/v3_schema.rs        include_str!("../../schemas/sqlite/v3.sql")
```

實作時 Go 端會編譯失敗：

```
//go:embed: pattern ../../schemas/sqlite/v3.sql: invalid pattern syntax
```

或：

```
//go:embed: cannot embed file outside package directory
```

Go 規範明確：`//go:embed` 只能 embed package 同層或子目錄；任何 `..` 都會被 toolchain 拒絕。

---

## 為什麼會踩

- Rust `include_str!` 在 macro 展開時把字面路徑相對於 `file!()`（也就是該 `.rs` 檔位置）解析；可以任意往上跳目錄，rustc 也會把這份 dependency 寫進 dep-info，cargo 因此會在外部檔變更時 rebuild。
- Go 的 `embed` 在 toolchain 層級限制 path 必須位於 package 目錄內，原因之一是 module / vendor 邏輯不希望 embed 跨越模組界線。
- 因此「把 canonical schema 搬到 repo root，雙方都向上 embed」的對稱方案，只有 Rust 可行。

---

## 解法（本 repo 採用）

把 canonical schema 留在 Go package 內，讓 Rust 反方向 include：

```text
pkg/database/sqlite_schema.sql                   ← canonical
pkg/database/sqlite_store.go                     //go:embed sqlite_schema.sql
tools-rs/src/v3_schema.rs                        include_str!("../../pkg/database/sqlite_schema.sql")
```

漂移防護（三層 + 一層 CI）：

1. `pkg/database/sqlite_store_test.go::TestSQLiteSchemaSQL_MatchesCanonicalFile`
2. `tools-rs/src/v3_schema.rs::tests::embedded_schema_matches_canonical_file_on_disk`
3. `tools-rs/tests/integration_db_tool.rs::embedded_v3_schema_matches_canonical_go_package_file`
4. `db-verify` 整合測試：拿 Rust embed 跑 schema → 對結果 SQLite 跑 verify，要綠

三個檔層級的測試任何一個失敗，就代表有人偷偷編了第二份 schema。

---

## 不做的替代方案

| 方案 | 為什麼不採 |
|------|-----------|
| `go:generate` 在 build 前複製 `schemas/...` 進 `pkg/database/` | 引入 codegen pipeline + checked-in generated file，pre-commit 容易漂移 |
| `tools-rs/build.rs` 反向複製到 `tools-rs/src/` | 多一份檔案、多一個 pipeline 步驟，與 (上) 對稱地差 |
| Symlink | Windows 跨 dev 環境設定不一致；git 對 symlink 支援不穩定 |
| 兩端各維護一份 schema + lint 比對 | 漂移成本最高；違反「single source of truth」原則 |

---

## 驗證 fix 是否在你的 build

```powershell
# 1. Go 端內嵌與檔案一致
go test .\pkg\database -run TestSQLiteSchemaSQL_MatchesCanonicalFile -v

# 2. Rust 單元 + 整合層級各驗一次
cargo test --manifest-path tools-rs\Cargo.toml --lib embedded_schema_matches_canonical_file_on_disk
cargo test --manifest-path tools-rs\Cargo.toml --test integration_db_tool embedded_v3_schema_matches_canonical_go_package_file
```

三條都綠 = 兩端拿到的是同一份 byte。

---

## 相關頁面

- [架構頁：資料庫架構](../architecture/database.md) §「Schema 共用 (Go + Rust)」
- [架構頁：SQLite 影子資料庫（歷史）](../architecture/sqlite-shadow-db.md)
