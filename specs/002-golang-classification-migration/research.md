# Research & Technical Decisions

**Feature**: 分類功能 Golang 遷移  
**Date**: 2025-10-18  
**Purpose**: 解決實施計劃中的所有技術未知項，為 Phase 1 設計提供基礎

---

## 1. gRPC 串流進度回報最佳實踐

### 決策: 使用 Server Streaming + Ticker 批次發送

**選擇理由**:
- gRPC Server Streaming 非常適合單向進度推送（伺服器 → 客戶端）
- Go 的 `time.Ticker` 可以精確控制每 1 秒發送一次
- 配合 channel 緩衝可以實現「100 檔案或 1 秒取較先發生者」的邏輯
- Python grpcio 的 `stub.Method(request)` 返回迭代器，可直接遍歷串流訊息

**實作模式**:
```go
func (s *Server) ScanFiles(req *pb.ScanRequest, stream pb.ClassifierService_ScanFilesServer) error {
    ticker := time.NewTicker(1 * time.Second)
    defer ticker.Stop()
    
    progressChan := make(chan *pb.ScanProgress, 100)
    
    // Goroutine 1: 實際掃描邏輯
    go func() {
        count := 0
        for _, file := range files {
            processFile(file)
            count++
            
            // 每 100 檔案發送一次
            if count%100 == 0 {
                progressChan <- &pb.ScanProgress{
                    ProcessedCount: int32(count),
                    Percentage:     float32(count) / float32(total) * 100,
                }
            }
        }
        close(progressChan)
    }()
    
    // Goroutine 2: 定時或批次發送
    for {
        select {
        case <-ticker.C:
            // 每秒發送當前進度
            if progress := getLatestProgress(); progress != nil {
                if err := stream.Send(progress); err != nil {
                    return err
                }
            }
        case progress, ok := <-progressChan:
            if !ok {
                return nil // 完成
            }
            if err := stream.Send(progress); err != nil {
                return err
            }
        }
    }
}
```

**Python 客戶端範例**:
```python
import grpc
from proto import classifier_pb2, classifier_pb2_grpc

channel = grpc.insecure_channel('localhost:50051')
stub = classifier_pb2_grpc.ClassifierServiceStub(channel)

request = classifier_pb2.ScanRequest(folder_path="/path/to/videos", recursive=True)

for progress in stub.ScanFiles(request):
    print(f"進度: {progress.percentage:.1f}% ({progress.processed_count}/{progress.total_count})")
    print(f"當前檔案: {progress.current_file}")
    print(f"預估剩餘時間: {progress.estimated_remaining_ms / 1000:.1f}秒")
```

**錯誤處理**:
- 使用 gRPC 的 `status` 套件返回詳細錯誤
- 客戶端捕獲 `grpc.RpcError` 並解析錯誤碼
- 實作指數退避重連機制 (最多重試 3 次)

**效能特性**:
- 延遲: <5ms (本地 localhost 通訊)
- 頻寬: 每秒約 100 bytes (進度訊息很小)
- 記憶體: Channel 緩衝 100 筆，約 10KB

**替代方案考量**:
- ❌ **HTTP SSE (Server-Sent Events)**: 需要 HTTP 伺服器，複雜度高
- ❌ **WebSocket**: 適合雙向，但此場景只需單向
- ❌ **輪詢 (Polling)**: 延遲高，浪費資源

---

## 2. Goroutine 並行檔案操作最佳實踐

### 決策: Worker Pool + 資料夾鎖定

**選擇理由**:
- Worker Pool 模式可精確控制並行度（最大 8 workers）
- 使用 `sync.Map` 追蹤正在處理的目標資料夾，避免並行寫入衝突
- `golang.org/x/sync/errgroup` 簡化錯誤聚合和取消機制
- 資料夾層級並行：不同子資料夾可以同時掃描，但同一資料夾內的檔案循序處理

**實作模式**:
```go
import (
    "golang.org/x/sync/errgroup"
    "sync"
)

type FolderProcessor struct {
    maxWorkers    int
    targetFolders sync.Map // 追蹤正在寫入的目標資料夾
}

func (p *FolderProcessor) ProcessFolders(folders []string) error {
    g, ctx := errgroup.WithContext(context.Background())
    sem := make(chan struct{}, p.maxWorkers) // Semaphore 限制並行度
    
    for _, folder := range folders {
        folder := folder // 避免 closure 問題
        sem <- struct{}{} // 獲取 token
        
        g.Go(func() error {
            defer func() { <-sem }() // 釋放 token
            
            return p.processFolder(ctx, folder)
        })
    }
    
    return g.Wait() // 等待所有 goroutine 完成，聚合錯誤
}

func (p *FolderProcessor) processFolder(ctx context.Context, folder string) error {
    files, err := os.ReadDir(folder)
    if err != nil {
        return fmt.Errorf("read folder %s: %w", folder, err)
    }
    
    for _, file := range files {
        select {
        case <-ctx.Done():
            return ctx.Err() // 取消信號
        default:
            targetFolder := determineTargetFolder(file)
            
            // 檢查目標資料夾是否正在被其他 goroutine 寫入
            if !p.lockTargetFolder(targetFolder) {
                // 如果資料夾被鎖定，等待或跳過
                time.Sleep(10 * time.Millisecond)
                continue
            }
            defer p.unlockTargetFolder(targetFolder)
            
            if err := moveFile(file, targetFolder); err != nil {
                return fmt.Errorf("move file %s: %w", file.Name(), err)
            }
        }
    }
    
    return nil
}

func (p *FolderProcessor) lockTargetFolder(folder string) bool {
    _, loaded := p.targetFolders.LoadOrStore(folder, struct{}{})
    return !loaded // 如果已存在 (loaded=true)，返回 false
}

func (p *FolderProcessor) unlockTargetFolder(folder string) {
    p.targetFolders.Delete(folder)
}
```

**並行度控制**:
- 預設值: `runtime.NumCPU()` (CPU 核心數)
- 最大值: 8 (避免檔案系統過載)
- CLI 參數: `--workers=4`

**錯誤處理**:
- 單一檔案失敗不中斷整體流程
- 使用 `errgroup` 聚合所有錯誤
- 記錄每個失敗檔案的路徑和錯誤訊息

**效能預期**:
- 在 8 核心 CPU 上，並行處理應達到單執行緒的 4-6 倍速度
- 瓶頸主要在磁碟 I/O，非 CPU

**替代方案考量**:
- ❌ **檔案層級並行**: 會導致對同一資料夾的並行寫入，檔案系統可能不穩定
- ❌ **完全循序**: 無法利用多核心，效能差

---

## 3. JSON 資料庫原子操作

### 決策: File Lock + Temp File + Atomic Rename

**選擇理由**:
- 檔案鎖定 (flock) 確保多程序環境下的互斥存取
- Temp file + rename 確保寫入失敗時不損壞原始資料
- 跨平台支援 (Windows: LockFileEx, Unix: flock)
- 不需要外部資料庫，符合 Constitution 的 "Zero External Dependencies"

**實作模式**:
```go
import (
    "github.com/gofrs/flock" // 跨平台檔案鎖定函式庫
)

type JSONDatabase struct {
    filePath string
    lock     *flock.Flock
}

func NewJSONDatabase(filePath string) *JSONDatabase {
    return &JSONDatabase{
        filePath: filePath,
        lock:     flock.New(filePath + ".lock"),
    }
}

func (db *JSONDatabase) Read() (Data, error) {
    // 獲取共享鎖 (允許多個讀取者)
    if err := db.lock.RLock(); err != nil {
        return Data{}, fmt.Errorf("acquire read lock: %w", err)
    }
    defer db.lock.Unlock()
    
    data, err := os.ReadFile(db.filePath)
    if err != nil {
        return Data{}, fmt.Errorf("read file: %w", err)
    }
    
    var result Data
    if err := json.Unmarshal(data, &result); err != nil {
        return Data{}, fmt.Errorf("unmarshal JSON: %w", err)
    }
    
    return result, nil
}

func (db *JSONDatabase) Write(data Data) error {
    // 獲取排他鎖 (阻止其他讀取或寫入)
    if err := db.lock.Lock(); err != nil {
        return fmt.Errorf("acquire write lock: %w", err)
    }
    defer db.lock.Unlock()
    
    // 寫入到暫存檔
    tempPath := db.filePath + ".tmp"
    jsonData, err := json.MarshalIndent(data, "", "  ")
    if err != nil {
        return fmt.Errorf("marshal JSON: %w", err)
    }
    
    if err := os.WriteFile(tempPath, jsonData, 0644); err != nil {
        return fmt.Errorf("write temp file: %w", err)
    }
    
    // 原子性重新命名
    if err := os.Rename(tempPath, db.filePath); err != nil {
        os.Remove(tempPath) // 清理暫存檔
        return fmt.Errorf("atomic rename: %w", err)
    }
    
    return nil
}
```

**跨平台實作細節**:
- Windows: 使用 `LockFileEx` API (由 flock 函式庫封裝)
- Unix/Linux: 使用 `flock()` 系統呼叫
- macOS: 使用 `flock()` (BSD 風格)

**Python-Go 共存**:
- Python 端使用 `fcntl.flock()` (Unix) 或 `msvcrt.locking()` (Windows)
- Go 和 Python 都遵守相同的鎖定協定
- 鎖定檔案: `data.json.lock`

**效能優化**:
- 讀取操作使用共享鎖，允許多個程序同時讀取
- 寫入操作使用排他鎖，確保互斥
- 記憶體快取: 將常用資料 (actresses, studios) 快取在記憶體中，TTL 1 分鐘

**替代方案考量**:
- ❌ **SQLite**: 需要 cgo，違反 Constitution
- ❌ **無鎖定**: 存在競爭條件風險
- ❌ **樂觀鎖 (版本號)**: 實作複雜，衝突處理困難

**選擇的依賴套件**:
- `github.com/gofrs/flock` - 跨平台檔案鎖定 (1.8k stars, 活躍維護)

---

## 4. 跨平台路徑處理

### 決策: filepath.Join + unicode/utf8 驗證

**選擇理由**:
- `filepath.Join` 自動處理不同平台的路徑分隔符 (\ 或 /)
- Go 原生支援 UTF-8，正確處理日文、中文、Emoji
- `filepath.Clean` 規範化路徑，移除 `..` 和 `.`
- `filepath.Abs` 轉換為絕對路徑，避免相對路徑歧義

**實作模式**:
```go
import (
    "path/filepath"
    "unicode/utf8"
)

// 安全的路徑拼接
func SafeJoinPath(base, target string) (string, error) {
    // 轉換為絕對路徑
    absBase, err := filepath.Abs(base)
    if err != nil {
        return "", fmt.Errorf("resolve base path: %w", err)
    }
    
    // 拼接並規範化
    joined := filepath.Join(absBase, target)
    cleaned := filepath.Clean(joined)
    
    // 驗證路徑不會逃脫 base 目錄 (防止路徑遍歷攻擊)
    if !strings.HasPrefix(cleaned, absBase) {
        return "", fmt.Errorf("path traversal detected: %s", target)
    }
    
    // 驗證 UTF-8 有效性
    if !utf8.ValidString(cleaned) {
        return "", fmt.Errorf("invalid UTF-8 in path: %s", cleaned)
    }
    
    return cleaned, nil
}

// 處理特殊字元
func SanitizeFileName(name string) string {
    // 移除或替換不允許的字元
    // Windows: < > : " / \ | ? *
    // Unix: / (null)
    
    replacements := map[rune]rune{
        '<':  '＜', // 全形替代
        '>':  '＞',
        ':':  '：',
        '"':  '"',
        '/':  '／',
        '\\': '＼',
        '|':  '｜',
        '?':  '？',
        '*':  '＊',
    }
    
    var result strings.Builder
    for _, r := range name {
        if replacement, ok := replacements[r]; ok {
            result.WriteRune(replacement)
        } else {
            result.WriteRune(r)
        }
    }
    
    return result.String()
}
```

**UNC 路徑支援 (Windows 網路路徑)**:
```go
func IsUNCPath(path string) bool {
    return strings.HasPrefix(path, `\\`)
}

func HandleUNCPath(path string) (string, error) {
    if !IsUNCPath(path) {
        return path, nil
    }
    
    // UNC 路徑格式: \\server\share\folder
    // filepath.Join 正確處理 UNC 路徑
    return filepath.Clean(path), nil
}
```

**符號連結處理**:
```go
func ResolveSymlink(path string) (string, error) {
    // 使用 filepath.EvalSymlinks 解析符號連結
    resolved, err := filepath.EvalSymlinks(path)
    if err != nil {
        // 如果不是符號連結，返回原始路徑
        if os.IsNotExist(err) {
            return path, nil
        }
        return "", fmt.Errorf("resolve symlink: %w", err)
    }
    return resolved, nil
}
```

**檔案名稱長度限制**:
- Windows: 260 字元 (MAX_PATH)，NTFS 支援長路徑 (需啟用)
- Linux: 4096 字元 (PATH_MAX)
- macOS: 1024 字元

**實作策略**: 檢查路徑長度，超過限制時提示使用者或自動截斷

**替代方案考量**:
- ❌ **path.Join** (標準庫 path 套件): 僅適用於 URL，不處理本地檔案系統
- ❌ **字串拼接**: 無法處理不同平台的路徑分隔符

---

## 5. Python subprocess 與 Golang 互動

### 決策: subprocess.run + JSON 輸出 + 錯誤處理

**選擇理由**:
- `subprocess.run()` 適合短時間執行的 CLI 命令 (掃描、分類)
- JSON 輸出易於解析，結構化
- `subprocess.Popen()` 適合長時間運行的程序 (gRPC 伺服器)
- 標準錯誤 (stderr) 用於日誌，標準輸出 (stdout) 用於 JSON 結果

**實作模式 - CLI 呼叫**:
```python
import subprocess
import json
from pathlib import Path

class GoClassifierCLI:
    def __init__(self, executable_path: str = "tools/golang/classifier.exe"):
        self.executable = Path(executable_path)
        if not self.executable.exists():
            raise FileNotFoundError(f"Golang classifier not found: {executable_path}")
    
    def scan_files(self, folder: str, recursive: bool = True) -> dict:
        """呼叫 Go CLI 掃描檔案"""
        cmd = [
            str(self.executable),
            "scan",
            "--folder", folder,
            "--format", "json"
        ]
        if recursive:
            cmd.append("--recursive")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=300  # 5 分鐘超時
            )
            
            # 解析 JSON 輸出
            return json.loads(result.stdout)
            
        except subprocess.CalledProcessError as e:
            # Go 程序返回非零退出碼
            raise RuntimeError(f"Scan failed: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise TimeoutError("Scan operation timed out after 5 minutes")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON output from Go: {e}")
    
    def classify_actress(self, folder: str, mode: str = "auto", conflict: str = "skip") -> dict:
        """呼叫 Go CLI 分類女優"""
        cmd = [
            str(self.executable),
            "classify-actress",
            "--folder", folder,
            "--mode", mode,
            "--conflict", conflict
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
```

**實作模式 - gRPC 伺服器管理**:
```python
import subprocess
import time
import grpc
from proto import classifier_pb2_grpc

class GoClassifierServer:
    def __init__(self, executable_path: str = "tools/golang/classifier-server.exe"):
        self.executable = Path(executable_path)
        self.process = None
        self.port = 50051
    
    def start(self):
        """啟動 Go gRPC 伺服器"""
        if self.process is not None:
            raise RuntimeError("Server already running")
        
        self.process = subprocess.Popen(
            [str(self.executable), "--port", str(self.port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 等待伺服器啟動 (檢查連線)
        for _ in range(10):
            try:
                channel = grpc.insecure_channel(f'localhost:{self.port}')
                grpc.channel_ready_future(channel).result(timeout=1)
                channel.close()
                print(f"gRPC server started on port {self.port}")
                return
            except grpc.FutureTimeoutError:
                time.sleep(0.5)
        
        raise RuntimeError("Failed to start gRPC server")
    
    def stop(self):
        """停止 Go gRPC 伺服器"""
        if self.process is None:
            return
        
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
        
        self.process = None
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
```

**大量輸出處理**:
```python
def scan_large_folder(folder: str):
    """處理大量輸出 (使用 streaming)"""
    cmd = ["classifier", "scan", "--folder", folder, "--format", "jsonl"]
    
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as proc:
        for line in proc.stdout:
            if line.strip():
                result = json.loads(line)
                process_scan_result(result)  # 逐行處理，避免記憶體爆炸
```

**錯誤處理**:
- 退出碼 0: 成功
- 退出碼 1: 一般錯誤 (解析 stderr 獲取詳細訊息)
- 退出碼 2: 無效參數
- 超時: 使用 `timeout` 參數防止 CLI 掛起

**進程清理**:
```python
import atexit

# 註冊清理函數，確保程序退出時關閉 Go 伺服器
server = GoClassifierServer()
atexit.register(server.stop)
```

**替代方案考量**:
- ❌ **直接呼叫 Go 函式 (cgo)**: 複雜度極高，違反 Constitution
- ❌ **檔案通訊**: 效能低，實時性差

---

## 6. 番號提取正則表達式模式

### 決策: 多模式匹配 + 優先級排序

**選擇理由**:
- 支援 10+ 種常見番號格式
- 使用正則表達式群組提取前綴和數字
- 優先級排序：先匹配嚴格格式，再匹配寬鬆格式

**實作模式**:
```go
import "regexp"

var codePatterns = []*regexp.Regexp{
    // 優先級 1: 標準格式 (ABC-123)
    regexp.MustCompile(`([A-Z]{2,6})-(\d{3,5})`),
    
    // 優先級 2: 無連字符 (ABC123)
    regexp.MustCompile(`([A-Z]{2,6})(\d{3,5})`),
    
    // 優先級 3: 帶網站前綴 (hhd800.com@ABC-123)
    regexp.MustCompile(`@([A-Z]{2,6})-(\d{3,5})`),
    
    // 優先級 4: 帶女優名後綴 (ABC-123-女優名)
    regexp.MustCompile(`([A-Z]{2,6})-(\d{3,5})-`),
    
    // 優先級 5: FC2 格式 (FC2-PPV-1234567)
    regexp.MustCompile(`(FC2)-(PPV)-(\d{6,8})`),
}

func ExtractVideoCode(filename string) (string, error) {
    // 移除副檔名
    name := strings.TrimSuffix(filename, filepath.Ext(filename))
    
    // 嘗試每個模式
    for _, pattern := range codePatterns {
        if matches := pattern.FindStringSubmatch(name); matches != nil {
            // matches[0]: 完整匹配
            // matches[1]: 前綴 (e.g., "ABC")
            // matches[2]: 數字 (e.g., "123")
            code := matches[1] + "-" + matches[2]
            return strings.ToUpper(code), nil
        }
    }
    
    return "", fmt.Errorf("no video code found in: %s", filename)
}
```

**測試案例**:
- `SONE-123.mp4` → `SONE-123`
- `ABC123.mkv` → `ABC-123`
- `hhd800.com@STARS-456.mp4` → `STARS-456`
- `SONE-789-女優名.mp4` → `SONE-789`
- `FC2-PPV-1234567.mp4` → `FC2-PPV-1234567`

**準確率驗證**:
- 使用現有 Python 實作的測試資料集
- 目標: ≥95% 匹配率

---

## 7. 記憶體優化策略

### 決策: 串流處理 + 限制快取大小

**選擇理由**:
- 避免一次性載入所有檔案資訊到記憶體
- 使用 `os.ReadDir` 逐個讀取目錄項目
- 限制記憶體快取大小 (LRU 策略)

**實作模式**:
```go
func ScanFolderStreaming(folderPath string, callback func(VideoFile) error) error {
    entries, err := os.ReadDir(folderPath)
    if err != nil {
        return err
    }
    
    for _, entry := range entries {
        if entry.IsDir() {
            continue
        }
        
        // 立即處理，不累積
        videoFile := VideoFile{
            Path: filepath.Join(folderPath, entry.Name()),
            Name: entry.Name(),
        }
        
        if err := callback(videoFile); err != nil {
            return err
        }
    }
    
    return nil
}
```

**LRU 快取**:
```go
import "github.com/hashicorp/golang-lru"

type DatabaseCache struct {
    actresses *lru.Cache
    studios   *lru.Cache
}

func NewDatabaseCache(size int) (*DatabaseCache, error) {
    actressCache, err := lru.New(size)
    if err != nil {
        return nil, err
    }
    
    studioCache, err := lru.New(size)
    if err != nil {
        return nil, err
    }
    
    return &DatabaseCache{
        actresses: actressCache,
        studios:   studioCache,
    }, nil
}
```

**記憶體監控**:
```go
import "runtime"

func PrintMemUsage() {
    var m runtime.MemStats
    runtime.ReadMemStats(&m)
    fmt.Printf("Alloc = %v MB", m.Alloc / 1024 / 1024)
    fmt.Printf("TotalAlloc = %v MB", m.TotalAlloc / 1024 / 1024)
    fmt.Printf("Sys = %v MB", m.Sys / 1024 / 1024)
}
```

---

## 總結與後續步驟

### 已解決的技術決策

1. ✅ gRPC 串流進度回報: Server Streaming + Ticker
2. ✅ Goroutine 並行: Worker Pool + 資料夾鎖定
3. ✅ JSON 資料庫: File Lock + Atomic Rename
4. ✅ 跨平台路徑: filepath.Join + UTF-8 驗證
5. ✅ Python-Go 通訊: subprocess.run (CLI) + Popen (gRPC 伺服器)
6. ✅ 番號提取: 多模式正則匹配
7. ✅ 記憶體優化: 串流處理 + LRU 快取

### 選定的依賴套件

| 套件 | 用途 | Stars | 維護狀態 |
|------|------|-------|---------|
| `google.golang.org/grpc` | gRPC 通訊 | 20k+ | ✅ 活躍 |
| `google.golang.org/protobuf` | Protocol Buffers | 1.4k+ | ✅ 活躍 |
| `github.com/spf13/cobra` | CLI 框架 | 35k+ | ✅ 活躍 |
| `go.uber.org/zap` | 結構化日誌 | 20k+ | ✅ 活躍 |
| `github.com/gofrs/flock` | 檔案鎖定 | 1.8k+ | ✅ 活躍 |
| `github.com/hashicorp/golang-lru` | LRU 快取 | 4k+ | ✅ 活躍 |
| `golang.org/x/sync/errgroup` | 錯誤聚合 | 標準庫擴展 | ✅ 官方 |

### 風險與緩解

| 風險 | 緩解措施 |
|------|---------|
| gRPC 延遲超過 10ms | 使用 localhost 通訊，優化訊息大小 |
| 並行寫入衝突 | 資料夾層級鎖定，Worker Pool 限制 |
| JSON 資料庫競爭 | File Lock 確保互斥存取 |
| 記憶體超過 500MB | 串流處理 + LRU 快取，定期 GC |
| 跨平台路徑問題 | 使用 filepath 標準庫，完整測試 |

### 後續步驟

1. ✅ **Phase 0 完成**: 所有技術決策已明確
2. ➡️ **進入 Phase 1**: 生成資料模型、API 契約、快速開始指南
3. 準備開發環境: 安裝 Go 1.22+, Protocol Buffers 編譯器
4. 建立專案結構: `golang/` 目錄和子模組

---

**更新日期**: 2025-10-18  
**審核狀態**: ✅ 已完成，可進入 Phase 1
