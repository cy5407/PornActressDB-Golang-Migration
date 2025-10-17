# gRPC 部署指南 - 本地端應用

**專案**: 女優分類功能 Golang 遷移  
**部署模式**: 本地程序通訊 (Local Process Communication)  
**日期**: 2025-10-17

---

## 🎯 核心概念澄清

### ❌ **不需要架設遠端伺服器**

您的情況是 **本地桌面應用程式**，gRPC 伺服器是：
- ✅ **本地程序** (localhost)
- ✅ **自動啟動/關閉**
- ✅ **不對外開放**
- ✅ **零網路配置**

類似於：
```
Python GUI (主程序)
  └─ 啟動 → Golang gRPC 伺服器 (子程序, localhost:50051)
       └─ 處理分類任務
  └─ 關閉 → 自動終止 Golang 程序
```

---

## 📋 方案比較：是否需要「伺服器」

| 方案 | 需要伺服器？ | 啟動方式 | 網路配置 | 複雜度 |
|------|-------------|---------|---------|--------|
| **CLI** | ❌ 不需要 | Python 直接呼叫 exe | 無 | ⭐ 最簡單 |
| **JSON-RPC** | ⚠️ 本地伺服器 | Python 自動啟動 localhost:8080 | 需管理 Port | ⭐⭐ 簡單 |
| **gRPC** | ⚠️ 本地伺服器 | Python 自動啟動 localhost:50051 | 需管理 Port | ⭐⭐ 簡單 |

**注意**: 這裡的「伺服器」只是本地程序，不是真正的網路伺服器！

---

## 🔧 方案 E 實際架構

### 階段 1: CLI 工具 (完全不需要伺服器)

```
使用者操作 GUI
    ↓
Python 呼叫 CLI
    ↓ subprocess.run()
Golang.exe --scan "D:\女優分類" --output json
    ↓ (執行完畢，程序結束)
回傳 JSON 結果
    ↓
Python 解析並顯示
```

**部署需求**:
- ✅ 只需一個 `classifier.exe` 執行檔
- ✅ 放在任意目錄 (例如: `tools/golang/classifier.exe`)
- ✅ Python 用 `subprocess.run()` 呼叫
- ❌ 不需要任何網路設定
- ❌ 不需要啟動/停止伺服器

**優點**:
- 零配置
- 零學習成本
- 程序隔離（崩潰不影響 GUI）

---

### 階段 2: 加入 gRPC (本地程序伺服器)

```python
# Python GUI 啟動時
class GoClassifier:
    def __init__(self):
        # 自動啟動 Golang gRPC 本地伺服器
        self.process = subprocess.Popen(
            ['tools/golang/classifier_server.exe'],
            # 監聽 localhost:50051 (只有本機可連線)
        )
        time.sleep(1)  # 等待啟動
        
        # 建立 gRPC 客戶端連線到 localhost
        self.channel = grpc.insecure_channel('localhost:50051')
        self.stub = ClassifierStub(self.channel)
    
    def classify_interactive(self, folder):
        # 呼叫 gRPC 方法 (像函式呼叫一樣)
        for progress in self.stub.ClassifyWithProgress(request):
            print(f"進度: {progress.percent}%")
    
    def __del__(self):
        # GUI 關閉時自動終止 Golang 程序
        self.process.terminate()
```

**實際運作**:
1. 使用者啟動 `run.py` (Python GUI)
2. Python 自動啟動 `classifier_server.exe` (背景程序)
3. Golang 程序監聽 `localhost:50051` (只有本機可連)
4. Python 透過 gRPC 呼叫 Golang 函式
5. 使用者關閉 GUI → Python 自動終止 Golang 程序

**部署需求**:
- ✅ 一個 `classifier_server.exe` 執行檔
- ✅ Python 自動管理啟動/關閉
- ✅ 只監聽 localhost (外部無法連線)
- ⚠️ 需確保 Port 50051 未被佔用 (可動態分配)
- ❌ **不需要 IIS / Nginx / Apache**
- ❌ **不需要網域名稱**
- ❌ **不需要 SSL 憑證**
- ❌ **不需要防火牆設定**

---

## 💡 與真正「架伺服器」的差異

### ❌ 傳統網路伺服器 (您不需要這樣)

```
[遠端伺服器 AWS/Azure]
    ├─ 安裝作業系統
    ├─ 設定防火牆
    ├─ 申請網域名稱
    ├─ 設定 SSL 憑證
    ├─ 部署應用程式
    └─ 24/7 運行
         ↓ (透過網路)
[使用者電腦] → https://api.example.com
```

### ✅ 本地程序通訊 (您的實際方案)

```
[使用者電腦 - 本地端]
    ├─ Python GUI (主程序)
    └─ Golang gRPC (子程序, localhost only)
         ↑
         └─ 只有本機內部通訊，不經過網路
```

---

## 📦 實際部署步驟

### 方案 E 階段 1: CLI (推薦先從這開始)

#### 1. 開發階段
```bash
# Golang 開發
cd golang-classifier
go build -o classifier.exe main.go

# 測試
./classifier.exe --scan "D:\test" --output json
```

#### 2. 整合到 Python
```python
# src/services/golang_cli_wrapper.py
import subprocess
import json
import os

class GolangClassifier:
    def __init__(self):
        # 找到 exe 位置
        self.exe_path = os.path.join(
            os.path.dirname(__file__), 
            '../../tools/golang/classifier.exe'
        )
    
    def scan_files(self, folder_path):
        """呼叫 Golang CLI 掃描檔案"""
        result = subprocess.run(
            [self.exe_path, '--scan', folder_path, '--output', 'json'],
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        
        if result.returncode != 0:
            raise Exception(f"掃描失敗: {result.stderr}")
        
        return json.loads(result.stdout)
```

#### 3. 部署到使用者電腦
```
專案資料夾/
├─ run.py                    # Python 主程式
├─ src/
│   └─ services/
│       └─ golang_cli_wrapper.py
└─ tools/
    └─ golang/
        └─ classifier.exe    # ← 只需複製這個檔案
```

**使用者操作**:
1. 解壓縮專案資料夾
2. 雙擊 `run.py`
3. ✅ 自動使用 Golang 加速 (無感切換)

**完全不需要**:
- ❌ 安裝 Golang
- ❌ 設定環境變數
- ❌ 啟動任何服務
- ❌ 網路設定

---

### 方案 E 階段 2: 加入 gRPC (如需互動功能)

#### 1. 開發階段
```bash
# 定義 Protocol Buffers
# classifier.proto
syntax = "proto3";

service Classifier {
  rpc ScanFiles(ScanRequest) returns (stream ScanProgress);
  rpc ClassifyActress(ClassifyRequest) returns (ClassifyResponse);
}

# 生成程式碼
protoc --go_out=. --python_out=. classifier.proto

# 編譯 Golang 伺服器
go build -o classifier_server.exe server.go
```

#### 2. Python 自動管理
```python
# src/services/golang_grpc_client.py
import subprocess
import grpc
import time
import atexit
from . import classifier_pb2_grpc

class GolangGRPCClient:
    def __init__(self):
        self.process = None
        self.channel = None
        self.stub = None
    
    def start(self):
        """啟動 Golang gRPC 本地伺服器"""
        exe_path = 'tools/golang/classifier_server.exe'
        
        # 啟動程序 (只監聽 localhost)
        self.process = subprocess.Popen(
            [exe_path, '--port', '50051'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # 等待伺服器就緒
        time.sleep(1)
        
        # 連線到本地伺服器
        self.channel = grpc.insecure_channel('localhost:50051')
        self.stub = classifier_pb2_grpc.ClassifierStub(self.channel)
        
        # 註冊清理函式
        atexit.register(self.stop)
    
    def stop(self):
        """關閉伺服器"""
        if self.channel:
            self.channel.close()
        if self.process:
            self.process.terminate()
            self.process.wait()
    
    def scan_with_progress(self, folder):
        """即時進度的掃描"""
        request = classifier_pb2.ScanRequest(folder=folder)
        
        # 串流接收進度更新
        for progress in self.stub.ScanFiles(request):
            yield progress.current, progress.total, progress.message
```

#### 3. GUI 整合
```python
# src/ui/main_gui.py
class MainWindow:
    def __init__(self):
        # 啟動 Golang gRPC 客戶端
        self.golang_client = GolangGRPCClient()
        self.golang_client.start()  # 背景啟動
    
    def on_scan_clicked(self):
        folder = self.folder_entry.get()
        
        # 即時顯示進度
        for current, total, message in self.golang_client.scan_with_progress(folder):
            self.progress_bar['value'] = (current / total) * 100
            self.status_label['text'] = message
            self.update()  # 更新 GUI
    
    def on_close(self):
        # GUI 關閉時自動停止 Golang 伺服器
        self.golang_client.stop()
```

#### 4. 部署
```
專案資料夾/
├─ run.py
├─ src/
│   └─ services/
│       ├─ golang_grpc_client.py
│       ├─ classifier_pb2.py          # 自動生成
│       └─ classifier_pb2_grpc.py     # 自動生成
└─ tools/
    └─ golang/
        ├─ classifier.exe              # CLI 版本
        └─ classifier_server.exe       # gRPC 版本
```

**使用者操作**:
1. 解壓縮專案資料夾
2. 雙擊 `run.py`
3. ✅ Python 自動啟動 Golang 背景程序
4. ✅ 使用完畢關閉 GUI → 自動清理

---

## 🔍 Port 管理策略

### 問題：Port 50051 被佔用怎麼辦？

#### 解決方案 1: 動態分配 Port (推薦)

```python
import socket

def find_free_port():
    """找到可用的 Port"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port

class GolangGRPCClient:
    def start(self):
        # 找到可用 Port
        port = find_free_port()
        
        # 啟動時傳入 Port
        self.process = subprocess.Popen(
            ['classifier_server.exe', '--port', str(port)]
        )
        
        # 連線到動態 Port
        self.channel = grpc.insecure_channel(f'localhost:{port}')
```

#### 解決方案 2: 檢查並重試

```python
def start(self, max_retries=3):
    for port in range(50051, 50051 + max_retries):
        try:
            self.process = subprocess.Popen(
                ['classifier_server.exe', '--port', str(port)]
            )
            self.channel = grpc.insecure_channel(f'localhost:{port}')
            # 測試連線
            self.stub.Ping(PingRequest())
            return  # 成功
        except:
            continue
    raise Exception("無法找到可用 Port")
```

---

## ⚖️ CLI vs gRPC 使用時機

### 階段 1: 只用 CLI (建議先這樣)

**適用場景** (80% 功能):
```python
# 批次掃描 - CLI 完全足夠
def batch_scan(folder):
    result = subprocess.run(['classifier.exe', '--scan', folder])
    return parse_json(result.stdout)

# 自動分類 - CLI 完全足夠
def auto_classify(folder):
    result = subprocess.run(['classifier.exe', '--classify', folder])
    return parse_json(result.stdout)
```

**優點**:
- ✅ 零配置
- ✅ 零學習成本
- ✅ 程序隔離安全

**限制**:
- ⚠️ 無法即時顯示進度 (只能事後看結果)
- ⚠️ 無法中途取消操作
- ⚠️ 互動選擇需要多次呼叫 (較慢)

---

### 階段 2: 加入 gRPC (需要時再加)

**適用場景** (20% 進階功能):
```python
# 即時進度顯示 - 需要 gRPC
def scan_with_live_progress(folder):
    for progress in grpc_client.ScanFiles(folder):
        update_progress_bar(progress.percent)  # 即時更新

# 互動式選擇 - 需要 gRPC
def interactive_classify(folder):
    candidates = grpc_client.GetCandidates(folder)  # 快速
    user_choice = show_dialog(candidates)
    result = grpc_client.ApplyChoice(user_choice)  # 快速
```

**優點**:
- ✅ 即時進度 (串流)
- ✅ 低延遲 (<10ms)
- ✅ 可中途取消
- ✅ 雙向通訊

**代價**:
- ⚠️ 需管理程序生命週期
- ⚠️ 需處理 Port 佔用
- ⚠️ 需學習 Protocol Buffers

---

## 📊 部署複雜度比較

| 項目 | CLI | gRPC | 傳統網路伺服器 |
|------|-----|------|---------------|
| **需要安裝** | exe 檔案 | exe 檔案 | 作業系統、框架、函式庫 |
| **網路設定** | 無 | 無 | 防火牆、DNS、SSL |
| **啟動方式** | 直接執行 | Python 自動啟動 | systemd/服務管理 |
| **監控需求** | 無 | 無 | 24/7 監控、日誌 |
| **安全考量** | 檔案權限 | localhost only | 網路安全、認證 |
| **用戶技能** | 無要求 | 無要求 | 系統管理員 |

---

## 🎯 針對您的情況的建議

### 您的環境
- ✅ **本地端資料** (D:\女優分類)
- ✅ **Windows 桌面應用程式**
- ✅ **單使用者**
- ✅ **無需網路存取**

### 推薦實施計畫

#### **第 1 階段: CLI Only (強烈推薦先這樣)**

**時間**: 2-3 週  
**投資**: $5,000  
**部署**: 零配置

```
部署清單:
├─ tools/golang/classifier.exe  (編譯好的執行檔)
└─ 修改 Python 程式碼呼叫 CLI

使用者體驗:
1. 解壓縮資料夾
2. 雙擊 run.py
3. ✅ 完成！ (速度提升 5-10x)
```

**決策點**: 
- ✅ 如果 CLI 已滿足需求 → **停在這裡**，省下 $7,500
- ⚠️ 如果需要即時進度/互動功能 → 進入階段 2

---

#### **第 2 階段: 加入 gRPC (可選)**

**時間**: 2-3 週  
**額外投資**: $5,000  
**部署**: Python 自動管理

```
額外部署清單:
├─ tools/golang/classifier_server.exe
├─ src/services/classifier_pb2.py
└─ src/services/golang_grpc_client.py

使用者體驗:
1. 解壓縮資料夾
2. 雙擊 run.py
3. ✅ Python 自動啟動 Golang 背景程序
4. ✅ 即時進度顯示
5. 關閉 GUI → 自動清理
```

**需要配置的項目**:
- Port 管理 (程式碼自動處理)
- 程序生命週期 (Python 自動管理)
- **完全不需要手動設定**

---

## ❓ 常見問題

### Q1: gRPC 需要網路連線嗎？
**A**: 不需要！只在本機 `localhost` 通訊，不經過網路卡。

### Q2: 使用者需要開放防火牆嗎？
**A**: 不需要！只監聽 `127.0.0.1` (本機)，防火牆不會阻擋。

### Q3: 需要管理員權限嗎？
**A**: 不需要！Port 50051 不需要特殊權限。

### Q4: 如何確保 Golang 程序不會殘留？
**A**: Python 使用 `atexit` 註冊清理函式，GUI 關閉時自動終止。

### Q5: 多個 Python 程序可以同時執行嗎？
**A**: 可以！每個 Python 程序啟動自己的 Golang 伺服器 (不同 Port)。

### Q6: 效能比較？
```
CLI 模式:
- 啟動開銷: ~50-100ms (程序啟動)
- 單次呼叫: 50-100ms
- 適合: 批次操作

gRPC 模式:
- 啟動開銷: ~500ms (一次性)
- 單次呼叫: <10ms
- 適合: 頻繁互動
```

### Q7: 如果我只有 1,000 部影片，需要 gRPC 嗎？
**A**: **不需要**！CLI 已經足夠，可省下 $5,000。

---

## 🏁 總結

### ✅ 您的情況完全不需要「架伺服器」

| 項目 | 傳統伺服器 | 您的方案 (gRPC) |
|------|-----------|----------------|
| 部署位置 | 雲端 (AWS/Azure) | **本地端電腦** |
| 網路設定 | 需要 (DNS/SSL/防火牆) | **不需要 (localhost only)** |
| 啟動方式 | 手動/服務管理 | **Python 自動啟動** |
| 運行模式 | 24/7 | **GUI 開啟時才運行** |
| 使用者技能 | 系統管理員 | **零技能 (雙擊執行)** |
| 維護成本 | 高 (監控/更新) | **零 (本地程式)** |

### 🎯 建議行動方案

1. **立即開始**: 階段 1 - CLI 工具
   - 2-3 週開發
   - $5,000 投資
   - 零部署成本
   - 立即驗證 5-10x 效能提升

2. **評估後決策**: 是否需要階段 2
   - 如果 CLI 足夠 → 停止，省下 $7,500
   - 如果需要即時進度 → 加入 gRPC (也是本地程序)

3. **完全不需要擔心**:
   - ❌ 租用雲端伺服器
   - ❌ 學習網路管理
   - ❌ 設定防火牆
   - ❌ 申請網域名稱

---

需要我：
1. ✅ **更新規格書，明確標示「本地程序通訊」**
2. 📝 建立詳細的 Python-Golang 整合程式碼範例
3. 🔧 建立 Port 動態分配的完整實作

請告訴我！
