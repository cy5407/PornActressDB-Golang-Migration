# PornActressDB-Golang-Migration Review Notes

審查模式：分批閱讀核心程式碼，不只看 README。  
開始時間：2026-03-20 23:23 CST  
目前進度：批次 6（已完成，含剩餘 tests 補讀） / 6

---

## 閱讀計畫

### 批次 1：入口與架構骨幹
已讀：
- `run.py`
- `cmd/scanner/main.go`
- `src/services/go_bridge.py`
- `src/models/go_accelerated_db.py`
- `src/models/go_accelerated_studio.py`

目的：
- 釐清 Python / Go 之間的橋接方式
- 找出主流程與 migration 邊界
- 先抓架構風險與顯性 bug

### 批次 2：Go 核心模組
待讀：
- `pkg/database/*`
- `pkg/extractor/*`
- `pkg/studio/*`
- `pkg/mover/*`
- `pkg/cache/*`

### 批次 3：Python 資料層與模型
待讀：
- `src/models/json_database.py`
- `src/models/incremental_json_database.py`
- `src/models/extractor.py`
- `src/models/studio.py`
- `src/models/json_types.py`
- `src/models/config.py`

### 批次 4：服務層與業務流程
待讀：
- `src/services/classifier_core.py`
- `src/services/studio_classifier.py`
- `src/services/interactive_classifier.py`
- `src/services/safe_searcher.py`
- `src/services/safe_javdb_searcher.py`
- `src/services/web_searcher.py`
- `src/services/unified_cache.py`

### 批次 5：Scraper 與工具層
待讀：
- `src/scrapers/**/*`
- `src/utils/*`

### 批次 6：測試與整體品質
待讀：
- `tests/*`
- Go tests
- integration / verify tools

---

## 批次 1 結論

### 已理解的架構
這個 repo 不是純 Go 重寫，而是：
- Python 仍然是主系統 / GUI / 大部分業務流程
- Go 提供 CLI 加速模組
- Python 透過 `subprocess` 呼叫 Go CLI
- Python 端再封裝成：
  - `GoAcceleratedDB`
  - `GoAcceleratedStudioIdentifier`

這代表 migration 路線是：

> Python 主體 + Go CLI 加速關鍵路徑

這個方向本身合理，而且比一次性全重寫風險低。

---

## 批次 1 優點

### 1. 遷移策略務實
- Go 優先
- 失敗 fallback 到 Python
- 盡量維持原 Python API

### 2. Go CLI 對外命令面清楚
`cmd/scanner/main.go` 目前已切出：
- `scan`
- `move`
- `history`
- `db`
- `identify`
- `cache`

### 3. Python bridge 有考慮相容性
`go_bridge.py` 中有：
- `_parse_json_from_output()` 支援混合輸出抓 JSON
- `list_operations()` 支援舊版表格輸出
- dataclass 包裝結果

---

## 批次 1 問題與風險

### 問題 1：`run.py` 的 Tk root 建立方式不夠乾淨
目前流程：
1. `root = tk.Tk()`
2. 若有 `ttkbootstrap` 再改成 `style.master`

風險：
- 可能出現多餘 root instance
- 初始化邏輯不乾淨
- 某些平台可能有 GUI 副作用

建議：
- root 建立邏輯做成二選一，不要先建再換

---

### 問題 2：`run.py` 直接改 `sys.path`，而且是雙重插入
目前同時插入：
- `src`
- 專案根目錄

風險：
- import 行為依賴啟動位置
- namespace 混亂
- 測試 / packaging / IDE 行為不一致

判斷：
- 這是技術債，不一定立刻出錯，但長期維護會痛

---

### 問題 3：`go_bridge.py` 的 `db_*` 系列參數順序有 bug 風險
Python 端類似這樣傳：
- `db get CODE -data-dir xxx`

但 Go 端 `dbCmd()` 先做：
- `fs.Parse(args[1:])`
- 再讀 `fs.Args()`

在 Go `flag` 的慣例下，第一個非 flag 之後後面的 flag 可能不會如預期解析。

#### 可能受影響的函式
- `db_get_video`
- `db_update_video`
- `db_delete_video`
- `db_list_videos`
- `db_get_stats`
- `db_compact_journal`

#### 目前判斷
這是本批次最優先的功能正確性風險。

---

### 問題 4：`go_bridge.py` 有過度吞錯的情況
不少 helper 在 `except Exception` 後直接：
- log error
- 回傳 `None` / `[]` / `{}` / fallback 值

風險：
- bridge bug 被掩蓋
- 參數錯誤和資料不存在混在一起
- 除錯成本上升

建議：
- 區分業務失敗、橋接故障、解析失敗三種錯誤

---

### 問題 5：`GoAcceleratedDB` 的快取一致性策略偏脆弱
目前模式：
- Go 更新成功後
- Python 手動同步 `self._python_db.base_db.data["videos"]`

風險：
- Go 寫入格式改變時容易不同步
- journal / compact 後狀態可能不一致
- 多執行緒 / 多程序情境下風險更高

判斷：
- 這是設計風險點，未必立刻爆，但需要後續確認

---

### 問題 6：`add_video()` 註解與 Go 真實語義可能不一致
Python 註解寫：
- `db update` 可以在不存在時自動建立

但要等讀 Go database 實作後才能確認是否屬實。

目前狀態：
- 標記為待驗證

---

### 問題 7：`cmd/scanner/main.go` 開始有膨脹跡象
目前已同時承擔：
- command router
- flag parser
- business glue
- output formatter
- 部分錯誤處理

目前還可讀，但如果繼續長，之後會變維護壓力點。

---

## 批次 1 暫時結論

### 架構方向是對的
- Python 主體 + Go 加速
- 有 fallback
- 有 bridge
- 有 CLI

### 但混合架構已出現常見風險
尤其是：
- 參數解析一致性
- Python/Go 狀態同步
- 錯誤處理邊界
- 啟動 / import 技術債

### 本批最重要問題
> `go_bridge.py` 的 `db_*` 自訂 `data_dir` 參數傳法，很可能有實際 bug。

---

## 批次 2（子區塊：pkg/database）

### 已讀
- `pkg/database/types.go`
- `pkg/database/jsondb.go`
- `pkg/database/journal.go`
- `pkg/database/jsondb_test.go`

### 這一輪確認到的事
- `db update` 在 Go 端**確實允許不存在時自動建立**，因為 `UpdateVideo()` 會在不存在時走 `OpAdd`
- 所以前一批在 `GoAcceleratedDB.add_video()` 中的註解，**方向上是對的**，不是空口假設
- Go 端資料庫設計是：
  - `data.json` 主資料
  - `data.journal` 增量日誌
  - `data.index` dirty tracking
- journal 會在每次 append 後 `f.Sync()`，偏保守，資料安全性優先於寫入效能

### 這一輪發現的問題

#### 問題 A：journal 重放與完整資料寫入的語義不一致
`UpdateVideo()` 寫入 journal 時，會把**整個 video 物件**當成 `data` 寫進去。

但 `loadJournal()` 在重放 `OpUpdate` 時，走的是：
- `applyVideoJournalEntry()`
- `json.Unmarshal(entry.Data, &updates)` 到 `map[string]any`
- `applyVideoUpdates(existing, updates)`

也就是說：
- 寫入時像「完整物件更新」
- 重放時像「部分欄位 patch」

這雖然目前大多數欄位能對上，但語義不乾淨，也容易出現：
- 某些欄位沒被 `applyVideoUpdates()` 支援時，journal replay 會靜默漏欄位
- 完整資料與 patch 資料混用，長期很難保證一致性

#### 問題 B：`applyVideoUpdates()` 欄位覆蓋不完整
目前只處理部分欄位，例如：
- `title`
- `studio`
- `release_date`
- `url`
- `actresses`
- `search_status`
- `original_filename`
- `file_path`
- `search_method`
- `test_field`

但 `VideoData` 其實還有：
- `id`
- `code`
- `created_at`
- `updated_at`
- `metadata`

這代表如果 journal 裡有這些欄位，replay 時可能不會被正確還原。

#### 問題 C：`BatchUpdate()` 的 journal operation 大小寫不一致
主系統常數使用：
- `OpAdd = "ADD"`
- `OpUpdate = "UPDATE"`
- `OpDelete = "DELETE"`

但 `BatchUpdate()` 呼叫的是：
- `appendJournal("update", code, video)`

雖然 `appendJournal()` 內部會轉成 `OpUpdate`，所以目前功能上還能跑，
但這顯示這一層 API 還存在舊/新格式混用痕跡，語義不夠一致。

#### 問題 D：`DeleteVideo()` 對 dirty tracking 的處理可疑
刪除成功後目前做的是：
- `delete(db.dirtyVideos, code)`
- `db.journalSize++`

這會造成一個語義問題：
- 資料被刪除了，但 dirty set 卻把 key 移除
- 如果 dirty tracking 的用途是表示「有哪些變更尚未 compact 到主檔」，那刪除其實也應該是一種 dirty 狀態

目前因為 delete journal 還在，所以功能未必立刻壞掉；但 dirty index 的意義已經不夠一致。

#### 問題 E：`MergeFromFile()` 只更新 dirty/index，不寫 journal
`MergeFromFile()` 會直接改 memory + dirty set + `journalSize`，但不寫 journal。

這代表：
- dirty/index 與 journal 之間的語義被拆開
- `journalSize` 不再等於 journal 真實條數
- 後續 `GetJournalEntryCount()` 和 `db.journalSize` 可能出現認知落差

這是我目前看到最明顯的資料一致性問題之一。

#### 問題 F：測試覆蓋偏功能 happy path，對一致性風險保護不夠
現有 `jsondb_test.go` 有測：
- CRUD
- save/load
- journal count
- compact
- merge

但還沒看到針對下面這些風險的測試：
- journal replay 後欄位是否完整一致
- merge 後 `journalSize` 與實際 journal 檔內容是否一致
- delete 後 dirty tracking 是否符合設計預期
- `UpdateVideo` / `UpdateVideoFields` 混用時 replay 是否一致

### 這一輪的修正/確認
- 前一批標記的「`db update` 是否真的能新增」已確認：**可以**

---

## 批次 2（子區塊：pkg/extractor + pkg/studio）

### 已讀
- `pkg/extractor/extractor.go`
- `pkg/extractor/extractor_test.go`
- `pkg/studio/identifier.go`
- `pkg/studio/identifier_test.go`

### 這一輪確認到的事
- extractor 的基本方向清楚：
  - 先清 filename 雜訊
  - 再跑多組 pattern
  - 最後 normalize + validate
- studio identifier 的基本方向也合理：
  - `studios.json` 規則
  - alias 對照
  - `major_studios.json` 後備
  - 反向 prefix map
- 測試至少有覆蓋：
  - 常見番號格式
  - alias normalize
  - major studio
  - 載入規則檔

### 這一輪發現的問題

#### 問題 G：extractor 的 pattern 優先順序可能導致誤抽或過早命中
目前 pattern 依序包含：
- `([A-Z]{2,6}-\d{3,5})`
- `([A-Z]{2,6}-\d{3,5})[A-Z]*`
- `([A-Z]{2,6}\d{3,5})`
- `([A-Z]{2,6}[._]\d{3,5})`
- `(\d{6}[-_]\d{3})`

其中前兩條其實重疊很高，且採 `FindStringSubmatch()` 會先命中局部片段。這可能造成：
- 某些帶尾碼的檔名只抓到前半，但不是因為設計清楚，而是剛好先撞到
- 未來擴充 pattern 時容易出現優先順序副作用

目前功能上未必錯，但正則策略偏脆弱。

#### 問題 H：`cleanFilename()` 的清洗規則是硬編碼且不可配置
像：
- `hhd800.com@`
- `xxx.com-`
- `1080p / 4K / HDR / HEVC / AVC / X264 / X265`
- `-C` / `CH`

這些規則對當前資料集可能有效，但長期來看：
- 規則來源不透明
- 增修得改程式碼
- 很難和 Python 端規則保持一致

這是典型「隨資料成長會膨脹」的區域。

#### 問題 I：extractor 的 skip 規則對 FC2/PPV 很明確，但對其他噪音/站點格式保護不足
現在對 FC2/PPV 有專門 skip，這很好。
但對其他常見非目標來源，目前比較依賴：
- 清洗後剛好沒 match
- 或 validate 擋掉

這種作法在資料集變雜時，容易出現 false positive。

#### 問題 J：studio identifier 的 prefix 抽取過於簡化
`IdentifyStudio()` 目前用：
- `^([A-Z]+)`

這代表它只取開頭連續英文字母。
雖然對多數 `SSIS-001`、`MIDV-456` 沒問題，
但對更複雜或未來可能出現的格式：
- 前面帶站點前綴
- 特殊符號
- 異常清洗結果
可能就太脆弱。

也就是說，studio 辨識其實高度依賴 extractor / 前置清洗已經做對。

#### 問題 K：`NormalizeStudioName()` 將「番號判斷優先」寫死，可能蓋掉外部來源較準確的 studio 名稱
現在邏輯是：
- 只要有 `videoCode`
- 先用 code 判 studio
- 若判得出來，就直接回傳，不再尊重傳入 `studioName`

這在多數情況下有助於標準化，
但如果外部 scraper 的 `studioName` 其實更準，而 prefix map 過期或不完整，就可能被錯誤覆蓋。

這不是一定錯，但屬於策略上偏強勢的決策，建議至少文件化或讓呼叫端能選擇策略。

#### 問題 L：`loadRules()` / `loadMajorStudios()` 的路徑搜尋策略方便，但可預測性差
目前會試：
- 當前檔案
- `.`
- `..`
- `../..`

這在桌面程式/打包場景確實方便，
但也代表：
- 啟動位置不同，實際載入的規則檔可能不同
- debug 時較難一眼判斷到底吃的是哪份規則

這和第一批 `sys.path` 技術債屬於同一類：
- 為了方便而犧牲可預測性。

#### 問題 M：測試雖有基本覆蓋，但缺少「錯誤案例導向」測試
目前 extractor/studio tests 偏向：
- 正常格式能抓到
- 預期 alias 能對到

但還沒看到夠多的：
- 容易誤判的檔名
- 清洗過頭的檔名
- 多重 pattern 衝突
- prefix map 與外部 studio name 衝突時的行為

這表示目前測試比較像驗證 happy path，對回歸保護還不夠。

### 這一輪暫時結論
- `pkg/extractor` / `pkg/studio` 的核心思路是清楚可維護的
- 但很多規則是「經驗型硬編碼」
- 當資料集或來源變雜時，這兩塊很可能成為誤判熱區

---

## 批次 2（子區塊：pkg/mover + pkg/cache）

### 已讀
- `pkg/mover/mover.go`
- `pkg/mover/mover_test.go`
- `pkg/cache/cache.go`
- `pkg/cache/types.go`
- `pkg/cache/cache_test.go`

### 這一輪確認到的事
- `mover` 的功能面算完整：
  - 單檔移動
  - 目錄移動
  - 批次移動
  - operation log
  - rollback
- `cache` 端已經有一個不錯的方向：
  - `AutoCleanup()` 用單次 index 讀寫避免原本兩次處理的 TOCTOU 問題
  - stats / prune / clear 的職責分離清楚
- tests 至少有覆蓋：
  - 基本 move/rollback
  - cache stats / expired cleanup / size cleanup / min keep

### 這一輪發現的問題

#### 問題 N：`MoveFile()` 的 overwrite 路徑存在資料遺失風險
現在 `Overwrite` 的流程是：
1. 先刪除目標檔案
2. 再嘗試 `os.Rename(src, dst)`
3. 失敗後才改用 copy+remove

風險：
- 如果刪掉目標後，rename/copy 失敗
- 你會同時失去原本目標檔案與預期的新結果

這是典型非原子 overwrite 問題。對檔案整理工具來說，這是比一般風格問題更嚴重的資料安全風險。

#### 問題 O：`Rollback()` 預設使用 `Skip`，可能讓回滾變成不完整但表面成功
rollback 建立反向 MoveItem 時固定：
- `OnConflict: Skip`

這代表如果原位置已經被其他東西佔住：
- 回滾會跳過
- 但整體 result 仍可能部分成功
- 使用者若沒仔細看細節，很容易誤以為已完整回滾

建議至少：
- 讓 rollback 衝突策略可配置
- 或在 rollback summary 中強烈標出「未完全還原」

#### 問題 P：`MoveDir()` 成功條件偏寬鬆，對來源刪除狀態表達不足
`MoveDir()` 的 `Success` 只看：
- `len(result.Errors) == 0`

但來源目錄是否真的刪除，另外放在：
- `DeletedSrc`

這代表：
- 所有檔案都搬完，但來源目錄沒刪掉時
- API 還是會顯示 success=true

這不一定錯，但語義上比較模糊；呼叫端如果只看 success，可能高估結果完整性。

#### 問題 Q：`MoveFile()` / `MoveDir()` 的 context 目前是名義支援，實際沒接取消點
`BatchMove(ctx, items)` / `AutoCleanup(ctx, config)` 都收了 context，
但目前實作基本上沒有中途檢查 `ctx.Done()`。

這不是 bug，但屬於：
- API 承諾比實作大
- 未來若外部以為可取消，會有認知落差

#### 問題 R：`copyFile()` 有資料保護意識，但還是缺少更穩的同目錄暫存覆蓋策略
優點是：
- copy 失敗會清理殘檔
- `Sync()` 和 `Close()` error 都有顧

但對 overwrite 情境來說，真正穩妥的做法通常是：
- 先寫到暫存檔
- 驗證成功
- 再原子 replace

目前 mover 沒走這條，所以 overwrite 風險仍在。

#### 問題 S：cache 的過期判斷同時看 `CreatedAt` 和 `TTLDays`，與 `TTLSeconds` 欄位語意分裂
`IndexEntry` 本身有：
- `TTLSeconds`

但 `CleanupExpired()` / `AutoCleanup()` 用的是：
- `config.TTLDays`
- 然後拿 `CreatedAt` 算全域 TTL

這代表：
- 單筆 entry 自帶的 TTL 沒被真正尊重
- stats 和 cleanup 的過期語義不完全一致

這會導致：
- 某些 entry 在 stats 看起來過期
- 但 cleanup 是否刪除又取決於外部 config

#### 問題 T：cache 的索引更新沒有原子寫入保護
`saveIndex()` 目前直接：
- `os.WriteFile(cm.indexPath, data, 0644)`

和 database 的 `saveUnsafe()` 相比，少了：
- tmp file
- rename replace

風險：
- 若寫入中斷，可能留下半寫入 index
- index 受損時 cleanup/stats 都會受影響

這是一個很具體、可修的可靠性問題。

#### 問題 U：cache tests 偏邏輯驗證，對真實檔案系統失敗情境保護不足
目前有測：
- 正常清理
- dry run
- min keep
- size cleanup

但還缺：
- 刪檔失敗時 index 是否仍一致
- index 損壞時行為
- `AutoCleanup()` 在同時 TTL + size 清理時的結果正確性
- `saveIndex()` 寫壞時的保護

### 這一輪暫時結論
- `pkg/mover` / `pkg/cache` 的功能面做得比我原本預期完整
- 但 mover 在 overwrite / rollback 的資料安全語義上還不夠保守
- cache 則存在 TTL 語義分裂與 index 原子性不足問題

---

## 批次 3（子區塊：json_database + incremental_json_database）

### 已讀
- `src/models/json_database.py`
- `src/models/incremental_json_database.py`

### 這一輪確認到的事
- 很多我在 Go 端看到的設計，其實不是憑空冒出來，而是有明顯 Python 前身：
  - `data.json + data.journal + data.index`
  - dirty tracking
  - compact threshold
  - `db update` / partial update / append-only journal
- 也就是說：
  - **有些問題是 migration 時沿用原設計**
  - 不一定全是 Go 新引入的問題
- `JSONDBManager` 與 `IncrementalJSONDB` 的責任邊界大致清楚：
  - `JSONDBManager`：完整 JSON 檔 + 驗證 + backup + stats
  - `IncrementalJSONDB`：增量 journal 寫入 + replay + compact

### 這一輪發現的問題

#### 問題 V：`JSONDBManager` 的讀寫鎖模型其實不是真正的多讀單寫
它同時建立：
- `self.read_lock = FileLock(str(lock_file), ...)`
- `self.write_lock = FileLock(str(lock_file), ...)`

但兩者其實鎖的是**同一個 lock file**。
也就是說：
- 名字上分成 read/write lock
- 實際上仍然是同一把互斥鎖

所以註解裡寫的「允許多個讀操作並行執行」在實作上並不成立。
這是設計描述與真實行為不一致。

#### 問題 W：`_release_locks()` 可能釋放到不屬於當前操作語境的鎖
由於整個物件共用同一組 `read_lock` / `write_lock` 狀態，
而且很多 public method 都會：
- acquire
- `finally: self._release_locks()`

這種設計雖然大多數時候能跑，
但把「釋放所有鎖」做成統一出口，讓語義偏粗。
如果未來方法巢狀呼叫或鎖策略擴張，很容易出現難追的副作用。

#### 問題 X：`IncrementalJSONDB` replay 邏輯本身就存在和 Go 類似的語義問題
Python 端：
- `update_video()` 寫入 journal 時只記錄 `updates` patch
- `add_video()` 寫完整物件

這比 Go 端其實還乾淨一點。
但 replay 時 `_apply_entry_to_memory()` 仍直接：
- `video.update(entry.data)`

也就是說 replay 完全信任 patch 結構，
沒有額外 schema/欄位驗證。

所以我在 Go 看到的 journal replay 一致性問題，
有一部分其實是來自 Python 增量模型本身的寬鬆設計。

#### 問題 Y：`IncrementalJSONDB` 對 memory 與 disk 的一致性保證偏弱
每次 `update_video()` / `add_video()` / `delete_video()` 都是：
1. append journal
2. 立即更新 `base_db.data`

這讓讀取很快，但代價是：
- 記憶體是即時狀態
- 主檔 `data.json` 是延後 compact 才一致

如果外部有人直接讀主檔、跳過 journal，看到的就不是最新狀態。
這不一定是 bug，但要很明確文件化；不然使用者容易誤以為 `data.json` 永遠是最新真相。

#### 問題 Z：`JSONDBManager` 裡混了太多責任
目前這個 class 同時管：
- 檔案初始化
- lock
- JSON 驗證
- referential integrity
- 統計快取
- 備份 / 還原
- CRUD
- 分析邏輯

這個類別已經非常肥。
這會導致：
- 測試切割困難
- 任何修改都容易牽動太多區域
- migration 到 Go 時也不容易只挑乾淨子模組搬

#### 問題 AA：`analyze_actress_primary_studio()` 明顯屬於業務規則，但放在資料庫管理器中
這不是純資料層操作，
而是高度業務判斷：
- 專屬女優
- 高忠誠度女優
- 跨片商女優
- 推薦分類

把這種邏輯放在 DB manager 裡，會讓資料層與業務層耦合過深。
這也解釋了為什麼後續 service/model 邊界可能會看起來不夠乾淨。

#### 問題 AB：`JSONDBManager` 的 `_save_all_data()` 雖然有原子寫入意識，但做法對某些同步雲端環境仍偏脆弱
它目前的邏輯是：
- 先寫 `.tmp`
- 若原檔存在，先 `unlink()` 原檔
- 再 `rename()` temp 到正式檔

這在一般情況可行，
但在 OneDrive / 雲同步 / 防毒干預下，先刪原檔再 rename 的窗口仍可能出現：
- 原檔已刪
- temp 尚未成功 replace

你有做 retry，這是加分；
但嚴格說，這還不是最穩的 replace 模式。

#### 問題 AC：`IncrementalJSONDB` 的 `compact()` 直接呼叫 `self.base_db._save_all_data()`，表示抽象邊界已被打穿
這代表：
- `IncrementalJSONDB` 不只是用 `JSONDBManager`
- 它直接依賴 `JSONDBManager` 的 internal method

這讓兩個 class 雖然表面分層，實際上仍然是強耦合。
之後只要 `_save_all_data()` 行為變動，incremental layer 就會被連帶影響。

### 這一輪暫時結論
- Python 原始資料層本身就有不少設計債
- Go migration 有些問題是在延續原本架構，而不是 Go 單獨造成
- 尤其是：
  - journal / main file 的雙層真相
  - class 責任過重
  - 邊界穿透
  - lock 語義和文件不一致

---

## 批次 3（子區塊：python extractor + studio）

### 已讀
- `src/models/extractor.py`
- `src/models/studio.py`

### 這一輪確認到的事
- Go 版 extractor / studio 的很多邏輯，確實是從 Python 版直接繼承或簡化而來：
  - pattern 順序
  - skip FC2/PPV
  - 清洗站點/品質標記
  - prefix-based studio mapping
  - `video_code` 優先的 studio normalize
- 也就是說：
  - Go 端不是平白變脆弱
  - 而是 Python 原版本來就帶著「規則型、經驗型硬編碼」的特性

### 這一輪發現的問題

#### 問題 AD：`src/models/extractor.py` 內有明顯重複定義 `_should_skip_file()`
這個檔案裡 `_should_skip_file()` 出現了**兩次**，而且內容幾乎相同。

這代表：
- 後面的定義會覆蓋前面的定義
- 表面上不一定立刻壞
- 但這是很明顯的維護疏漏

這類問題也說明這個模組目前缺少更嚴格的 lint / code review 保護。

#### 問題 AE：`code_patterns` 區塊看起來有疑似註解/字串殘留的可讀性問題
這段：
- `# 處理 STARS_707, STARS.707            (r'(\d{6}[-_]\d{3})', '數字格式')`

看起來像是註解與 pattern 列表在歷次修改時混在一起，雖然目前檔案還能 parse，
但可讀性很差，也提高未來改動時出錯的風險。

#### 問題 AF：Python extractor 和 Go extractor 的脆弱點本質一致
像這些問題在 Python 版就已存在：
- pattern 彼此重疊
- 清洗規則硬編碼
- skip 規則偏針對已知案例
- 對來源變雜時容易 false positive / false negative

所以我先前在 Go extractor 標的風險，大多不是 migration 新增，而是延續既有策略。

#### 問題 AG：`skip_prefixes` 屬性定義了，但實際沒被使用
`UnifiedCodeExtractor.__init__()` 裡有：
- `self.skip_prefixes = [...]`

但真正判斷跳過時，用的是 `_should_skip_file()` 內部自己寫的 regex / marker。

這表示：
- 有死資料結構
- 設計意圖和實作脫節
- 以後有人改 `skip_prefixes` 會誤以為有生效

#### 問題 AH：Python `StudioIdentifier._load_rules()` 的預設 fallback 比 Go 版更隱性
Python 版在找不到 `rules_file` 時，會：
- 直接建立預設 `studios.json`

這和 Go 版「載入失敗就用預設 in-memory 規則」不同。

風險是：
- 執行環境會被程式靜默改寫
- 第一次啟動就產生檔案副作用
- 在某些環境下可能讓人誤解規則來源

這不是一定錯，但從可預測性角度，我會偏保守看待。

#### 問題 AI：Python `StudioIdentifier` 的路徑處理比 Go 簡單，但也更依賴 cwd
它直接：
- `self.rules_file = Path(rules_file)`
- 然後檢查 exists / open

這代表它沒有像 Go 那樣亂試多層目錄，這點反而比較單純；
但代價是：
- 更依賴目前工作目錄
- 打包/不同啟動方式下，規則檔可發現性未必穩

也就是：
- Go 版是方便但不可預測
- Python 版是直接但更依賴 runtime cwd

兩邊各有問題。

#### 問題 AJ：Python `StudioIdentifier` 的 alias / code map 也是明顯的經驗型規則堆疊
不論是：
- 日文名稱
- 英文大小寫變體
- FALENO / Premium 等別名

本質上都還是硬編碼知識。
這在實務上常常有效，但長期要維護時：
- 需要一套明確來源
- 需要測試保護
- 需要和 JSON 規則檔邊界分清楚

目前 alias 與規則檔責任邊界並不完全清楚。

### 這一輪暫時結論
- Python extractor / studio 證實了：
  - Go 端多數規則脆弱點其實是繼承而來
  - migration 比較像把既有規則系統搬過去，不是重新設計
- 同時也抓到一個很具體的維護問題：
  - `_should_skip_file()` 重複定義

---

## 批次 3（子區塊：json_types + config）

### 已讀
- `src/models/json_types.py`
- `src/models/config.py`

### 這一輪確認到的事
- `json_types.py` 很明確是整個 Python 資料層的 schema/常數核心：
  - TypedDict
  - error types
  - schema version
  - defaults
- `config.py` 則承接了大量執行期行為：
  - 路徑設定
  - search/cache/go integration
  - user preference
  - studio classification 偏好
- 這兩個檔案補完後，批次 3 可以算完成，對 Python models 層的骨架理解已經足夠。

### 這一輪發現的問題

#### 問題 AK：`json_types.py` 的型別定義和實際統計結構已有明顯漂移
例如 `StatisticsDict` 定義的是：
- `actress_stats`
- `studio_stats`
- `cross_stats`
- `last_computed`

但 `JSONDBManager._compute_statistics()` 實際產出的鍵是：
- `actress_statistics`
- `studio_statistics`
- `enhanced_actress_studio_statistics`
- `computed_at`

這表示：
- 型別定義已經落後於實作
- TypedDict 在這裡更多只是文件，不是真正可信的契約

這是很重要的訊號：
**型別檔不能再被當成真相來源。**

#### 問題 AL：`json_types.py` 的 `TypedDict(total=False)` 全面採寬鬆模式，降低了型別保護價值
幾乎所有核心型別都 `total=False`，代表：
- 大量欄位其實都是 optional
- 靜態檢查對缺欄位幫助有限
- 更接近「描述大概會長這樣」而不是嚴格 schema

對快速迭代專案來說可以理解，
但對你這種資料模型複雜、還在 migration 的系統來說，會放大 drift 問題。

#### 問題 AM：`VIDEO_ALLOWED_FIELDS`、`SEARCH_STATUSES`、`SEARCH_METHODS` 這類常數集中是好事，但目前沒看出強制一致性的機制
也就是說：
- 有常數定義
- 但實作不一定都真的引用它們

例如前面已經看到一些地方直接寫字串、直接 patch 欄位、或統計鍵名自己長一套。
這表示：
- 常數層有在整理
- 但尚未成為真正的單一真相來源（single source of truth）

#### 問題 AN：`ConfigManager.load_config()` 有隱性副作用：讀設定時就可能寫設定檔
流程是：
- 讀 config
- 補 defaults
- 若缺項就 `save_config()`
- `_normalize_path_settings()` 可能再存一次
- `_validate_config()` 可能再存一次

也就是 `__init__()` 期間，單純讀設定就可能伴隨多次寫檔。

這在桌面工具上常見，但也會帶來：
- 啟動即修改環境
- 設定檔 diff 噪音
- 某些只讀/同步環境下的不必要風險

#### 問題 AO：`ConfigManager` 的責任也偏肥
它不只做：
- ini 設定讀寫
- 驗證
- 路徑標準化

還把：
- go integration
- search tuning
- cache policy
- database path
都集中在同一個 manager。

這本身不一定錯，但和前面 `JSONDBManager` 一樣，有「中心化過胖」傾向。

#### 問題 AP：`PreferenceManager` 把偏好、分類策略、片商分類門檻、資料夾命名混在同一份 JSON，會讓設定邊界變模糊
這代表 user preference 檔同時承載：
- 個人偏好
- collaboration choice memory
- studio classification policy
- backup/move policy

長期看會有兩個問題：
- 使用者偏好 vs 系統策略的邊界不清楚
- 日後如果要分權或做 UI，這份檔案會越來越難管

#### 問題 AQ：路徑標準化採用 `Path(...).as_posix()`，跨平台一致性好，但也可能在某些 Windows 相依情境下造成心理落差
這不一定是 bug，
但它是一種明確的產品選擇：
- 內部統一 POSIX 風格

這有利於一致性，
但若其他模組/使用者預期維持原始 Windows path 表現，可能需要更清楚的文件說明。

### 這一輪暫時結論
- `json_types.py` 揭露出一個很重要的問題：**型別/常數層和實作已出現漂移**
- `config.py` 則延續了整個專案的一個共通特徵：
  - 功能集中
  - 初始化就帶副作用
  - 實用但邊界不夠乾淨

### 本批次狀態
- **批次 3 已完成**

---

## 批次 4（子區塊：classifier_core + studio_classifier + interactive_classifier）

### 已讀
- `src/services/classifier_core.py`
- `src/services/studio_classifier.py`
- `src/services/interactive_classifier.py`

### 這一輪確認到的事
- service 層確實是整個系統真正把「models + search + move + GUI 互動」揉起來的地方。
- 也因此，前面 models 層的耦合問題，在這一層會被進一步放大。
- `UnifiedClassifierCore` 幾乎已經是 orchestration god object：
  - scan
  - search
  - persist
  - interactive move
  - studio classification
  - smart search-and-move
- 這也解釋了為什麼整個專案的真實複雜度主要不在單一模組，而在跨模組協作。

### 這一輪發現的問題

#### 問題 AR：`UnifiedClassifierCore` 明顯過胖，已經成為服務層的中心式巨物件
它目前同時掌管：
- config
- db manager
- code extractor
- scanner
- mover
- studio identifier
- web searcher
- interactive classifier
- studio classifier
- 多種 workflow (`process_and_search*`, `move_files`, `smart_search_and_move`)

這代表：
- 高度中心化
- 很難局部測試
- 任何一個依賴變動都容易牽動整個 core

#### 問題 AS：`UnifiedClassifierCore.__init__()` 直接硬編碼 `IncrementalJSONDB("data/json_db")`，忽略 config 內已有的 `json_data_dir`
這是很具體的問題。
前面 `ConfigManager` 明明有：
- `database.json_data_dir`

但 core 初始化時直接寫死：
- `IncrementalJSONDB("data/json_db")`

這代表：
- config 層已提供的彈性沒有真的被使用
- 測試、自訂資料目錄、部署彈性都被壓縮

#### 問題 AT：service 層充滿大量重複流程，尤其是「掃描 → 萃取 code → 查 DB → 搜尋 → persist」這條線重複很多次
像：
- `process_and_search`
- `process_and_search_japanese_sites`
- `process_and_search_javdb`
- `process_and_search_cascade`
- `smart_search_and_move`

雖然每條 workflow 有差異，但骨架高度重複。
這代表：
- 修一條流程時容易漏修其他條
- fallback / 統計 / persist 行為可能慢慢漂移

#### 問題 AU：`UnifiedClassifierCore` 的 import 風格顯示模組邊界仍不乾淨
這個檔案直接：
- `from models...`
- `from services...`
- `from utils...`

而不是全都走一致的 `src.` 路徑或 package 相對匯入。
這和前面 `run.py`/`sys.path` 問題是同一條線：
- 專案 package 結構仍然沒有完全收斂

#### 問題 AV：`get_actress_studio_distribution()` 是空實作 `pass`
這代表 service API 表面存在，實際未完成。
這種東西如果已暴露給其他層使用，之後很容易成為：
- 以為有功能
- 實際沒實作
的陷阱。

#### 問題 AW：`StudioClassificationCore` 內含大量硬編碼片商名單，而且和其他地方重複
像：
- `_scan_actress_folders()` 內的 `studio_folders`
- `_is_actress_folder()` 內另一份 `studio_folders`
- `_identify_major_studios()` 的大片商集合

這些名單：
- 重複
- 大小寫不完全一致
- 與 `StudioIdentifier` / 規則檔 / alias 邊界也不統一

這代表分類規則知識散落在：
- models/studio
- services/studio_classifier
- preferences/config
多個地方。

#### 問題 AX：`_scan_actress_folders()` 對被跳過資料夾的回報存在語義小 bug
它用 `skipped_by_parent` 收集所有因父資料夾被跳過的子資料夾，
但最後提示時只顯示單一 `parent_name`。

如果被跳過的資料夾其實來自不同父層，訊息就不精確。
這不是大 bug，但屬於典型回報邏輯瑕疵。

#### 問題 AY：`StudioClassificationCore._is_actress_folder()` 太重，而且混了資料判斷、命名規則、資料庫查詢、檔案掃描
這個方法目前在做：
- 排除片商資料夾
- 排除系統資料夾
- 排除番號樣式
- 查資料庫統計
- 檢查資料夾內是否有影片檔

這種方法太肥，會導致：
- 判斷路徑很難測
- 規則一改就容易影響大範圍
- logger/debug 很多，但策略仍不夠顯式

#### 問題 AZ：`InteractiveClassifier` 同時支援 GUI 與 console 互動，實用但把 UI 決策邏輯綁進 service flow
這不是一定錯，
但表示「分類決策引擎」和「具體互動介面」沒有完全分開。

較理想的分法通常是：
- decision service 給選項
- GUI / console adapter 各自處理顯示與輸入

現在這種寫法在小型工具很常見，但擴充性有限。

#### 問題 BA：`smart_search_and_move()` / `move_files()` / `interactive_move_files()` 的行為邊界容易重疊，使用者心智模型成本高
目前有很多相近但不完全相同的方法：
- 智慧分類
- 互動式移動
- 智慧搜尋並分類
- 多種搜尋模式

功能上很豐富，
但從架構看也反映出：
- workflow 已經開始分岔
- 若沒有更明確 command/use-case 分層，之後會越來越難維護

### 這一輪暫時結論
- service 層證實了整個系統的主要複雜度來源：
  - 不是單點演算法
  - 而是 workflow orchestration
- 目前最大的風險不是某個函式寫錯，而是：
  - 中心物件過胖
  - 重複流程太多
  - 規則知識散落
  - 邊界逐漸模糊

---

## 批次 4（子區塊：web_searcher + safe_searcher + safe_javdb_searcher + unified_cache）

### 已讀
- `src/services/web_searcher.py`
- `src/services/safe_searcher.py`
- `src/services/safe_javdb_searcher.py`
- `src/services/unified_cache.py`

### 這一輪確認到的事
- 搜尋/快取層是這個專案另一個高複雜度區域：
  - 多來源搜尋
  - 多層 fallback
  - AV-WIKI / chiba-f / JAVDB 不同節奏
  - 自製快取 + 統一快取 + 各來源專屬快取
- 這層做了很多「真的有實戰經驗才會補的東西」，像：
  - anti-block request pacing
  - header rotation
  - compression/encoding 補救
  - 分段批次搜尋
  - JAVDB 安全節流
- 但同時也讓責任分散、語義重疊的問題更明顯。

### 這一輪發現的問題

#### 問題 BB：`WebSearcher` 過胖，而且把太多不同層次的責任揉在一起
它目前同時負責：
- config 解析
- SafeSearcher 組態
- JAVDB 搜尋器整合
- AV-WIKI/chiba-f/JAVDB 的搜尋流程
- HTML 解析
- 壓縮/編碼修正
- studio normalize
- batch/search/cascade orchestration
- 快取整合

這已經不是單純 searcher，而是 search orchestrator + parser + transport workaround 集合體。

#### 問題 BC：搜尋方法命名與邊界已有重疊
像：
- `search_info`
- `search_japanese_sites_only`
- `search_japanese_sites`
- `search_javdb_only`
- `batch_search`
- `batch_search_avwiki_concurrent`
- `batch_cascade_search`
- `cascade_search_single`

功能上很豐富，
但命名和責任邊界開始有重疊，顯示搜尋策略是在演進中不斷疊加，而不是從統一抽象長出來。

#### 問題 BD：`search_cache`、`SafeSearcher.cache`、`SafeJAVDBSearcher.cache`、`UnifiedCacheManager` 之間存在多層快取語義重疊
目前至少有：
- `WebSearcher.search_cache`（memory）
- `SafeSearcher.cache`（JSON 檔）
- `SafeJAVDBSearcher.cache`（JSON 檔）
- `UnifiedCacheManager`（統一介面）

這不是完全錯，
但它表示：
- 快取層次很多
- cache hit / TTL / clear 的語義分散
- 「哪一層才是真正的快取控制中心」不夠明確

#### 問題 BE：`UnifiedCacheManager` 對各快取來源的介面假設過度樂觀
它的 `get/set/delete` 會假設 cache instance 可能有：
- `get`
- `set`
- `delete`
- `clear`
- `auto_cleanup`

但目前註冊進來的有些其實只是 dict 或自製物件，
並沒有真正一致的 protocol。

也就是說它比較像：
- best-effort adapter
而不是：
- 嚴格統一的 cache abstraction

這會讓後續擴充新 cache source 時，容易產生隱性不相容。

#### 問題 BF：`SafeSearcher.__del__()` / `SafeJAVDBSearcher.__del__()` 依賴析構保存資料，不夠可靠
兩邊都有在 `__del__()` 裡做：
- save cache
- save stats
- close session

這種寫法在 Python 中不能保證一定按預期執行，特別是：
- 解譯器退出
- 例外中止
- 循環引用
- 多執行緒

這不是說不能寫，但不該把持久化一致性寄託在析構函式上。

#### 問題 BG：`SafeJAVDBSearcher.safe_request()` 的重試與等待策略是實戰導向，但遞迴重試寫法可讀性與控制性一般
它現在用遞迴進行：
- timeout retry
- 403 retry
- 429 retry

而且夾雜長時間 sleep。
這在功能上可行，但長期看：
- 不如顯式 loop 容易維護
- 邏輯分支比較難 audit
- 測試也較不方便

#### 問題 BH：`WebSearcher` 內直接負責壓縮/編碼/HTML 修補，表示 transport 層和 parsing 層沒有分乾淨
像：
- `_handle_compression`
- `_force_decompress`
- `_detect_and_decode_content`
- `_is_valid_decoded_text`

這些本質更偏：
- HTTP content handling / transport workaround

但現在和：
- `_extract_studio_info`
- `_search_av_wiki`
- `_search_chiba_f_net`
混在同一個類別裡。

#### 問題 BI：`_get_studio_name_by_code()` 又另外讀一次 `studios.json`，規則來源進一步分散
現在片商知識來源至少分散在：
- `StudioIdentifier`
- `studios.json`
- `major_studios.json`
- `web_searcher` 內建 fallback mapping
- `studio_classifier` 硬編碼大片商名單

這讓「片商知識的單一真相來源」更加模糊。

#### 問題 BJ：`SafeSearcher` 與 `SafeJAVDBSearcher` 都有自己的 cache/stats/session/pacing，但沒有更上層的統一請求抽象
這代表目前系統是：
- 兩套相似但不完全一致的 anti-block request client

這在演進初期合理，
但如果還要擴更多來源，重複邏輯會繼續長。

#### 問題 BK：`UnifiedCacheManager.clear_all(confirm=True)` 有保險，但 `cleanup_all()` 對不同來源的清理語義仍不一致
有些來源：
- 真的支援 TTL/size cleanup
有些來源：
- 只是直接清掉 dict

所以它提供的是「統一入口」，但不是「統一行為」。
這點如果不在文件裡講清楚，使用者很容易高估它的統一性。

### 這一輪暫時結論
- 搜尋與快取層做了很多務實補強，顯示這專案不是紙上談兵
- 但也因此堆出了：
  - 更胖的 orchestrator
  - 多層快取重疊
  - 規則來源進一步分散
  - request client 重複演進

### 本批次狀態
- **批次 4 已完成**

---

## 批次 5（子區塊：scrapers core + source scrapers）

### 已讀
- `src/scrapers/base_scraper.py`
- `src/scrapers/unified_scraper.py`
- `src/scrapers/sources/avwiki_scraper.py`
- `src/scrapers/sources/chibaf_scraper.py`
- `src/scrapers/sources/javdb_scraper.py`

### 這一輪確認到的事
- scraper 層的存在證實了一件事：
  - 這個專案同時有「service 直接搜網站」和「較抽象的 scraper framework」兩條演化線並存。
- `BaseScraper` / `UnifiedWebScraper` 其實比前面 service 層更像一套乾淨的架構嘗試：
  - retry
  - health check
  - rate limiter
  - cache
  - source abstraction
- 但它目前和 `WebSearcher` / `SafeSearcher` / `SafeJAVDBSearcher` 沒有真正收斂成單一路線，顯示專案內有**兩套搜尋框架並行**。

### 這一輪發現的問題

#### 問題 BL：搜尋系統目前存在雙軌架構並行，且未完成收斂
一條是：
- `WebSearcher`
- `SafeSearcher`
- `SafeJAVDBSearcher`

另一條是：
- `BaseScraper`
- `UnifiedWebScraper`
- `AVWikiScraper` / `ChibaFScraper` / `JAVDBScraper`

這代表：
- 不是單純模組多
- 而是**兩套設計哲學同時存在**

這會直接拉高：
- 維護成本
- 使用者心智成本
- 新功能放哪邊的不確定性

#### 問題 BM：`BaseScraper` 很完整，但 `HealthChecker` 在 `__init__()` 直接 `asyncio.create_task()`，有事件迴圈依賴風險
`HealthChecker.__init__()` 內會在 `enable_auto_recovery=True` 時直接：
- `asyncio.create_task(health_check_worker())`

這在某些情境下可行，
但若初始化發生在沒有 running event loop 的上下文，就可能出問題。

也就是：
- 架構設計是好的
- 但生命週期管理仍偏鬆

#### 問題 BN：`BaseScraper` 和前面 service 搜尋層有大量功能重疊，顯示抽象邊界未落地
例如這些能力：
- rate limiting
- cache
- retry
- encoding handling
- health check
- source-specific parser

在 scraper 層已經有一套了；
但前面 `WebSearcher` / `SafeSearcher` 等也各自實作了類似概念。

這表示目前不是「底層抽象，上層複用」，
而是「兩邊都在長」。

#### 問題 BO：source scrapers 裡的 parsing/validate 規則與前面 service 層再次重複
像：
- 提取 actress
- studio code 推測
- valid actress name 過濾
- 搜尋頁 / 詳情頁切換
- AV-WIKI / JAVDB / CHIBA-F 站點專屬解析

這些邏輯在前面的 `WebSearcher` 其實也已經有另一套。

也就是說同一站點規則現在有**重複實作**，後續很容易出現：
- 一邊修了
- 另一邊沒修

#### 問題 BP：`AVWikiScraper._is_valid_actress_name()` 在 `return ActressNameFilter...` 之後還殘留大量永遠不會執行的舊邏輯
目前寫法是：
- 先 `return ActressNameFilter.is_valid_actress_name(name)`
- 後面還留著很長一段舊的垃圾文本過濾規則

這是明顯 dead code。
表示：
- 曾經重構過
- 但舊實作沒有真正清掉

這類殘留會讓閱讀和維護都變更混亂。

#### 問題 BQ：`UnifiedWebScraper.clear_all_caches()` 呼叫 `scraper.clear_cache()`，但 `BaseScraper` / 各 source scraper 並未明確暴露這個方法
從目前已讀內容看：
- `BaseScraper` 沒有定義 `clear_cache()`
- source scraper 也沒看到明確實作

如果其他檔沒有 monkey patch 或 mixin，這裡就有介面不一致風險。

這和前面 `UnifiedCacheManager` 的 best-effort adapter 問題屬於同類：
- 介面看似統一，實際未必完整。

#### 問題 BR：`UnifiedWebScraper.health_check()` 用 `scraper.search_video("test-001")` 當健康檢查，實際上把「功能測試」和「健康檢查」混在一起
這不是單純 ping domain，而是：
- 真正跑一次搜尋流程

優點是更接近真實路徑；
缺點是：
- 依賴測試樣本是否合適
- 成本較高
- 更容易被外部站點策略影響

這種健康檢查設計要嘛文件化，要嘛改名，不然容易誤導。

#### 問題 BS：`AVWikiScraper.batch_search_concurrent()` 已經很像成熟實戰功能，但和 `WebSearcher.batch_search_avwiki_concurrent()` 的存在再次反映責任重疊
也就是：
- service 層有 AV-WIKI 批次併發搜尋
- scraper 層也有 AV-WIKI 批次併發搜尋

這不是功能缺失，而是功能重疊。
長期一定要選一條當主路，不然維護成本會持續翻倍。

#### 問題 BT：`UnifiedScraper` 是這個 repo 目前最像「下一代乾淨架構」的地方，但還沒成為真正主路徑
我這輪最大的感覺是：
- 如果未來要整頓搜尋層
- `scrapers/` 這套反而比較有潛力成為收斂核心

但現在它還不是全系統唯一入口，
所以整體仍然維持雙軌混亂。

### 這一輪暫時結論
- `scrapers/` 不是壞設計，反而是目前比較像「想把事情做乾淨」的一條線
- 但它和既有 `services/web_searcher.py` 那條線沒有完成收斂
- 所以你現在感覺越看越亂，是因為這裡正式證實：
  - **同一類責任在 repo 內有雙重實作與雙重抽象**

---

## 批次 5（子區塊：utils）

### 已讀
- `src/utils/actress_name_filter.py`
- `src/utils/file_mover.py`
- `src/utils/json_utils.py`
- `src/utils/path_setup.py`
- `src/utils/progress_tracker.py`
- `src/utils/retry_utils.py`
- `src/utils/scanner.py`

### 這一輪確認到的事
- `utils/` 很明顯是整個專案的 cross-cutting concern 聚集地：
  - 路徑
  - scanner/mover 包裝
  - 進度顯示
  - JSON backend
  - retry/backoff
  - actress name filter
- 這些工具大多不是壞東西，很多甚至是實用的；
  但它們再次證實：
  - 專案內很多能力都有「wrapper 再包 wrapper」的傾向。

### 這一輪發現的問題

#### 問題 BU：`file_mover.py` / `scanner.py` 和前面 core/service/go bridge 之間再次形成包裝層重疊
現在有：
- Go CLI bridge
- `FileMover`
- `UnifiedFileScanner`
- core/service 直接操作 scan/move 流程

這本身是可以理解的 façade，但如果沒有明確規定「哪一層才是正式入口」，就會繼續加深心智負擔。

#### 問題 BV：`path_setup.py` 本質上是在為 package 結構不收斂買單
它存在的理由很直接：
- 腳本/工具沒辦法穩定 import 專案模組
- 所以要靠 `run.py` / `src` 路徑搜尋和 `sys.path` 注入來補

單看這個工具沒什麼錯，
但它是第一批 `run.py sys.path` 問題的延伸證據。

#### 問題 BW：`ProgressTracker` / `LoadingIndicator` 這類 UI/流程工具很實用，但也顯示 GUI/console/service 邊界混得比較近
例如：
- 載入動畫
- 進度節流
- 級聯搜尋結果資料結構

這些工具跨越：
- UI 顯示
- service workflow
- 搜尋統計

本身不是 bug，但再次說明整個系統分層是偏實用混合，而不是嚴格切層。

#### 問題 BX：`ActressNameFilter` 雖然是好的收斂動作，但仍是硬編碼規則中心
這個工具本身其實是加分：
- 把女優名稱過濾邏輯抽出來了

但它的內容仍然是：
- 大量 title keyword
- 日文/中文關鍵詞
- 特例規則

也就是說它只是把知識集中，
還沒有變成可配置、可版本化、可測試來源明確的規則系統。

#### 問題 BY：`FileMover` / `UnifiedFileScanner` 的 fallback façade 很實用，但也進一步增加「實際路徑在哪裡」的不透明性
例如：
- use_go=True 時走 Go bridge
- 失敗就 silent fallback 到 Python

這和前面其他層的風格一致：
- 盡量讓功能繼續跑
- 但代價是 debug/審計時要花更多力氣才知道真正走了哪條路

#### 問題 BZ：`json_utils.py` 很乾淨，反而凸顯其他模組可以更小更純
這是少數我會直接說「寫得乾淨」的檔案：
- 單一責任
- fallback 清楚
- API 簡單

它剛好反襯出專案其他模組的問題不是能力不足，
而是責任沒有像這個檔案一樣被壓小。

#### 問題 CA：`retry_utils.py` 與 scraper/base retry/health/rate limit 再次有概念重疊
- `ExponentialBackoff`
- `AdaptiveConcurrencyController`

這些是合理的工具；
但專案不同地方也各自有 retry/backoff/限流概念。
這說明 cross-cutting concern 目前仍未真正集中成唯一機制。

### 這一輪暫時結論
- `utils/` 補齊後，批次 5 可以算完成
- 它再次證實這個 repo 的主要問題不是單一壞模組，而是：
  - wrapper 太多
  - fallback 太多
  - 正式入口不夠明確
  - cross-cutting concern 尚未真正收斂

### 本批次狀態
- **批次 5 已完成**

---

## 批次 6（子區塊：tests core + bridge/integration scripts）

### 已讀
- `tests/test_actress_name_filter.py`
- `tests/test_extractor.py`
- `tests/test_go_accelerated_db.py`
- `tests/test_incremental_db.py`
- `tests/test_json_database.py`
- `tests/test_safe_javdb_searcher.py`
- `test_go_db_bridge.py`

### 這一輪確認到的事
- 專案**不是沒有測試**，而且某些區域（例如 extractor、actress filter、json utils、基礎 DB CRUD）其實有不錯的基本覆蓋。
- 但測試結構也反映出整體架構狀態：
  - 有些是正規 pytest 測試
  - 有些其實是手動驗證 script
  - 有些測試依賴實際資料目錄/環境
- 也就是說：
  - 測試存在
  - 但測試層本身還沒有完全收斂成穩定、自動化、可重現的一致體系。

### 這一輪發現的問題

#### 問題 CB：測試層混合了「單元測試 / 手動驗證 / 基準腳本 / 環境依賴測試」，邊界不清
例如：
- `tests/test_actress_name_filter.py` 很像正常 pytest 單元測試
- `tests/test_incremental_db.py` 比較像手動執行的示範/基準腳本
- `test_go_db_bridge.py` 是 root level script，還自己改 `sys.path`

這表示測試檔案雖然多，但型態不一致。

#### 問題 CC：不少測試仍然在替 package/import 結構問題買單
像：
- `test_go_db_bridge.py` 直接 `sys.path.insert(0, str(Path(__file__).parent / "src"))`

這再次證明：
- import 路徑設計還沒完全收斂
- 連測試層都需要自行 patch 路徑才能跑

#### 問題 CD：`tests/test_incremental_db.py` 和 `test_go_db_bridge.py` 依賴實際資料/環境，降低自動化可靠性
像：
- `IncrementalJSONDB("data/json_db")`
- `db_get_video("STARS-707")`
- 取既有資料庫內容做測試

這種測試在人工驗證時很有價值，
但不適合當穩定 CI 單元測試，因為：
- 依賴本機資料狀態
- 資料改變就可能造成測試漂移
- 很難保證可重現

#### 問題 CE：已有的 pytest 測試較擅長保護局部功能，但不夠保護架構級風險
目前已讀 tests 對這些有保護：
- extractor 規則
- actress name filter
- JSON CRUD
- 某些 retry/safe_request 細節

但對前面已經確認的重要風險，保護明顯不足，例如：
- Python/Go 雙軌行為是否一致
- workflow 重複流程是否漂移
- config 是否真的被 service/core 使用
- cache 多層邏輯是否一致
- 規則來源分散時是否同步

也就是說：
- 有測試
- 但大多在守局部 correctness
- 還守不住整體 architecture drift

#### 問題 CF：`test_go_accelerated_db.py` 很有價值，但更像 smoke/integration/perf 腳本，不是純單元測試
它同時在做：
- fallback 模式測試
- API 相容性
- 效能對比
- 工廠函式

這內容本身是有用的，
但把這些混在單一 script 中，也反映出：
- 測試層尚未按責任拆乾淨
- unit/integration/benchmark 邊界不夠明確

#### 問題 CG：`tests/test_extractor.py` 有測到很多 happy path 與已知案例，但仍不足以覆蓋你前面 extractor 規則重疊/脆弱性風險
它有測：
- 標準格式
- 無橫槓
- 品質標記
- FC2/PPV skip
- 複雜檔名

這很好；
但前面我標記的高風險點還包括：
- pattern 優先順序衝突
- 容易誤判的噪音檔名
- false positive
- 與 Python/Go 行為是否一致

這部分還沒有足夠保護。

#### 問題 CH：測試層尚未形成「哪一種問題應該由哪一層測試防守」的清楚策略
目前看起來更像是：
- 哪裡痛就補一個 test/script

這種方式在專案前期很合理，
但到你現在這個規模時，就會導致：
- 有不少 test
- 但仍然缺少測試體系

### 這一輪暫時結論
- 測試層不是空白，甚至比很多 side project 完整
- 但它目前更像「歷史累積出的測試集合」，不是「能穩定保護架構演進的測試體系」
- 所以它能抓到不少局部 bug，卻還守不住你這個 repo 現在最大的風險：
  - 邊界漂移
  - 雙軌架構
  - 規則分散
  - workflow 膨脹

### 補讀剩餘 tests 後的追加發現

#### 問題 CI：剩餘 tests 進一步證實「測試很多，但型態持續不一致」
補讀的：
- `tests/test_studio.py`
- `tests/test_studio_integration.py`
- `tests/test_scanner_integration.py`
- `tests/test_integration_actress_filter.py`
- `tests/測試程式說明.txt`

其中同時存在：
- 標準 pytest
- root-level/manual style integration
- 直接 print/log 的驗證腳本
- 說明文件中提到 `unit/ integration/ fixtures/`，但實際目前並非完全依此結構收斂

#### 問題 CJ：`tests/測試程式說明.txt` 描述的測試架構與目前 repo 現況不完全一致
說明檔寫的是：
- `unit/`
- `integration/`
- `fixtures/`

但目前 `tests/` 根目錄仍是多種測試檔直接平鋪，
顯示測試文件與實際結構也有輕微漂移。

#### 問題 CK：`test_studio_integration.py` / `test_scanner_integration.py` 再次證明 smoke/integration/perf/manual 驗證混在一起
這些檔案內容很有價值，
但它們本質更像：
- 可人工執行的驗證腳本
- 帶 logging/benchmark 的整合檢查

不是純 unit test。

這讓我更確定：
- 測試層是有誠意的
- 但尚未變成統一、自動化、可重現的測試體系

### 本批次狀態
- **批次 6 已完整完成**

---

## 最終總結

### 一句話評價
這個 repo 不是「做不好」，而是：

> **功能驅動、實戰導向、持續疊代，但架構收斂失敗，導致技術債已上升到架構級。**

### 我看到的 4 類問題分級

#### A. 高風險、應優先修
1. Go bridge `db_*` 參數順序 / CLI 旗標解析風險
2. mover overwrite 非原子，存在資料遺失風險
3. database journal / dirty/index / merge 語義不一致
4. cache index 非原子寫入
5. Python/Go 狀態同步點過於脆弱（特別是 `GoAcceleratedDB`）

#### B. 中期一定要整理
1. `UnifiedClassifierCore` / `WebSearcher` / `JSONDBManager` 過胖
2. workflow 重複過多（search / move / classify）
3. config / type / constants 與實作漂移
4. 測試層缺乏一致的 unit/integration/smoke 邊界

#### C. 正常技術債，但不急著第一時間處理
1. import / `sys.path` / `path_setup` 技術債
2. fallback 吞錯與 best-effort adapter 風格
3. progress/UI/service 混合式分層
4. alias / keyword / actress filter 等規則型硬編碼

#### D. 架構級問題（不是單點 patch 能解）
1. 搜尋系統雙軌並行：
   - `WebSearcher` 線
   - `scrapers/` 線
2. 規則知識分散：
   - studio rules / alias / fallback mapping / classifier lists
3. cross-cutting concern 未收斂：
   - cache / retry / pacing / fallback / path/import
4. 中心物件過胖，責任邊界失控

### 我對專案成熟度的重新評價
- **功能成熟度：中高**
- **架構成熟度：中低**
- **實戰經驗感：高**
- **長期可維護性：正在惡化，如果不整頓會反噬開發速度**

### 最值得先做的整頓方向（不是立刻改碼清單，而是方向）
1. 指定「唯一正式搜尋路線」：決定 `WebSearcher` 還是 `scrapers/` 才是主幹
2. 收斂規則知識來源：studio/alias/prefix/fallback mapping 不要再散
3. 切小巨型中心物件：
   - classifier core
   - web searcher
   - json db manager
4. 建立真正的測試分層：
   - unit
   - integration
   - smoke/manual
5. 把高風險資料一致性問題先補強：
   - overwrite 原子性
   - cache/db 原子寫入
   - journal 語義一致性

### 審查結論
- 核心程式碼已依計畫分批閱讀完成
- README 之外的核心模組、服務層、scraper、utils、tests 都已實際閱讀
- 目前已足以進入「整理優先級 / 制定重構路線」階段

REVIEW_COMPLETE
