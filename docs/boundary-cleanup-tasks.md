# 邊界清理任務清單(契約/介面更乾淨)

> 來源:`docs/ARCHITECTURE.md` §7「未來 AI 易踩的坑」（原 10 條，B1 完成後縮為 9 條）的可行性評估。
> 產出:2026-05-30 ｜ 狀態:A 區、B 區已全數完成（2026-08 前），C 區維持文件化不動。
> 本檔分三區:**A 馬上做**(低風險,可一批並行)、**B 值得做**(中風險真重構,序列)、**C 不硬做**(白話說明為何暫緩)。

## 怎麼用這份檔

- **用 `/goal` 跑單一任務**:把某任務的「🎯 /goal 句」整段貼給 `/goal`,它會 loop 到該任務的 DoD 全綠為止。DoD 都寫成可機檢條件(build/test/grep),不含需要你中途判斷的卡點。
- **用 `/workflow` 並行**:看每任務的「檔案集」。**A 區三個任務檔案集互斥 → 可放同一個 workflow 一批並行執行**。B 區三個是 cohesive 真重構、且彼此/與既有檔有重疊 → **逐一序列**(每個可在內部用 workflow 做調查/驗證,但編輯要聚焦單一關注點)。
- **驗證**:每任務附「驗證程序」。全部做完後跑 `docs/contract-deadcode-audit-2026-05-30-tasks.md` 的通用驗證指令庫(G1–G8)+ `/tool-scan`(最終閘,**修正落地後才跑**)。

---

# A 區 — 馬上做(低風險、純工具/腳本/文件層,可一批並行)

> 這三個**不碰任何生產邏輯**,只新增腳本或修文件/測試 seed。檔案集互斥,適合一個 workflow 三 agent 並行。

## A1 — combined deadcode 腳本(消除雙 binary 假陽性) ✅ 已完成
- **對應坑**:#1。`deadcode ./cmd/scanner` 會把只有 wails 用的函數誤報死碼。
- **檔案集**:`scripts/deadcode-all.ps1`(新檔)、`scripts/deadcode-all.sh`(新檔)。**不動既有檔。**
- **做法**:寫腳本同時從 `./cmd/scanner`(root)與 `wails-app/`(`deadcode .`)跑 `deadcode`,各自輸出 unreachable 清單,**取兩邊交集**(只有兩個 binary 都不可達才算真死碼),排除 `*_test.go`。輸出人類可讀清單 + 提示「交集外的是另一 binary 在用,勿刪」。
- **完成條件(DoD)**:`scripts/deadcode-all.ps1` 存在且可執行;對當前 repo 跑出的「真死碼」清單**不包含** `database.NewVideo`/`Mover.BatchMoveDirs`/`Mover.GetOperation`(已知 wails 活路徑,證明交集邏輯正確)。
- **驗證**:`pwsh scripts/deadcode-all.ps1`(需 `go install golang.org/x/tools/cmd/deadcode@latest`),確認輸出不含上述三個 wails-live 函數。
- 🎯 **/goal 句**:`/goal 寫 scripts/deadcode-all.ps1 + .sh,同時從 cmd/scanner 與 wails-app 跑 deadcode 取交集當真死碼清單,排除 *_test.go;驗證輸出不含 database.NewVideo/Mover.BatchMoveDirs/Mover.GetOperation 這三個 wails-live 函數`

## A2 — 本機統一驗證腳本(消除 Rust 三步/跨 module 漏跑) ✅ 已完成
- **對應坑**:#5(Rust 只跑 cargo test 漏 fmt/clippy)、#4 的痛點(root go test 不涵蓋 wails)。
- **檔案集**:`scripts/verify.ps1`(新檔)。**不動既有檔。**
- **做法**:一個腳本依序跑全工具鏈並在任一步紅時非零退出:root `go build/vet/test ./...` → wails `cd wails-app; go build ./...; go test ./backend/...` → Rust **三步**(`cargo fmt --check` + `cargo clippy -- -D warnings` + `cargo test`)→ `python -m pytest tests/ -q`。可加 `-Quick` 旗標只跑 build+lint。
- **完成條件(DoD)**:`scripts/verify.ps1` 存在;在當前(全綠)樹上執行回 exit 0 且涵蓋 5 個工具鏈步驟;故意把 `tools-rs` 某行縮排弄壞後執行會非零退出(證明 fmt --check 有納入)。
- **驗證**:`pwsh scripts/verify.ps1` → exit 0;臨時破壞 fmt 再跑 → 非零,還原。
- 🎯 **/goal 句**:`/goal 寫 scripts/verify.ps1 一鍵跑 root go(build/vet/test ./...) + wails(build/test ./backend) + Rust 三步(fmt --check/clippy -D warnings/test) + python pytest,任一步紅就非零退出;驗證當前樹 exit 0、且故意弄壞 tools-rs fmt 後會非零`

## A3 — 修 fixture 污染(recipe + 測試 seed) ✅ 已完成
- **對應坑**:#6。對真 `tests/fixtures/json_db_minimal/` 跑 `migrate-from-json` 會留下 `db.sqlite` 被整合測試 copy 進去而紅。
- **檔案集**:`tests/integration/test_db_cli_contract.py`、`docs/contract-deadcode-audit-2026-05-30-tasks.md`(G7 recipe)、`CLAUDE.md`(CI 注意點的本機重現指令)。
- **做法**:(1) 整合測試的 `_seed_fixture_data_dir`/copytree 改成**只複製 `data.json`** 到 tmp(而非整個 fixture 目錄),或在 copy 後主動刪除任何 `db.sqlite*`。(2) 文件的 G7 本機重現 recipe 改成**先複製 fixture 到 temp dir 再 migrate**,並加註「勿對真 fixture 跑、會污染」。
- **完成條件(DoD)**:`python -m pytest tests/integration/test_db_cli_contract.py -q` 綠;且**連續跑兩次**都綠(證明不再有殘留污染);文件 recipe 不再直接寫 `tests/fixtures/**`。
- **驗證**:`python -m pytest tests/integration/test_db_cli_contract.py -q`(跑兩次)。
- 🎯 **/goal 句**:`/goal 修 fixture 污染:tests/integration/test_db_cli_contract.py 的 fixture seed 改成只複製 data.json 到 tmp(或 copy 後刪 db.sqlite*),G7 recipe 與 CLAUDE.md 本機重現改成先複製到 temp dir 再 migrate;驗證該整合測試連跑兩次都綠`

> **A 區 /workflow 提示**:三任務檔案集互斥(scripts 兩新檔 / scripts 一新檔 / tests+docs),可用**一個 workflow 三 agent 並行**(各自 self-verify 自己 scope),完成後跑 A 區三個驗證確認。

---

# B 區 — 值得做(中風險真重構,逐一序列,有測試保護)

> 這三個是真的動生產碼的重構,**不要並行**(彼此或與既有檔有重疊、且需聚焦驗證)。建議各自一個 `/goal` loop,內部可用 workflow 做調查/對抗式驗證。每個都先做「調查 → 計畫 → 編輯 → 驗證」四步。

## B1 — DTO 收斂(消除四處同步)【建議最先做,ROI 最高】 ✅ 已完成
- **對應坑**:#3。`pkg/contracts` 與 `pkg/mover` 是兩套 byte-identical 平行 DTO,靠 `pkg/app` 手寫轉換橋接;改欄位要動四處且漏了不會編譯失敗。
- **檔案集**:`pkg/contracts/{scan,move,history}.go`、`pkg/app/{scan,move,history}_service.go`、`cmd/scanner/*.go`(序列化點)、`tests/test_go_cli_contracts.py`(契約鎖)。wails 用 `mover.*` alias,**通常不需動**(但要驗)。
- **做法(二擇一,預設採 A)**:
  - **(A) 收斂到 `mover.*`(推薦)**:刪 `pkg/contracts` 的 move/scan/history DTO 與 `pkg/app` 的 `*ToContract` 轉換層,讓 `cmd/scanner` 直接序列化 `mover.*`/`extractor.*`/對應型別。`pkg/app` 服務函式改回傳 `mover.*`。GUI 已用 `type X = mover.Y`,證明可行。
  - (B) 保留 `contracts` 當唯一邊界,讓 `mover` 改用 `contracts` 型別(反向)。
- **完成條件(DoD)**:全專案只剩**一套** move/scan/history 對外 DTO(grep 確認 `pkg/contracts/move.go` 等已移除或已成唯一來源);`tests/test_go_cli_contracts.py` 全綠(JSON 形狀不變);root + wails `go build/test` 全綠;CLI `move`/`history`/`scan` 輸出 JSON 與重構前逐欄一致(可用既有契約鎖證明)。
- **不可破壞**:輸出 JSON tag 與形狀**必須完全不變**(下游 Python/前端只認形狀)。`files_skipped` 等欄位不可遺失。
- **驗證**:`go test ./... -count=1`、wails `go test ./backend`、`python -m pytest tests/test_go_cli_contracts.py -q`,並手動比對 `classifier.exe move/history` JSON。
- 🎯 **/goal 句**:`/goal 收斂 move/scan/history DTO 成一套:刪 pkg/contracts 的這三組 DTO 與 pkg/app 的 *ToContract 轉換,cmd/scanner 直接序列化 mover.* ;DoD=全專案只剩一套對外 DTO、輸出 JSON 形狀逐欄不變、root+wails go test 與 test_go_cli_contracts.py 全綠`
- 🔧 **/workflow 提示**:先一個唯讀 agent 盤點所有 `contracts.*`/`*ToContract` 使用點與 wails alias 依賴,再序列套用編輯,最後並行驗證 root/wails/python。

## B2 — 結構化 not-found 訊號(消除 stderr 字串依賴) ✅ 已完成
- **對應坑**:#8。`go_cli._is_not_found_error` 靠 Go stderr 英文 `"not found"` 子字串區分「資料不存在 vs 真錯誤」;Go 改措辭就壞。
- **檔案集**:`cmd/scanner/db_cmd.go`(`runDBGet`/`runDBDelete`/`runDBActressGet`/`runDBActressDelete` handlers)、`src/services/go_cli.py`(`_is_not_found_error` 與 `db_get/delete_*`)、`tests/test_go_cli_contracts.py`。
- **做法**:Go 端「資料不存在」改用**結構化訊號**——擇一:(a) 專屬 exit code(如 `3`),(b) stdout `{"error_kind":"not_found"}`。Python `_is_not_found_error` 改判該結構化訊號(保留舊字串比對當 fallback 一版過渡)。
- **完成條件(DoD)**:`db get <不存在>` 回穩定的結構化 not-found 訊號(exit code 或 JSON `error_kind`);`go_cli.db_get_video(<不存在>)` 仍回 `None`、`db_delete_video` 仍回 `False`,且**不再依賴** stderr 中文/英文措辭(把 Go 訊息改成中文後測試仍綠);新增測試鎖定該行為。
- **驗證**:`go test ./cmd/scanner`、`python -m pytest tests/test_go_cli_contracts.py tests/test_coverage_go_cli.py -q`;手動把 Go not-found 訊息改成中文驗證 Python 仍正確分流(驗完還原)。
- 🎯 **/goal 句**:`/goal 把 db get/delete 的 not-found 從 stderr 字串改成結構化訊號(exit code 3 或 stdout error_kind=not_found),go_cli._is_not_found_error 改判結構化欄位;DoD=db_get/delete_* 對不存在仍回 None/False、且把 Go 訊息改成中文後測試仍綠、新增鎖定測試、go test 與 pytest 全綠`

## B3 — JSONDatabase 移到獨立 fixture package(消除「誤當 runtime」混淆) ✅ 已完成
- **對應坑**:#7。`JSONDatabase`(`jsondb.go`/`journal.go`)是生產死碼、刻意保留為測試 fixture,但結構上與 runtime store 同 package,易被誤用。**這是不做完整移除(避免 ~92 測試重寫)前提下的中間方案。**
- **檔案集**:`pkg/database/jsondb.go`、`journal.go` → 搬到新 package(如 `pkg/database/jsonfixture/`);所有 import `JSONDatabase`/`NewJSONDatabase`/`setupTestDB`/`loadedJSONDB`/`seededJSONDB` 的 `*_test.go`(改 import 路徑);`db_helpers.go` 內被 SQLiteStore 依賴的 live free-functions **留在 `pkg/database`**(它們不屬 fixture)。
- **做法**:把 `JSONDatabase` 型別 + 其方法 + journal + 純服務它的型別搬到 `pkg/database/jsonfixture`(或 `internal/jsonfixture`),改用 export 名稱供測試 import;`pkg/database` 的 runtime 檔不再含 `JSONDatabase`。注意 `db_helpers.go` 的 merge/backup/欄位 helper 是 live、**不可搬**。注意 `actress_cleaner.go` 的 `ActressCleanupTarget` 介面讓 cleaner 同時作用於 SQLiteStore 與 fixture——介面要跨 package 仍可用。
- **完成條件(DoD)**:`pkg/database`(runtime 檔)內 grep 不到 `type JSONDatabase`;fixture 在獨立 package 且測試改 import 後 `go test ./pkg/database/... -count=1` 全綠;`go build ./...` 與 wails build 全綠;`deadcode ./cmd/scanner` 不新增不可達。
- **不可破壞**:`db_helpers.go` 的 live helper 留在原 package;schema-drift 四鎖全綠。
- **驗證**:`go test ./pkg/database/... -count=1`、`go build ./...`、wails build、四道 schema drift 鎖、CI 釋出閘(在 temp dir)。
- 🎯 **/goal 句**:`/goal 把 JSONDatabase(jsondb.go+journal.go)搬到獨立 package pkg/database/jsonfixture,測試改 import;db_helpers.go 的 live helper 留在 pkg/database;DoD=runtime 檔 grep 不到 type JSONDatabase、go test ./pkg/database/... 全綠、root+wails build 綠、schema drift 四鎖綠`
- 🔧 **/workflow 提示**:先唯讀 agent 盤點 fixture vs live 的精確分界(哪些符號搬、哪些留)與所有 test import 點,再序列搬移,最後並行驗證。

> 📌 事後訂正：規格中提到的 `db_helpers.go` 實際不存在（git 歷史查無此檔）；那些 live free-function 一直在 `pkg/database/jsondb.go`，B3 執行時也確實留在 `pkg/database`，結論不受影響。

> **B 區順序建議**:B1(ROI 最高、解四處同步)→ B2(獨立、低耦合)→ B3(搬 package、測試面最大)。三者互不阻塞但都動 Go,逐一做、各自驗證閘綠再進下一個。

---

# C 區 — 不建議現在硬做(白話說明)

## C1 — §7.1 的「sibling SQLite 路徑」反直覺(坑 #2)

**現況**:你下 `-data-dir data/json_db`,SQLite 不是放在 `data/json_db/db.sqlite`,而是放在它**旁邊**的 `data/db.sqlite`。第一次看一定覺得怪。

**為什麼怪**:因為這個資料夾的名字 `json_db` 是**舊時代留下的**——以前資料庫就是那個資料夾裡的 JSON 檔。遷移到 SQLite 後,為了不打架,SQLite 就放隔壁。名字沒改,所以規則看起來「反直覺」。

**為什麼暫時不清**:要把它變乾淨(讓路徑規則一致、直覺),你得同時做三件事:
1. 改 CLI 預設資料夾名(例如改成 `-data-dir data`,SQLite 就自然在 `data/db.sqlite`);
2. 改 Python 端 `go_cli.py` 送的預設值(它現在送 `data/json_db`);
3. **幫所有「已經有舊資料夾佈局」的安裝寫一個搬遷**——這是會動到**使用者真實資料**的破壞性變更。

換句話說:**收益只是「看起來比較整齊」,代價卻是可能搞壞別人現有的資料庫位置**。而且現在這個規則是**有測試鎖死、能正常運作**的。拿真實資料去冒險換一個純美觀的好處,不划算。

**正確的做法**:把它在文件講清楚(已在 `ARCHITECTURE.md` §5 / §7 標明「反直覺、預設走 sibling」),讓人不會踩。真要清,等未來有一個更大的「v4 資料佈局調整」時**順手一起做、一起寫搬遷**,而不是現在單獨為它冒險。

## C2 — Wails backend 是「獨立 go module」(坑 #4)

**現況**:`wails-app/` 有自己的 `go.mod`,跟主專案是兩個 module(靠 `replace` 互通)。所以你在根目錄跑 `go test ./...` **不會**測到 wails;改 wails 的 bound method 還要重新產生 bindings。

**為什麼這樣**:這**不是亂設計,是 Wails 框架本來就這樣**。Wails 專案天生就是「一個獨立 module + 自己的前端建置工具鏈(npm/vite)」。它跟主 module 的職責本來就該分開——一個是 GUI 殼,一個是核心邏輯。

**為什麼暫時不清(其實是「不該清」)**:如果硬把它合併進主 module(只為了「只有一個 go.mod 比較乾淨」),你會**跟框架對著幹**:很可能搞壞 `wails build`(它預期那個 module 結構),而換來的好處幾乎是零。這不是「髒邊界」,這是**框架本來就有的、正確的邊界**。

**真正的痛點其實很小**:就是「容易忘記跑 wails 的測試」。這個用**一行統一測試腳本**就解決了——正是 A 區的 **A2(`scripts/verify.ps1`)**,它會把 root 跟 wails 的測試一起跑掉。所以這個坑不需要重構,**A2 做完就等於補起來了**。

---

## 總結

| 區 | 項目 | 風險 | 並行 |
|---|---|---|---|
| **A 馬上做** | A1 deadcode 腳本、A2 verify 腳本、A3 fixture 污染 | 低(不碰生產邏輯) | ✅ 一批並行 |
| **B 值得做** | B1 DTO 收斂、B2 結構化 not-found、B3 fixture 移 package | 中(動生產碼,有測試保護) | ❌ 逐一序列 |
| **C 不硬做** | §7.1 sibling、wails 獨立 module | — | 文件化即正解;§7.1 等 v4 佈局再做,wails 痛點由 A2 補起 |

> 建議節奏:先一個 workflow 把 **A 區**清掉(快、純收益),其中 **A2 順便補掉 C2 的痛點**;再依 **B1 → B2 → B3** 各開一個 `/goal` 逐一做。C 區維持文件化、不動。
