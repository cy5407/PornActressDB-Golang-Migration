---
name: code-review
description: 審查 Python/Go 程式碼品質、執行緒安全、安全漏洞。用於審查新程式碼、Pull Request、Git diff 或偵測專案特定問題（GUI 執行緒、資料庫操作、GoBridge 整合）。
argument-hint: "[file-path or git-diff]"
user-invocable: true
---

# Code Review Skill

## 何時使用此 Skill

當需要：
1. **審查新程式碼或 Pull Request**（偵測 bug、安全漏洞）
2. **檢查執行緒安全**（Python GUI、Go 並發）
3. **驗證資料庫操作**（IncrementalJSONDB 使用規範）
4. **審查 Python ↔ Go 整合**（GoBridge、JSON 結構）
5. **偵測效能問題**（不當資料庫使用、重複操作）

## 審查原則

**高信噪比** - 僅報告重要問題：
- ✅ Bug、安全漏洞、執行緒不安全、效能問題
- ❌ 風格、格式、命名（預設不審；若使用者明確要求命名一致性，改搭配 `.Codex/skills/naming-conventions/SKILL.md`）

---

## Python 程式碼審查檢查清單

### 1. 執行緒安全 ⚠️ 最重要

#### ❌ 常見錯誤
```python
# 錯誤：直接在背景執行緒更新 GUI
def worker_thread(self):
    result = long_task()
    self.label.config(text="完成")  # ❌ 崩潰風險！
```

#### ✅ 正確做法
```python
# 正確：使用 root.after() 回到主執行緒
def worker_thread(self):
    result = long_task()
    self.root.after(0, lambda: self.label.config(text="完成"))
```

#### 檢查重點
- [ ] 長時間操作在背景執行緒執行？
- [ ] GUI 更新使用 `root.after()`？
- [ ] 共用資料使用 `threading.Lock`？
- [ ] 進度回報函式是執行緒安全的？

### 2. 資料庫操作規範

#### ❌ 效能陷阱
```python
# 錯誤：迴圈中重複寫入完整 JSON
for code in codes:
    db = JSONDBManager('data/json_db')  # ❌ 每次讀寫完整檔案！
    db.add_video(code, info)
```

#### ✅ 正確做法
```python
# 正確：使用增量資料庫
db = IncrementalJSONDB('data/json_db')
for code in codes:
    db.add_or_update_video(code, info)  # ✅ 快 40 倍
db.compact()  # 最後統一合併
```

#### 檢查重點
- [ ] 使用 `IncrementalJSONDB` 而非 `JSONDBManager`？
- [ ] 批次操作後呼叫 `compact()`？
- [ ] 沒有在迴圈中重複開啟資料庫？

### 3. 錯誤處理

#### ❌ 不完整的錯誤處理
```python
# 錯誤：網路請求沒有錯誤處理
def search_actress(code):
    response = requests.get(url)  # ❌ 可能失敗
    return response.json()
```

#### ✅ 正確做法
```python
# 正確：完整的錯誤處理
def search_actress(code):
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.Timeout:
        logger.error(f"❌ 搜尋逾時: {code}")
        return None
    except Exception as e:
        logger.error(f"❌ 搜尋失敗: {e}")
        return None
```

#### 檢查重點
- [ ] 網路請求有 timeout？
- [ ] 檔案操作有 try-except？
- [ ] 使用 emoji 日誌前綴？（🚀 ✅ ❌ ⚠️ 📊）

### 4. 日文編碼處理

#### ❌ 編碼問題
```python
# 錯誤：假設所有網站都是 UTF-8
html = response.content.decode('utf-8')  # ❌ 日文網站可能不是
```

#### ✅ 正確做法
```python
# 正確：自動檢測編碼
import chardet

detected = chardet.detect(response.content)
html = response.content.decode(detected['encoding'], errors='ignore')
```

#### 檢查重點
- [ ] 日文網站爬蟲使用 chardet？
- [ ] HTTP 請求拒絕 Brotli 壓縮？
- [ ] BeautifulSoup 使用正確的 parser？

---

## Go 程式碼審查檢查清單

### 1. 錯誤處理 ⚠️ 最重要

#### ❌ 常見錯誤
```go
// 錯誤：忽略錯誤
file, _ := os.Open("data.json")  // ❌ 危險！
defer file.Close()
```

#### ✅ 正確做法
```go
// 正確：檢查所有錯誤
file, err := os.Open("data.json")
if err != nil {
    return fmt.Errorf("開啟檔案失敗: %w", err)  // ✅ 錯誤包裝
}
defer file.Close()
```

#### 檢查重點
- [ ] 所有 `error` 都檢查了？
- [ ] 使用 `fmt.Errorf` 包裝錯誤？
- [ ] 錯誤訊息包含上下文資訊？

### 2. 並發安全

#### ❌ 競態條件
```go
// 錯誤：未保護的共用資源
type Counter struct {
    count int
}

func (c *Counter) Increment() {
    c.count++  // ❌ 競態條件！
}
```

#### ✅ 正確做法
```go
// 正確：使用 Mutex
type Counter struct {
    mu    sync.Mutex
    count int
}

func (c *Counter) Increment() {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.count++  // ✅ 執行緒安全
}
```

#### 檢查重點
- [ ] 共用資料使用 `sync.Mutex` 或 `sync.RWMutex`？
- [ ] goroutine 使用 `sync.WaitGroup` 等待？
- [ ] channel 正確關閉？

### 3. JSON 輸出規範

#### ❌ 錯誤輸出到 stdout
```go
// 錯誤：錯誤訊息輸出到 stdout
func main() {
    if err != nil {
        fmt.Println("Error:", err)  // ❌ 破壞 JSON 格式！
        os.Exit(1)
    }
    // JSON 輸出...
}
```

#### ✅ 正確做法
```go
// 正確：錯誤到 stderr，JSON 到 stdout
func main() {
    if err != nil {
        fmt.Fprintln(os.Stderr, "Error:", err)  // ✅ stderr
        os.Exit(1)
    }
    json.NewEncoder(os.Stdout).Encode(result)  // ✅ stdout
}
```

#### 檢查重點
- [ ] 錯誤訊息輸出到 `os.Stderr`？
- [ ] JSON 輸出到 `os.Stdout`？
- [ ] 使用 `json.NewEncoder` 輸出 JSON？

### 4. 資源管理

#### ❌ 資源洩漏（檔案）
```go
// 錯誤：沒有關閉檔案
func readFile(path string) ([]byte, error) {
    file, err := os.Open(path)
    if err != nil {
        return nil, err
    }
    return io.ReadAll(file)  // ❌ 檔案沒關閉！
}
```

#### ✅ 正確做法（檔案）
```go
// 正確：使用 defer 確保關閉
func readFile(path string) ([]byte, error) {
    file, err := os.Open(path)
    if err != nil {
        return nil, err
    }
    defer file.Close()  // ✅ 一定會關閉
    return io.ReadAll(file)
}
```

#### ❌ 資源洩漏（HTTP）
```go
// 錯誤：沒有關閉 Response Body
func fetchData(url string) ([]byte, error) {
    resp, err := http.Get(url)
    if err != nil {
        return nil, err
    }
    return io.ReadAll(resp.Body)  // ❌ Body 沒關閉！
}
```

#### ✅ 正確做法（HTTP）
```go
// 正確：必須關閉 Response Body
func fetchData(url string) ([]byte, error) {
    resp, err := http.Get(url)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()  // ✅ 防止連線洩漏
    return io.ReadAll(resp.Body)
}
```

#### 檢查重點
- [ ] 檔案操作使用 `defer Close()`？
- [ ] HTTP response body 被關閉？
- [ ] 沒有 goroutine 洩漏？
- [ ] 使用 `go vet` 檢查資源洩漏？

---

## Python ↔ Go 整合審查

### 1. JSON 結構一致性

#### 檢查重點
- [ ] Go 輸出的 JSON 結構與 Python 預期相符？
- [ ] 欄位名稱使用 snake_case（JSON tag）？
- [ ] 可選欄位使用 `omitempty`？

#### 範例檢查
```go
// Go 結構
type ScanResult struct {
    Path string `json:"path"`
    Code string `json:"code"`
    Size int64  `json:"size"`
}
```

```python
# Python 對應
@dataclass
class ScanResult:
    path: str
    code: str
    size: int
```

### 2. GoBridge 錯誤處理

#### ❌ 不完整的 fallback
```python
# 錯誤：沒有 fallback
def scan_directory(self, dir):
    bridge = GoBridge()
    return bridge.scan(dir)  # ❌ Go 不可用時崩潰
```

#### ✅ 正確做法
```python
# 正確：完整的 fallback
def scan_directory(self, dir):
    bridge = GoBridge()
    if bridge.is_available:
        try:
            return bridge.scan(dir)  # Go 加速
        except Exception as e:
            logger.warning(f"Go 失敗，切換 Python: {e}")
    
    # Fallback 到 Python
    return python_scanner.scan(dir)
```

#### 檢查重點
- [ ] 檢查 `bridge.is_available`？
- [ ] 有 Python fallback 機制？
- [ ] 記錄 fallback 原因？

---

## 特殊檢查項目

### Windows 路徑處理

#### ❌ 錯誤
```python
path = "C:/Users/test/file.mp4"  # ❌ Unix 風格
```

#### ✅ 正確
```python
import os
path = os.path.join("C:\\Users", "test", "file.mp4")  # ✅ 跨平台
# 或使用 pathlib
from pathlib import Path
path = Path("C:/Users/test/file.mp4")  # ✅ 自動轉換
```

### 級聯搜尋邏輯

#### 檢查順序
```python
# 正確的級聯順序
# 1. AV-WIKI (主要)
# 2. chiba-f (備援)
# 3. JAVDB (最終)
```

#### 檢查重點
- [ ] 搜尋順序正確？
- [ ] 每層失敗才降級？
- [ ] 記錄每次搜尋結果？

---

## 審查報告格式

當發現問題時，使用以下格式報告：

### 🐛 Bug 報告範本
```markdown
**問題**: [簡短描述]
**位置**: 檔案:行號
**嚴重性**: 🔴 高 / 🟡 中 / 🟢 低
**原因**: [為什麼這是問題]
**建議修正**:
[程式碼區塊]
```

### ✅ 審查通過範本
```markdown
✅ **審查通過**
- 執行緒安全：正確
- 錯誤處理：完整
- 效能考量：良好
```

---

## 審查流程

1. **理解變更** - 閱讀 diff 或檔案內容
2. **識別關鍵區域** - 執行緒、資料庫、網路、錯誤處理
3. **檢查專案規範** - 參考本 Skill 的檢查清單
4. **報告重要問題** - 使用報告範本
5. **忽略小問題** - 風格、格式等

---

## 相關資源

- `AGENTS.md` - 完整開發規範
- `src/services/go_bridge.py` - Python ↔ Go 橋接層
- `pkg/` - Go 套件原始碼
- `.Codex/skills/go-bridge-development/SKILL.md` - Go 開發指引
- `.Codex/skills/gui-development/SKILL.md` - GUI 執行緒安全指引

---

## 快速檢查指令

```bash
# Python 語法檢查
python -m py_compile src/**/*.py

# Go 語法檢查
go build ./...

# Python 測試
python -m pytest tests/ -v

# Go 測試
go test ./... -v

# Go 競態檢測
go test -race ./...
```

---

**記住：專注於真正重要的問題，保持高信噪比！** 🎯
