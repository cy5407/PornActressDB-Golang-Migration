# 掃描 / 搬移 / 橋接層深入重構方案

更新日期：2026-04-04

## 目的

這份文件是 [04-scan-move-and-bridge.md](./04-scan-move-and-bridge.md) 的深入版，目標不是只回答「適不適合 Go」，而是直接回答：

1. 現在這區每一段 Python / Go 程式碼各自負責什麼。
2. 實務上哪些片段應該搬到 Go。
3. 要怎麼搬，才不會只是把大檔案換語言。
4. 最終 Python 要縮成什麼程度。

## 本次深入檢閱範圍

已細讀：

- `src/services/go_bridge.py`
- `src/utils/scanner.py`
- `src/utils/file_mover.py`
- `src/services/go_bridge_test.py`
- `tests/test_scanner_integration.py`
- `cmd/scanner/main.go`
- `pkg/mover/mover.go`
- `pkg/extractor/extractor.go`

## 一句話結論

這一區不應再維持「Python 包一層邏輯 + Go 再做一次核心」的雙層模式。  
**正確方向是：Go 成為唯一核心實作，Python 只保留極薄的 adapter 與 GUI 對接。**

---

## 一、現況拆解：每個檔案現在到底在做什麼

### 1. `src/services/go_bridge.py`

這個檔案現在同時做了 5 種工作：

1. 執行檔探索
2. subprocess 執行與 timeout 控制
3. JSON 解析與輸出容錯
4. Python DTO 定義
5. 高階 API 包裝

代表片段：

- `GoBridge._find_exe()`：找 `classifier.exe`
- `GoBridge._run_command()`：真正執行 subprocess
- `GoBridge._parse_json_from_output()`：容忍混合輸出
- `GoBridge.scan_directory()`：掃描 API
- `GoBridge.move_file()` / `batch_move()` / `rollback()`：搬移與歷史 API
- `db_*` / `identify_*` 家族：其實已經不只是 bridge，而是「領域 API adapter」

### 2. `src/utils/scanner.py`

這個檔案現在做 3 件事：

1. 決定用 Go 還是 Python
2. Python 原生掃描 fallback
3. 回傳 GUI / service 端習慣的資料格式

代表片段：

- `UnifiedFileScanner.scan_directory()`
- `_scan_with_python()`
- `_scan_with_go()`
- `scan_with_codes()`

### 3. `src/utils/file_mover.py`

這個檔案現在做 4 件事：

1. 決定用 Go 還是 Python
2. Python 原生單檔 / 批次 / 目錄移動
3. 將 Go 回傳結果轉成 Python dict
4. 暫存最後一次 operation ID 供 rollback

代表片段：

- `move_file()`
- `_move_with_python()`
- `_move_with_go()`
- `batch_move()`
- `rollback()`
- `list_operations()`

### 4. `cmd/scanner/main.go`

這個檔案同時是：

1. CLI 入口
2. 旗標解析器
3. 命令協調器
4. JSON 輸出入口
5. 部分業務流程容器

這表示目前 Go 端雖然已經很強，但 `main.go` 仍偏肥。

### 5. `pkg/mover/mover.go`

這是目前最接近「真正核心」的 Go 實作：

- `MoveFile`
- `MoveDir`
- `BatchMove`
- `Rollback`
- `ListOperations`
- 日誌寫入 / 載入
- 衝突命名與安全覆蓋

### 6. `pkg/extractor/extractor.go`

這個模組已經是很乾淨的 Go 核心元件，幾乎可以作為其他區塊重構的參考樣板。

---

## 二、實務上的核心問題：不是不能搬，而是目前邊界還不夠乾淨

### 問題 1：Python bridge 不只是 bridge

`go_bridge.py` 已經把「命令列呼叫」、「資料格式轉換」、「錯誤語義」、「領域 API」都混在一起。  
這會導致：

- Python 變胖
- Go CLI 一改，Python 大片跟著改
- bridge 很難收斂成穩定層

### 問題 2：Python fallback 與 Go 核心重複實作太多

`scanner.py` 和 `file_mover.py` 不是單純 adapter，而是各自保有一份 Python 實作。  
這表示你雖然有 Go 核心，但 Python 還是維持了完整備援版。

### 問題 3：CLI 與核心套件尚未完全分層

目前 `cmd/scanner/main.go` 雖已比 Python 薄，但還是承擔了：

- 參數驗證
- I/O 模式切換
- 部分流程控制
- 輸出格式責任

如果之後功能繼續加，`main.go` 會越來越像新的 `go_bridge.py`。

### 問題 4：有些功能 Go 套件有了，但 CLI 沒完整暴露

最典型的是：

- `pkg/mover/mover.go` 已有 `MoveDir`
- 但 Python `FileMover.move_dir()` 仍主要靠 Python 實作
- 而且其中還有明顯不一致：Python 端對 Go `move_file()` 傳了不存在的 `log_operation` 參數概念，代表兩邊能力模型沒完全對齊

---

## 三、最終目標架構：Go-only 核心，Python thin adapter

建議的最終形態：

```text
Tkinter GUI / Python Service
        |
        v
   thin adapter
        |
        v
   Go command façade
        |
        v
 Go domain packages
   - scan
   - move
   - history
   - db
   - identify
```

### Python 最終只保留

- GUI 事件處理
- GUI 需要的訊息轉譯
- 極薄的命令呼叫封裝
- fallback 開關策略

### Go 最終負責

- 掃描
- 番號提取
- 單檔 / 批次 / 目錄搬移
- 歷史日誌
- rollback
- DB / identify 的可呼叫 API
- 結構化輸出模型

---

## 四、逐檔案重構：每個程式碼片段應該怎麼搬

## A. `src/services/go_bridge.py`

### A1. `ScanResult` / `MoveResult` / `BatchMoveResult` / `OperationLog`

#### 現況

Python 端自己再定義一次 DTO。

#### 應該怎麼重構

這些資料模型應該把「真相來源」定在 Go 的 JSON schema，而不是 Python dataclass。

#### 實務做法

1. 在 Go 建立穩定輸出模型，例如：
   - `pkg/contracts/scan.go`
   - `pkg/contracts/move.go`
   - `pkg/contracts/history.go`
2. `cmd/scanner/main.go` 只輸出這些 contract。
3. Python 端改成最薄的 mapping：
   - 要嘛直接回 `dict`
   - 要嘛保留 dataclass，但只作為 UI 層 convenience wrapper

#### 建議

若你的目標是壓低 Python，**Python 端 dataclass 可逐步移除，直接使用 dict**。

---

### A2. `_find_exe()`

#### 現況

Python bridge 負責找 `classifier.exe`。

#### 判斷

這段不需要搬到 Go，因為它是 Python 呼叫端的本機探索責任。

#### 但要怎麼收斂

保留在 Python，並縮成獨立 helper，例如：

- `src/services/go_runtime.py`

只負責：

- 找執行檔
- 檢查可用性
- 快取結果

這樣 `go_bridge.py` 不再混這些啟動責任。

---

### A3. `_run_command()` / `_parse_json()` / `_parse_json_from_output()`

#### 現況

Python 端自己處理：

- subprocess timeout
- returncode
- JSON 解析
- 混合輸出容錯

#### 問題

`_parse_json_from_output()` 的存在，代表 Go CLI 並沒有完全保證 stdout 永遠只輸出 JSON。  
這會讓 bridge 被迫容忍髒輸出。

#### 應該怎麼重構

這一段不要搬到 Go，而是要讓 Go 端規格更嚴格，讓 Python 端可以簡化。

#### 實務做法

1. 定義 CLI 規則：
   - `stdout` 永遠只出 JSON
   - `stderr` 永遠出人類訊息
2. 移除 Python 的混合輸出容錯依賴
3. 將 `_run_command()` 縮成單一責任 helper

#### 目標狀態

Python 端只需要：

```python
result = runner.run_json(["move", ...], timeout=300)
return result
```

而不是現在這樣自己猜測輸出哪一段是 JSON。

---

### A4. `scan_directory()`

#### 現況

Python 已很薄，只是組命令後轉 `ScanResult`。

#### 應該怎麼重構

這一段不需要再往 Go 搬邏輯，因為核心邏輯本來就在 Go。  
真正要做的是把 Python 端從「物件方法 + dataclass」進一步縮成「command adapter」。

#### 具體建議

- 保留 `scan_directory()` 對 GUI / service 的穩定介面
- 內部改成呼叫新的 `GoCommandRunner.run_json()`
- 回傳 dict 或極薄 DTO

---

### A5. `move_file()` / `batch_move()` / `rollback()` / `list_operations()` / `get_operation()`

#### 現況

這些都是 bridge 層合理存在的 API，但目前包含太多輸出修補與資料重建。

#### 應該怎麼重構

1. Go 端統一 contract
2. Python 端只做：
   - 參數組裝
   - timeout
   - JSON decode
   - 例外轉換

#### 尤其是 `batch_move()`

目前 Python 需要先建立暫存 JSON 檔案再交給 CLI。

這做法可用，但中長期更好的方向有兩個：

### 方案 A：維持現狀但抽成共用 helper

優點：

- 不用改 CLI 格式
- 成本最低

做法：

- 把 `NamedTemporaryFile + json.dump + cleanup` 抽成 `JsonPayloadFile`

### 方案 B：Go CLI 支援從 stdin 讀批次 JSON

更好的長期方案：

```bash
classifier.exe move -batch-stdin
```

Python 端就能直接：

- 不落地暫存檔
- 少一次磁碟 I/O
- bridge 更乾淨

#### 建議

如果你真要把 Python 比例壓低，**我建議直接做方案 B**。

---

### A6. `db_*` 與 `identify_*` 家族

#### 判斷

這些函式邏輯上不是掃描/搬移層，但它們揭露了一個重要方向：

目前 bridge 已經變成 Python 端的「Go API façade」。

#### 建議

將 `go_bridge.py` 拆成：

- `go_runner.py`
- `go_scan_api.py`
- `go_move_api.py`
- `go_db_api.py`
- `go_identify_api.py`

最後甚至可以只留：

- `src/services/go_api/scan.py`
- `src/services/go_api/move.py`

讓邊界清楚。

---

## B. `src/utils/scanner.py`

### B1. `supported_formats`

#### 現況

Python 自己維護一份副檔名清單，Go `extractor.SupportedFormats` 也維護一份。

#### 問題

這是明顯重複來源。

#### 應該怎麼重構

若目標是 Go-only 核心，副檔名清單應以 Go 為主。

#### 實務做法

短期：

- Python 保留 fallback 時需要的本地常數

中期：

- 將 Python fallback 只留最小應急版本
- 正常路徑一律走 Go scan

長期：

- Python 不再自己維護主清單

---

### B2. `_scan_with_python()`

#### 判斷

這是最典型的「可以保留，但要降級成 emergency fallback」的程式碼。

#### 不建議

- 繼續在 Python 上擴充掃描功能
- 在 Python 版加入更多 parallel / filter / code extraction

#### 應該怎麼重構

保留，但明確降格：

- 僅作為 Go 不可用時的保底模式
- 文件上標示為 degraded mode

#### 目標

不要讓 Python fallback 和 Go 主流程一起演化。

---

### B3. `scan_with_codes()`

#### 現況

Python fallback 模式下回傳 `{"path": ..., "code": ""}`。

#### 問題

這讓同一個 API 在不同模式下語義不一致。

#### 應該怎麼重構

有兩條路：

### 方案 A：fallback 也用 Python extractor 真正提取 code

優點：

- API 一致

缺點：

- Python fallback 會變胖

### 方案 B：將 `scan_with_codes()` 明確標為 Go-only capability

優點：

- 邊界清楚
- 鼓勵主路徑全走 Go

#### 建議

若你的主目標是降 Python 佔比，我建議 **方案 B**。  
也就是說：

- `scan_directory()` 可以 fallback
- `scan_with_codes()` 應視為 Go-only

---

## C. `src/utils/file_mover.py`

### C1. `_move_with_python()`

#### 判斷

這一段目前完整重做了：

- 衝突處理
- 建目錄
- move
- rename fallback

這些都已經是 Go mover 的責任範圍。

#### 應該怎麼重構

保留作為應急 fallback，但不要再擴充。

#### 更重要的是

凡是正常執行路徑，應盡量保證走 Go mover。

---

### C2. `_move_with_go()`

#### 現況

Python 在呼叫 Go 前還先建立目錄：

```python
if create_dirs:
    destination.parent.mkdir(parents=True, exist_ok=True)
```

#### 問題

Go `pkg/mover/mover.go` 的 `MoveFile()` 已經會自己建立目錄。  
這代表責任重複。

#### 應該怎麼重構

這段前置建目錄邏輯應刪掉，讓 Go 成為唯一責任來源。

#### 例外

若 `create_dirs=False` 是一個真實需求，那應該變成 Go API 的顯式選項，而不是 Python 本地行為。

---

### C3. `move_dir()`

#### 這段很重要

這是目前最值得優先收斂的片段之一。

#### 現況問題

1. Python 端對目錄搬移仍保有完整邏輯
2. Go 其實已經有 `Mover.MoveDir()`
3. CLI 尚未正式暴露 `move dir` 能力
4. Python 端嘗試把目錄丟進 `go_bridge.move_file()`，能力模型不乾淨

#### 正確做法

直接把「目錄搬移」升格成 Go CLI 的一級能力。

#### 建議 CLI

```bash
classifier.exe move-dir -src <dir> -dst <dir> -strategy <...>
```

或：

```bash
classifier.exe move -dir -src <dir> -dst <dir>
```

#### Python 端最終應該只剩

```python
def move_dir(...):
    return move_api.move_dir(...)
```

#### 這一段是高優先度重構點

因為它能直接刪掉不少 Python 分支。

---

### C4. `batch_move()`

#### 現況

Python 做格式轉換後丟給 Go，很合理。

#### 建議重構

這段可保留，但把 Python 自己的 `_batch_move_with_python()` 降格成 emergency fallback。

#### 額外建議

Go 端可以再往前一步，支援：

- 分批 flush
- context timeout
- 進度事件輸出到 stderr

這樣未來 GUI 批次搬移就更不需要 Python 介入。

---

### C5. `rollback()` / `list_operations()`

#### 判斷

這些功能天生就該留在 Go 核心，因為它們依賴：

- log schema
- 檔案系統狀態
- 回滾語義

Python 端不應該碰任何回滾規則，只應顯示結果。

#### 最終形態

- Go：定義 rollback 邏輯與狀態模型
- Python：顯示結果

---

## D. `cmd/scanner/main.go`

## D1. `scanCmd()`

#### 現況

這段目前已經是主掃描流程。

#### 應該怎麼重構

把 `scanCmd()` 再切成兩層：

1. `cmd/scanner/main.go`
   - 只處理 flags
   - 呼叫 app service
2. `pkg/app/scan_service.go`
   - 真正執行掃描流程

#### 原因

未來若要加：

- timeout
- include/exclude patterns
- code only / path only 模式
- progress callback

直接堆在 `main.go` 會很快變難維護。

---

## D2. `moveCmd()`

#### 現況

這段已經很接近 façade，但還可以再收斂。

#### 應該怎麼重構

新增 Go 服務層，例如：

- `pkg/app/move_service.go`

由 service 決定：

- 單檔 / 批次 / 目錄模式
- JSON decode
- 結果 contract

CLI 只做旗標解析與輸出。

---

## D3. `historyCmd()`

#### 現況

CLI 本身還處理了：

- 表格輸出
- JSON 輸出
- `--last` 特例

#### 建議

把 `--last` 與歷史查詢邏輯移到 service 層。  
CLI 只選輸出格式。

#### 更進一步

若 Python GUI 主要吃 JSON，未來甚至可以考慮：

- human output mode
- machine JSON mode

明確拆兩種 command policy。

---

## E. `pkg/mover/mover.go`

這個檔案不需要換語言，它需要的是再模組化。

### E1. 應拆出哪些 Go 套件

建議拆成：

- `pkg/moveops/file_move.go`
- `pkg/moveops/dir_move.go`
- `pkg/moveops/batch.go`
- `pkg/moveops/rollback.go`
- `pkg/moveops/history_store.go`
- `pkg/moveops/contracts.go`

#### 理由

現在 `mover.go` 同時放了：

- 檔案移動
- 目錄移動
- 批次流程
- rollback
- log 儲存
- unique naming
- safe replace

邏輯已經夠大，該拆但不用重寫。

---

### E2. `MoveDir()` 應升格成 CLI 公開能力

這是最重要的 Go 端功能缺口之一。  
Go 核心已有，CLI 與 Python adapter 卻還沒收斂到它。

### 建議立即做

1. CLI 新增 `move-dir` 或 `move -kind dir`
2. Python `FileMover.move_dir()` 改走 Go
3. Python 目錄搬移邏輯降為 fallback

---

### E3. `BatchMove(ctx context.Context, ...)`

#### 現況

已接受 `ctx`，但幾乎尚未真正用到取消語意。

#### 建議

這裡非常值得補齊：

- `select { case <-ctx.Done(): ... }`
- 中途取消時的部分完成狀態
- 結構化 cancellation summary

#### 為什麼重要

這能讓 GUI 長任務真正由 Go 控制，而不是 Python 在外層硬切。

---

## 五、具體重構藍圖：分 4 階段做

## 階段 1：先清責任，不急著大改功能

### 目標

- Python bridge 變薄
- Go contract 變穩

### 要做

1. 將 `go_bridge.py` 拆成 runner + domain api
2. 規範所有 CLI：
   - stdout 純 JSON
   - stderr 純訊息
3. 將 Python 的 `_parse_json_from_output()` 依賴降到最低
4. 盤點並統一所有輸出 schema

---

## 階段 2：把目錄搬移與批次輸入徹底 Go 化

### 目標

- 刪掉最肥的 Python 搬移分支

### 要做

1. CLI 暴露 `MoveDir`
2. `FileMover.move_dir()` 優先走 Go
3. `move -batch-stdin` 或等效能力
4. Python 批次暫存檔流程改成可選而非唯一方案

---

## 階段 3：讓掃描變成真正的 Go service

### 目標

- Python 不再自行演化掃描邏輯

### 要做

1. 將 `scanCmd()` 背後抽成 Go service
2. 支援 timeout / cancel / filter
3. `scan_with_codes()` 明確 Go-only
4. Python scanner fallback 降級為 emergency mode

---

## 階段 4：Python 只剩 GUI adapter

### 最終保留的 Python 檔案形態

#### `src/utils/scanner.py`

- 只剩 `from_config()`
- `scan_directory()` 委派 Go
- fallback 非預設

#### `src/utils/file_mover.py`

- 只剩 API 轉接
- 不再是核心實作

#### `src/services/go_bridge.py`

- 不再是一個 800+ 行大檔
- 分裂成多個小型 adapter

---

## 六、最建議的 Go 目錄重組

建議新增：

```text
cmd/scanner/
  main.go

pkg/contracts/
  scan.go
  move.go
  history.go

pkg/app/
  scan_service.go
  move_service.go
  history_service.go
  identify_service.go

pkg/moveops/
  file_move.go
  dir_move.go
  batch.go
  rollback.go
  history_store.go

pkg/runtime/
  jsonio.go
  exitcodes.go
```

### 分工原則

- `contracts`：輸出入 schema
- `app`：命令用服務層
- `moveops`：純核心
- `runtime`：CLI 共用基礎工具

---

## 七、最應優先刪掉的 Python 邏輯

如果只能先砍 5 個地方，我建議依序處理：

1. `src/utils/file_mover.py` 中對目錄搬移的 Python 主流程
2. `src/utils/file_mover.py` 中 Go 前置建目錄的重複責任
3. `src/services/go_bridge.py` 中混合輸出 JSON 修補邏輯
4. `src/utils/scanner.py` 中把 `scan_with_codes()` 當成雙模式 API 的做法
5. `src/services/go_bridge.py` 中過肥的 `db_* / identify_* / move_*` 混雜責任

---

## 八、最務實的實作結論

### 該搬到 Go 的

- 掃描主流程
- 目錄搬移
- 批次搬移輸入處理
- rollback / history 語義
- 所有 move / scan / history contract

### 暫時留在 Python 的

- exe 探索
- subprocess 啟動
- timeout 設定
- GUI 需要的例外轉換

### 不應再繼續擴充的 Python 邏輯

- Python 掃描能力
- Python 搬移能力
- Python 端自己維護的輸出語義修補

---

## 九、最後建議

如果你下一步真的要開始實作，我建議第一批就做這 3 件事：

1. 在 Go CLI 暴露 `MoveDir`
2. 將 `go_bridge.py` 拆成 runner + move/scan api
3. 把 `FileMover` 的 Go 路徑改成真正單一主路徑，Python fallback 只作保底

這三件做完後，這個區塊的 Python 佔比就會明顯下降，而且不需要先動 GUI。

