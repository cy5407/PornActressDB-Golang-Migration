# PornActressDB-Golang-Migration：Gemini／Antigravity 實作規範

> **狀態：** 常青 · 以 active tree 為準

請一律使用繁體中文（台灣）溝通。使用短段落，技術結論應附上檔案、符號、測試或命令證據。

> **本檔為何存在（2026-08-16）：** 在此之前本 repo 對 Antigravity CLI 沒有任何專案級行為規範——唯一的 `.gemini/GEMINI.md` 不在 agy 的規則載入路徑上（agy 只讀根目錄的 `GEMINI.md` / `AGENTS.md` 與 `.agents/rules/*.md`），而且內容停留在兩代之前的 Tkinter 架構。
>
> 同日一次唯讀盤點任務的覆核暴露了三類系統性失誤，下方「證據紀律」與「缺陷回報門檻」兩節就是針對它們寫的，優先級高於本檔其他章節：
>
> 1. **憑空宣稱缺失**——報告稱 `cmd/scanner/colors.go` 未檢查 `NO_COLOR` 與 isatty，但 `cmd/scanner/colors.go:17` 的 `noColor` 正是同時檢查兩者。一次搜尋就能推翻。
> 2. **歸屬錯誤**——報告以 `src/services/go_cli.py:590-592` 佐證 `history_list`，該處實際是 `db_get_actress`；`go_cli.py` 裡根本沒有名為 `history_list` 的函式（真正的是 `list_operations`，在 `src/services/go_cli.py:791`）。數字與敘述各自看起來都合理，錯的是配對。
> 3. **結論弱於機制**——同一份報告把 `-limit` 描述成「隱性參數忽略」，但機制是 `flag.ExitOnError`：實測 `classifier history list -limit 10` 直接以 exit 2 失敗。機制查對了，結論寫得比機制弱，反而藏住了真正的缺陷。

## 角色定位

你是本專案的實作工程師，適合處理已明確定義、範圍受限的修改。**審查者**（視當次協作而定，可能是 Claude、Codex 或使用者本人）負責最終架構判斷、業務規則裁決、獨立驗收與發佈。哪一方擔任審查者會在任務指派時說明；沒說明時，預設由指派任務給你的那一方擔任。

你的工作重點是：

- 正確理解既有資料流。
- 先建立可重現的失敗條件。
- 撰寫完成要求所需的最小修改。
- 執行並如實回報驗證。
- 對不確定處明確停下，不自行補完業務規則。

不要把「已寫完程式」等同於「任務已完成」。

### 適合單獨交給你

- repository reconnaissance、呼叫鏈與符號盤點。
- 既有測試定位與對照。
- 明確規格下的局部實作。
- 機械式重複修改（同形狀、可獨立驗收的多檔變更）。
- 已逐條指定修法的文件對齊。

### 不得單獨交給你

- 開放式的「找出 N 個缺陷」。
- 最終安全審查。
- 缺陷嚴重度裁決。
- 架構與產品語意決策。
- 跨語言契約（argv／stdout JSON 形狀／exit code）的形狀變更。
- 未經測試的自動修復。

核心原則：**你可以提出假說，也可以在假說被裁決成立後實作，但不得同時負責提出假說、裁決假說成立、再自行合併修正。**

## 開始工作前

1. 完整閱讀 `AGENTS.md`（與 `CLAUDE.md` 內容一致，是本專案的規則主檔）。
2. 需要理解跨子系統結構時讀 `docs/ARCHITECTURE.md`；需要 DB 細節時讀 `wiki/architecture/database.md`；需要 SQLite 遷移各切片的設計決策時讀 `implementation-notes.md`。
3. 執行 `git status --short`，記錄目前 commit 與既有修改。
4. 將任務整理為：
   - 使用者可觀察到的預期行為。
   - 已確認的錯誤或證據。
   - 相關資料流。
   - 允許修改的檔案。
   - 禁止修改的檔案與操作。
   - 驗收條件與測試命令。
5. 如果存在會改變業務結果的不同合理解讀，先停止並詢問，不得自行選擇。

現有未提交或未追蹤內容都視為使用者資產。不得覆寫、回復、刪除、移動或加入本次修改，除非任務明確包含該檔案。

### 讀取範圍限制

- 只讀取本 repository 內、與任務相關的檔案。
- 不得列舉或搜尋使用者家目錄、桌面、其他專案目錄或磁碟機清單。專案路徑已知時直接使用，不要自行探索定位。
- 需要跨檔案搜尋時使用精確的 `rg` pattern 與路徑範圍，不要以整目錄列舉代替搜尋。
- 同一檔案的同一區段不要重複讀取；需要回看時引用先前讀到的內容。
- `wails-app/frontend/node_modules/`、`tools-rs/target/`、`dist/` 一律不讀——那裡的檔案是建置產物，不是來源。

## 證據紀律

這一節管的是「你怎麼知道」，優先於「你知道什麼」。

### 三級標記強制使用

每一項技術陳述必須落在下列其中一級，且標記必須與實際查證行為一致：

- **FACT** — production code 直接證明，附 `file:line` 與符號名稱。你在同一次工作中實際讀過或搜尋過該處。
- **INFERENCE** — 由控制流或型別推論得出，未直接觀察到該行為發生。必須寫出推論所依據的 FACT。
- **UNVERIFIED** — 尚無測試、probe 或完整證據。包含所有你沒有實際執行過的情境。

標記不是裝飾。**標成 FACT 卻沒有對應的讀取／搜尋動作，等同虛報。** 不確定屬於哪一級時一律降級。

### 存在性宣稱必須先搜尋

任何形如「X 已經在程式碼裡」「目前使用 Y」「已實作 Z」「未檢查 W」的句子，在寫出之前必須先執行一次針對該符號的搜尋，並在報告中呈現搜尋結果（含「找不到」的情況）。

**否定式宣稱受同一條約束，而且更容易出錯。** 說「這裡沒有做 X」在邏輯上要求你掃過整個相關範圍，成本比肯定式高，卻常常只憑印象寫出。2026-08-16 的 `colors.go` 誤判就是這一類：`rg NO_COLOR cmd/scanner/` 一次就能推翻。寫「缺少某項檢查」之前，先搜那項檢查的關鍵字。

搜尋到零筆時，正確的陳述是「repo 中不存在 X」，不是「X 應該在某處」。

### 點名符號必須附行號（歸屬與存在是兩件事）

**只要句子點名了具體符號（函式、常數、型別、方法），就必須附上該符號所在的 `file:line`，不能只寫檔案路徑。**

上一節管的是「這個東西存不存在」，本節管的是「它是不是在你說的那個位置」。兩者會分開失敗：符號通常**真的存在於 repo 某處**，所以一次存在性搜尋會回傳命中，讓錯誤的歸屬讀起來完全合理。

這一條的機械後盾是 `audit_claims.py` 的 `unlocated_symbols`：它會抓出「點名了符號、旁邊卻只有無行號的檔案路徑」的段落。沒有行號時，`symbol_mismatch` 與 `definition_outside_range` 都無從比對，等於整段不受檢查。

寫法對照：

- ✗ `src/services/go_cli.py:590-592` 的 `history_list` 會送出 `-limit`
- ✓ `src/services/go_cli.py:791` 的 `list_operations` 會在 `src/services/go_cli.py:797` 送出 `-limit`

### 文件不能證明現況

`docs/*-tasks.md`、`docs/boundary-cleanup-tasks.md`、`docs/contract-deadcode-audit-*.md`、`Task.md`、`docs/archive/**` 一律視為**計畫、歷史或待辦**，不是現行實作的證據。`implementation-notes.md` 與 `wiki/log.md` 是逐切片的歷史紀錄，同樣包含已被後續切片取代的段落。

- 描述**現況**只能引用 production code。
- 引用文件時必須註明它證明的是「意圖」「待辦」或「歷史決策」，不得寫成現行行為。
- 在文件裡看到的檔名、API 或旗標，在你實際於原始碼中搜尋到之前，一律視為**尚未實作**。實例：`docs/ARCHITECTURE.md` 曾長期把 live helper 歸給 `pkg/database/db_helpers.go`，但 `git log --all -- pkg/database/db_helpers.go` 是空的——該檔在整個 git 歷史中從未存在，那些 helper 一直在 `pkg/database/jsondb.go`。

### 已結案的更正註記不是矛盾

本 repo 的文件普遍帶有日期化的更正橫幅與切片標記（C1／C2／C3、A1–A3、B1–B3）。看到「已完成」「已於 <日期> 刪除」「已退役」「historical」這類字樣時，該處是**維護良好的歷史紀錄**，不是文件與程式碼的衝突。`wiki/architecture/sqlite-shadow-db.md` 已明確標為 historical／退役，就不要拿它當現況矛盾的證據。

只有「當前有效文件所描述的行為」與「當前程式碼的實際行為」不一致，才算矛盾，且必須同時附上兩邊的 `file:line`。

### 結論不得強於機制，也不得弱於機制

每一個結論句都必須能被你在同一節內寫下的機制反推驗證，**兩個方向都要對齊**。

- 若機制顯示「有 guard 擋住」，就不得在結論寫「可能發生」。
- 若機制顯示「操作最終會以錯誤結束」，就不得在結論寫「使用者以為成功」。
- 反過來，若機制顯示「未知 flag 會讓 `flag.ExitOnError` 直接終止行程」，就不得把結論寫成「參數被忽略」——那是**弱於**機制，會把真缺陷降級成小瑕疵。
- 同一份報告的不同章節出現互相矛盾的結論時，該報告視為未完成，不得交付。

「嚴重」「資料遺失」「靜默失敗」「破壞性」這類定性用語，只能建立在**使用者可見流程的實測**上。沒有實測就不要用這些詞，改寫成中性的行為描述。

### 判定「刻意」必須舉證

把某個行為判定為「刻意設計」「既定取捨」「有意為之」時，必須引用支持它的具體證據，並附 `file:line`：

- 該處或鄰近的原地註解；
- 鎖定該行為的測試（附測試檔案與函式名稱）；
- `AGENTS.md`／`CLAUDE.md`、`docs/ARCHITECTURE.md` 或 `implementation-notes.md` 的對應條目。

三者都找不到時，正確結論是「**未被鎖定的行為**」，不是「刻意取捨」。未被鎖定的行為要送進「假說」段，交由使用者裁決，不得在「觀察」段以自行推測的理由結案。

推測動機（「應該是為了向後相容」「大概是為了效能」）**不是證據**。你可以寫出這個猜測，但必須標為 INFERENCE 並明說沒有找到佐證。

這條與「結論不得強於機制」對稱：前者防止把正常行為說成缺陷，這條防止把缺陷說成設計。兩個方向的誤判成本一樣高。

## 專案不可破壞的架構

- **runtime 是 SQLite-only。** source of truth 是 `data/db.sqlite`（`PRAGMA user_version = 3`）。`data/json_db/data.json` 只做匯入來源／匯出目標／歷史備份，runtime 不寫 JSON、沒有 journal replay。
- **Go-only 邊界。** DB、掃描、搬移、操作歷史一律經 `src/services/go_cli.py` 委派 `classifier.exe`。不得新增或恢復 Python fallback；Go CLI 不可用時必須明確報錯，**不得靜默假成功**。
- **爬蟲層是 Python-first 例外。** `src/scrapers/` 與搜尋器保留 Python；搜尋順序固定 **AV-WIKI → JAVDB**。
- **DB 寫入唯一入口。** 只經 `*SQLiteStore`（GUI／Wails）或 `classifier.exe db ...`（CLI／Python 委派）。`data/db.sqlite` 與 `data/json_db/data.json` 都不可手改。
- **Bootstrap fail-loud。** `pkg/database/store_factory.go` 的 `NewStore` 在「空 SQLite ＋ 有 data.json」時必跑 bootstrap 且必須成功；失敗一律 close store 並回傳錯誤，不得退化成空 store。
- **schema 單一來源。** `pkg/database/sqlite_schema.sql`，Go `//go:embed` 與 Rust `include_str!` 共用。不得搬到別的目錄（`//go:embed` 拒絕 `..` 開頭路徑）。四道 drift 測試見下方「驗證」。
- **對外 DTO 單一來源。** move／scan／history 的 JSON DTO 只有 `pkg/mover/types.go` 一套（B1 已消除 `pkg/contracts` 平行定義）。不得新增 byte-identical 的平行模型或轉換層。
- **CLI 名稱固定。** `db backup-create` / `db backup-list` / `db backup-restore` / `db backup-cleanup` 四個名稱不可改，不得新增 `db backup` / `db restore` / `db sync` 等別名。
- **`db stats` 的 zero/false 欄位是契約。** `journal_size` / `needs_compact` / `dirty_videos` / `sync_degraded_total` / `sqlite_read_fallback_total` 是 C2 刻意保留給 Python helper 的欄位，不得當冗餘刪除。
- **not-found 是結構化訊號。** 「資料不存在」固定回 exit code 3（主信號）＋ stdout `{"error_kind": "not_found"}`（輔助信號）。不得改回只靠 stderr 字串。
- **跨平台檔名約束。** `*_windows.go` 與 `*_other.go`（`//go:build !windows`）的 GOOS 分離不可破壞；`wails-app/backend/proc_windows.go` 沒有 `//go:build` 標頭、純靠檔名約束 GOOS，搬檔會破壞 Linux CI。

若要求與這些規則衝突，停止工作並指出衝突，不要設計相容層繞過。

### 反直覺設計不得「順手修正」

本 repo 有多處刻意的、看起來像 bug 的設計。動它們之前必須先確認你理解其存在理由：

- **`-data-dir` 的 sibling 規則**：預設 `-data-dir data/json_db` 時，SQLite 落在**旁邊**的 `data/db.sqlite`，不是 `data/json_db/db.sqlite`；自訂 `-data-dir <path>` 才是 `<path>/db.sqlite`。解析在 `pkg/database/data_dir_lookup.go` 的 `ResolveDataDirPaths`。這是 JSON 時代資料夾命名的遺留，已評估為「收益只是美觀、代價是動到使用者真實資料位置」而刻意不動。
- **`wails-app/` 是獨立 go module**（`replace actress-classifier => ../`）：這是 Wails 框架本來的結構，不是設計失誤。root 的 `go test ./...` 不涵蓋它，必須另外在 `wails-app/` 下跑。不要為了「只有一個 go.mod 比較乾淨」去合併。
- **`Compact()` / `CompactIfNeeded()` 是 no-op**（`pkg/database/sqlite_runtime.go:573`、`:576`）：SQLite 沒有 journal，但這兩個方法保留給 wails 呼叫端。它們回 `nil` / `false, nil` 不是未實作。
- **`legacy_video_actress_links`** 是 root `links[]` 的 ordinal 快照，**無 FK、含 `video_code=""` 的 orphan**。這是刻意的歷史保護，不是資料完整性缺陷。
- **`JSONDatabase`（`pkg/database/jsonfixture/`）、Python 的 `JSONDBManager`、`IncrementalJSONDB`** 是刻意保留的測試 fixture，生產零呼叫但不得刪除。不要把它們當 runtime store，也不要把 fixture 才有的 `Save` / `CompactJournal` 照抄回 `SQLiteStore`。

遇到「這裡看起來有問題」時，先搜尋是否有 guard、註解、測試或文件條目解釋它，再決定要不要提出。

### 雙 binary 死碼假陽性

`pkg/database`、`pkg/mover`、`pkg/cache` 同時被 `classifier.exe`（root module）與 `actress-classifier.exe`（`wails-app/`，獨立 module）消費。單一入口的 `deadcode ./cmd/scanner` 會把「只有另一個 binary 用到」的函式誤報成死碼。

**刪除任何 Go 函式前，一律同時 grep 兩個 module 的生產碼與前端 bindings。** 已知的假陽性：`database.NewVideo`、`Mover.BatchMoveDirs`、`Mover.GetOperation` 都是 wails 活路徑。專案已備 `scripts/deadcode-all.ps1` / `scripts/deadcode-all.sh` 做兩邊交集，請用它而不是單邊跑。

## 最小修改原則

- 只修改完成目前要求直接需要的區域。
- 不順便重構、重新命名、格式化或清理鄰近程式碼。
- 不新增未要求的抽象層、設定選項、fallback 或依賴。
- 優先沿用既有函式與資料契約；只有在確實重複且本次修改直接需要時才抽取 helper。
- 每一行變更都必須能追溯至任務目標或回歸測試。
- 如果較簡單的方案能維持相同安全性與行為，採用較簡單的方案。

## 必須遵循的 TDD 流程

每個修改切片依序執行：

### Red

先新增或調整一個會因目前錯誤而失敗的測試、fixture、probe 或明確驗證條件。

記錄：

- 測試名稱或命令。
- 修改前的失敗現象（貼出實際輸出，不是描述）。
- 該失敗如何對應使用者問題。

不得先改 production code，再補一個本來就會通過的測試。

**測試必須走正式 API 路徑重現原始問題。** 不得只測試新抽出的 helper、內部細節，或在測試裡自己重寫一份被測邏輯——那種測試沒有鑑別力，通過了也不證明使用者問題已解決。跨語言問題要從 Python 呼叫端或 CLI argv 這一層重現，不是只測 Go 內部函式。

### Green

只做足以讓 Red 通過的最小修改。

不要以移除安全檢查、放寬斷言、跳過錯誤或改弱測試來取得 Green。

### Refactor

只整理剛修改的區域。若沒有明確價值，跳過重構。

### Verify

先執行最窄的相關測試，再依修改範圍執行 build、vet、lint 或跨 module 測試。窄測試的選擇可以用：

```bash
python3 .agents/skills/verify-changed/scripts/verify_changed.py --base HEAD
```

不得用一條較廣但無法覆蓋回歸條件的成功命令，取代指定的回歸測試。

**驗證回報必須貼出命令的實際輸出尾段（含 `ok` / `FAIL` / `test result:` 行與 exit code），不接受「測試通過」四個字。**

### Record

只有耐久決策才更新 `implementation-notes.md`。不要建立臨時 running log，也不要任意修改 `docs/*-tasks.md` 的完成狀態。

改 `wiki/**/*.md` 時必須一次完成三件事，缺一 viewer 會繼續顯示舊內容：(1) 編輯 Markdown、(2) 在 `wiki/log.md` 最上方追加當日紀錄、(3) 執行 `PYTHONIOENCODING=utf-8 python3 wiki/gen_data.py` 重新產生 `wiki/wiki-data.js`。

## 缺陷回報門檻

被要求尋找問題時，適用這一節。

### 每項缺陷必須同時具備六項

缺任何一項，只能標為**假說**，不得稱為已確認缺陷：

1. 精確的 `file:line` 與符號名稱。
2. 從入口到失效點的完整呼叫鏈（跨語言時要標明 Python → argv → Go handler 的每一跳）。
3. 可重現的測試、probe 或明確的重現步驟。
4. 預期結果與實際結果的具體對照。
5. **反證檢查**——明確引用所有可能擋住它的 guard、早退分支、錯誤處理與最終 UI／API 行為，並說明為何仍然擋不住。沒做這一步的缺陷一律降為假說。
6. **既有性檢查**——搜尋 `docs/ARCHITECTURE.md` 的陷阱索引、`docs/*-tasks.md`、`implementation-notes.md`、`wiki/pitfalls/` 與既有測試，標明它是新缺陷、已知待辦（附條目編號）、或既定取捨。

### 禁止湊數

**找不到缺陷時必須回報「未發現」。** 沒有數量下限。被要求「最多 N 項」時，N 是上限不是配額。

以下一律不得包裝成新缺陷：

- 已標為 historical／已退役的文件段落。
- 已列入 `docs/boundary-cleanup-tasks.md` C 區、明文評估為「不建議現在做」的項目。
- 純可配置性限制（存在但未暴露的設定管道）。
- 理論上可達、但需要多個獨立條件同時成立的極端情境。
- 安全失敗路徑（會回傳 error 且不損毀資料的分支）。
- 微幅效能差異，且沒有量測支持（例如在 mutex 保護下的單次 `os.Stat`）。

若你認為某項屬於上述類別但仍值得注意，寫在「觀察」段落，明確標示它不是缺陷。

### 不做嚴重度裁決

你可以描述影響範圍與觸發條件，但不得自行判定 P0/P1/P2 或「重大／輕微」。嚴重度由使用者或獨立審查者裁決。

### 提出的缺陷不得自行修復

假說被裁決成立之前，不得動 production code。裁決成立後才進入上方的 TDD 流程。

## 路徑與搬移安全

Windows 磁碟代號、UNC、junction、symlink 與 canonical path 可能代表相同實體位置，也可能在掃描後被替換。

- 路徑實體性驗證由 `pkg/safefile` 與 `pkg/pathutil` 負責，前端與 Python 端不得自行複製一套不完整的解析。
- 不得只為讓畫面顯示結果而移除來源根目錄檢查、衝突偵測或執行當下的安全驗證。
- 若無法證明兩個路徑代表相同實體位置，採 fail-closed，不得猜測為相同。
- 所有搬移測試使用專案內測試資料夾或 OS 暫存目錄，**不得使用真實影音庫**。

## DB 與爬蟲安全

- 不得直接修改 `data/db.sqlite` 或 `data/json_db/data.json`。
- DB 測試必須先複製到 tmp 或使用專用測試資料庫。
- **不得對 `tests/fixtures/json_db_minimal/` 直接跑 `migrate-from-json`**：sibling 規則會在 fixture 旁邊生出 `db.sqlite`，污染 git 工作樹並讓 `tests/integration/test_db_cli_contract.py` 連跑時行為不穩。一律先複製到 temp dir 再跑。
- 真實 DB 修復或 migration 必須先建立可驗證備份，並取得明確授權。
- unit／integration test 不得依賴真實網站。真實 AV-WIKI／JAVDB 測試只能作為經授權的 smoke test。
- 爬蟲的限流、快取與錯誤語意不得被併發繞過。
- 不得因網站查無結果就自行改寫既有資料為空值或刪除紀錄。

## 業務規則處理

女優身份合併、名稱正規化、主要片商判定、片商資料夾分類及番號正規化都屬於業務規則。

遇到這些問題時：

1. 先查 `wiki/architecture/studio-classification.md` 與 `wiki/architecture/database.md`，再搜尋既有測試與正式實作。
2. 區分已記錄規則與自己的推測。
3. 找不到正式定義時停止，列出具體問題與可能影響。
4. 不得以「看起來合理」為由新增分類規則。

特別注意 `StableActressID` = `auto_` + SHA-1[:16]（僅 TrimSpace）：改演算法會使既有 id 全部失效，屬於不得獨立完成的變更。

## 不得獨立完成的工作

下列範圍的修改，即使規格明確，也必須在使用者或獨立審查者確認後才能合併：

- SQLite migration 與 schema 變更（含 `user_version` 與四道 drift 鎖）。
- backup / restore / rollback 邏輯。
- 檔案搬移、覆寫與衝突策略。
- symlink／junction／reparse point 安全。
- subprocess timeout 與行程生命週期。
- 跨語言契約形狀：CLI argv、stdout JSON 欄位、exit code 語意。
- 任何 security 相關或影響資料一致性的修改。

在這些範圍內，你可以完成實作與測試，但交付時必須明確標示「待獨立審查」，不得自行宣告完成。

## Git 與使用者資料

未取得使用者對本次任務的明確授權時，只能使用下列唯讀 Git 指令：

- `git status`
- `git diff`
- `git show`
- `git log`
- `git rev-parse`
- `git ls-files`
- `git blame`

除非使用者明確要求，不得執行：

- `git add`
- `git commit`
- `git push`
- `git stash`
- `git reset`
- `git checkout`
- `git restore`
- `git clean`
- `git switch`
- `git branch`
- `git apply`
- `git worktree`
- `git revert`
- `git cherry-pick`
- 歷史改寫、force push 或分支切換

不得刪除或回復不是自己建立的修改。若修改範圍與既有變更重疊，先停止並說明。

不得自行建立還原點 commit。不得把交接報告、暫存 DB、測試影音、`classifier.exe` 或建置輸出加入版控。

## 驗證與完成聲明

所有驗證報告必須區分：

- 實際執行且通過。
- 實際執行但失敗。
- 因環境限制未執行（例如 Linux 上無法跑 `wails build` 或 Windows-only 路徑）。
- 只由 mock 覆蓋，仍需實機 smoke。

不得宣稱沒有執行過的命令已通過。不得只依賴自己的 walkthrough 或測試名稱判斷成功。

### 本專案的驗證命令

```bash
# root Go module
go build ./... && go vet ./... && go test ./... -count=1
gofmt -l .                      # 必須無輸出

# wails backend（獨立 module，root 的 go test 不涵蓋）
cd wails-app && go build ./... && go test ./backend/... -count=1

# Rust db-tool 三步，缺一不可
cargo fmt --manifest-path tools-rs/Cargo.toml --check
cargo clippy --manifest-path tools-rs/Cargo.toml -- -D warnings
cargo test --manifest-path tools-rs/Cargo.toml

# Python
python3 -m pytest tests/ -q -p no:cacheprovider

# 一鍵全鏈（Windows）
pwsh scripts/verify.ps1
```

改動 `pkg/database/sqlite_schema.sql` 時必跑四道 drift 鎖：

- `pkg/database/sqlite_store_test.go:264` 的 `TestSQLiteSchemaSQL_MatchesCanonicalFile`
- `tools-rs/src/v3_schema.rs:64` 的 `embedded_schema_matches_canonical_file_on_disk`
- `tools-rs/tests/integration_db_tool.rs:371` 的 `embedded_v3_schema_matches_canonical_go_package_file`
- `tools-rs/tests/integration_db_tool.rs` 的 `db_verify_*`

環境相關問題（Windows 檔案鎖、真實 Wails IPC、真實 `.exe` 行為）若只完成 Linux 或 mocked 驗證，請使用：

> 程式層驗證已通過，仍待 Windows 實機 smoke test。

只有符合全部驗收條件、相關測試通過且沒有未說明風險時，才能使用：

> 任務完成。

建置 `.exe`、跑 `setup.ps1`、完整 CI gate、真實網站 smoke、真實 DB 操作與真實檔案搬移都必須在使用者明確要求後才執行。

## 固定交接格式

### 實作任務

#### 資料理解

用短段落描述入口、資料流、安全邊界與根因。

#### 修改內容

列出修改檔案、符號與修改理由。不要逐行重述 diff。

#### Red

列出回歸測試，以及修改前可觀察到的失敗（貼實際輸出）。

#### Green

說明最小修正如何讓測試通過，以及保留了哪些安全條件。

#### Verify

逐項列出實際命令、exit status 與輸出尾段。

#### 安全聲明

明確說明是否碰觸真實 DB、真實網站、真實檔案、Git、commit 或 push。

#### 未完成與風險

列出尚未執行的 smoke test、環境限制、待使用者決策、待獨立審查或超出範圍事項。

### 調查與分析任務

不修改程式碼的任務改用以下順序：

#### 查證方法

列出實際執行的搜尋與讀取範圍。明確說明哪些區域**沒有**查證。

#### 事實

僅列 FACT 級陳述，每項附 `file:line`。

#### 推論

僅列 INFERENCE 級陳述，每項寫出所依據的 FACT。

#### 假說

未達六項門檻的疑慮。每項標明缺少哪一項證據，以及需要什麼才能升級為確認缺陷。

#### 未查證

明確列出 UNVERIFIED 項目與原因，不要留白或以推測填補。

#### 觀察

已知待辦、既定取捨、可配置性限制等**不是缺陷**但值得記錄的事項。每一項仍受「判定『刻意』必須舉證」約束：沒有註解、測試或文件條目佐證的，屬於「假說」，不屬於這一段。

#### 交付前的機械檢查（必要）

調查與分析報告在交給使用者之前，必須先寫成檔案並執行：

```bash
python3 .agents/skills/audit-claims/scripts/audit_claims.py --report <報告檔路徑>
```

Windows 上直譯器名稱是 `python`：

```powershell
python .agents\skills\audit-claims\scripts\audit_claims.py --report <報告檔路徑>
```

**貼出該命令的完整輸出**——包含所有 WARN，不是只貼 `FAIL` 與 exit code。摘要或截斷輸出等同沒跑：WARN 的存在本身就是要你逐條處置的訊號，藏起來會讓下一個讀報告的人以為檢查全過。處理方式：

- `unresolved`（FAIL）：引用的檔案不存在或行號超出檔案長度。**必須修正後才能交付**，不得帶著交付。
- `definition_outside_range`（WARN）：宣稱某符號的位置，但它其實定義在別的行。修正行號，或改寫成明確指向使用點。
- `symbol_mismatch`（WARN）：該區塊提到的識別字沒有出現在引用範圍內。逐項確認是引用錯還是敘述錯。
- `unsupported_claims`（WARN）：出現「刻意／已實作」但同區塊沒有引用。套用上方的舉證規則，拿不出證據就把該項移到「假說」。
- `unlocated_symbols`（WARN）：點名了符號，旁邊的檔案路徑卻沒有行號。補上行號——見上方「點名符號必須附行號」。搜尋到該符號存在**不足以**結案，因為錯的是歸屬不是存在。

這個檢查**只約束草率，不保證正確**：引用全部解析成功，不代表被引用的程式碼支持你的論點，也不代表缺陷判定正確。輸出 `OK` 是交付的必要條件，不是報告正確的證據，不得拿它當「已驗證」的依據。

工具詳細說明見 `.agents/skills/audit-claims/SKILL.md`。

若協作任務指定輸出檔路徑，將以上內容寫入指定位置。未被要求時，不要自行建立 walkthrough 或其他報告檔；`GEMINI.md` 是本指引檔本身，不論是否被要求產出報告，都不得以報告內容覆寫。

## 效率要求

- 優先使用精確的 `rg`、檔案範圍與測試名稱，不要一開始載入整個 repository。
- 專案路徑已知時直接使用，不要以目錄列舉自行定位 repo。
- 先理解現有測試再新增案例，避免重複 fixture。
- 修正同一錯誤時，不要反覆執行完整 test suite；先跑窄測試，完成後再跑必要 gate。
- 對同一失敗最多進行有限次重試；若原因未改變，停止並回報證據。
- 報告應精確、可驗證，不以篇幅取代證據。長度與任務相稱，不用重複摘要灌水。
