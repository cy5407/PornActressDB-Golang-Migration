# CLI Interface Specification

**Feature**: 分類功能 Golang 遷移  
**Date**: 2025-10-18  
**Purpose**: 定義命令列介面規格，供 Python 整合層呼叫

---

## 概述

Golang classifier CLI 提供三個主要命令：
1. `scan` - 掃描檔案並提取番號
2. `classify-actress` - 女優資料夾分類
3. `classify-studio` - 片商資料夾分類

所有命令輸出標準化 JSON 格式，透過 stdout 返回結果，透過 stderr 輸出日誌。

---

## 通用參數

所有命令支援以下通用參數：

```bash
--help, -h          # 顯示幫助資訊
--version, -v       # 顯示版本號
--verbose           # 啟用詳細日誌 (輸出到 stderr)
--quiet             # 靜默模式 (僅輸出 JSON 結果)
--log-file <path>   # 日誌檔案路徑 (預設: 不寫檔案)
```

---

## 命令 1: scan - 掃描檔案

### 用途
掃描指定資料夾中的影片檔案，提取番號並生成統計報告。

### 語法
```bash
classifier scan --folder <path> [options]
```

### 參數

| 參數 | 簡寫 | 必填 | 類型 | 預設值 | 說明 |
|------|------|------|------|--------|------|
| `--folder` | `-f` | ✅ | string | - | 要掃描的資料夾路徑 |
| `--recursive` | `-r` | ❌ | bool | false | 遞迴掃描子資料夾 |
| `--format` | - | ❌ | string | json | 輸出格式: json, jsonl, table |
| `--extensions` | `-e` | ❌ | string | mp4,mkv,avi,mov,wmv | 支援的副檔名 (逗號分隔) |
| `--workers` | `-w` | ❌ | int | CPU 核心數 | 並行 worker 數量 (最大 8) |
| `--output` | `-o` | ❌ | string | - | 輸出檔案路徑 (預設: stdout) |

### 輸出 (JSON 格式)

```json
{
  "total_files": 10000,
  "success_count": 9500,
  "failed_files": [
    "/path/to/failed1.mp4",
    "/path/to/failed2.mkv"
  ],
  "duration_ms": 25000,
  "timestamp": "2025-10-18T10:30:00Z",
  "video_files": [
    {
      "path": "/path/to/SONE-123.mp4",
      "name": "SONE-123.mp4",
      "size": 4294967296,
      "code": "SONE-123",
      "scanned": true,
      "error": ""
    },
    {
      "path": "/path/to/invalid.mp4",
      "name": "invalid.mp4",
      "size": 1048576,
      "code": "",
      "scanned": true,
      "error": "no video code found"
    }
  ]
}
```

### 輸出 (JSONL 格式) - 適合大資料集

每行一個 JSON 物件：
```jsonl
{"type":"progress","processed":100,"total":10000,"percentage":1.0}
{"type":"file","path":"/path/to/SONE-123.mp4","code":"SONE-123","size":4294967296}
{"type":"file","path":"/path/to/STARS-456.mkv","code":"STARS-456","size":3221225472}
...
{"type":"summary","total_files":10000,"success_count":9500,"duration_ms":25000}
```

### 退出碼

| 碼 | 說明 |
|----|------|
| 0 | 成功 |
| 1 | 一般錯誤 (詳見 stderr) |
| 2 | 無效參數 |
| 3 | 資料夾不存在或無權限 |

### 範例

```bash
# 基本掃描
classifier scan --folder /path/to/videos

# 遞迴掃描，輸出到檔案
classifier scan -f /path/to/videos -r -o scan_result.json

# 使用 4 個 workers
classifier scan -f /path/to/videos -w 4

# 僅掃描 mp4 和 mkv
classifier scan -f /path/to/videos -e mp4,mkv

# JSONL 格式 (適合串流處理)
classifier scan -f /path/to/videos --format jsonl
```

---

## 命令 2: classify-actress - 女優資料夾分類

### 用途
將影片檔案根據女優資訊移動到對應的女優資料夾。

### 語法
```bash
classifier classify-actress --folder <path> [options]
```

### 參數

| 參數 | 簡寫 | 必填 | 類型 | 預設值 | 說明 |
|------|------|------|------|--------|------|
| `--folder` | `-f` | ✅ | string | - | 來源資料夾路徑 |
| `--target` | `-t` | ❌ | string | <folder>/classified | 目標根資料夾 |
| `--mode` | `-m` | ❌ | string | auto | 模式: auto (僅單女優), all (所有) |
| `--conflict` | `-c` | ❌ | string | ask | 衝突策略: ask, skip, overwrite, rename |
| `--database` | `-d` | ❌ | string | data.json | 資料庫檔案路徑 |
| `--workers` | `-w` | ❌ | int | 4 | 並行 worker 數量 |
| `--dry-run` | - | ❌ | bool | false | 模擬執行 (不實際移動) |

### 輸出 (JSON 格式)

```json
{
  "total_videos": 1000,
  "moved": 950,
  "skipped": 30,
  "failed": 20,
  "duration_ms": 45000,
  "timestamp": "2025-10-18T10:35:00Z",
  "operations": [
    {
      "source_path": "/path/to/SONE-123.mp4",
      "target_path": "/path/to/classified/女優A/SONE-123.mp4",
      "operation_type": "auto",
      "status": "success",
      "actress_name": "女優A",
      "file_size": 4294967296
    },
    {
      "source_path": "/path/to/STARS-456.mkv",
      "target_path": "",
      "operation_type": "auto",
      "status": "skipped",
      "error_message": "multiple actresses, manual selection needed",
      "file_size": 3221225472
    }
  ]
}
```

### 退出碼

| 碼 | 說明 |
|----|------|
| 0 | 成功 |
| 1 | 一般錯誤 |
| 2 | 無效參數 |
| 3 | 資料夾不存在或無權限 |
| 4 | 資料庫檔案不存在或無效 |
| 5 | 磁碟空間不足 |

### 範例

```bash
# 自動分類單女優影片
classifier classify-actress --folder /path/to/videos

# 指定目標資料夾
classifier classify-actress -f /source -t /target/actresses

# 跳過衝突
classifier classify-actress -f /source -c skip

# 模擬執行 (不實際移動)
classifier classify-actress -f /source --dry-run

# 覆蓋同名檔案
classifier classify-actress -f /source -c overwrite

# 使用自訂資料庫
classifier classify-actress -f /source -d custom_data.json
```

---

## 命令 3: classify-studio - 片商資料夾分類

### 用途
分析女優資料夾的片商分佈，將女優資料夾移動到對應片商資料夾。

### 語法
```bash
classifier classify-studio --folder <path> [options]
```

### 參數

| 參數 | 簡寫 | 必填 | 類型 | 預設值 | 說明 |
|------|------|------|------|--------|------|
| `--folder` | `-f` | ✅ | string | - | 女優資料夾根目錄 |
| `--target` | `-t` | ❌ | string | <folder>/studios | 目標根資料夾 |
| `--threshold` | - | ❌ | float | 0.7 | 信心度閾值 (0.5-0.9) |
| `--workers` | `-w` | ❌ | int | 4 | 並行 worker 數量 |
| `--database` | `-d` | ❌ | string | data.json | 資料庫檔案路徑 |
| `--dry-run` | - | ❌ | bool | false | 模擬執行 (不實際移動) |
| `--report` | - | ❌ | bool | false | 僅生成報告，不移動 |

### 輸出 (JSON 格式)

```json
{
  "total_actresses": 100,
  "classified": 85,
  "solo_actress": 15,
  "duration_ms": 20000,
  "timestamp": "2025-10-18T10:40:00Z",
  "statistics": [
    {
      "actress_name": "女優A",
      "studio_distribution": {
        "S1": 120,
        "MOODYZ": 30
      },
      "primary_studio": "S1",
      "confidence": 0.8,
      "recommended_class": "S1",
      "total_videos": 150
    },
    {
      "actress_name": "女優B",
      "studio_distribution": {
        "S1": 20,
        "MOODYZ": 15,
        "IDEA POCKET": 10
      },
      "primary_studio": "S1",
      "confidence": 0.44,
      "recommended_class": "SOLO_ACTRESS",
      "total_videos": 45
    }
  ],
  "operations": [
    {
      "source_path": "/path/to/actresses/女優A",
      "target_path": "/path/to/studios/S1/女優A",
      "status": "success"
    }
  ]
}
```

### 退出碼

| 碼 | 說明 |
|----|------|
| 0 | 成功 |
| 1 | 一般錯誤 |
| 2 | 無效參數 (例如: threshold 超出範圍) |
| 3 | 資料夾不存在或無權限 |
| 4 | 資料庫檔案不存在或無效 |

### 範例

```bash
# 使用預設閾值 (70%)
classifier classify-studio --folder /path/to/actresses

# 調整閾值為 80%
classifier classify-studio -f /actresses --threshold 0.8

# 僅生成報告，不移動
classifier classify-studio -f /actresses --report

# 模擬執行
classifier classify-studio -f /actresses --dry-run

# 指定目標資料夾和並行度
classifier classify-studio -f /actresses -t /studios -w 8
```

---

## 日誌格式 (stderr)

### 日誌級別

- `DEBUG`: 詳細除錯資訊 (僅在 --verbose 時輸出)
- `INFO`: 一般資訊 (進度更新、操作確認)
- `WARN`: 警告 (非致命錯誤、跳過的檔案)
- `ERROR`: 錯誤 (失敗的操作)

### 日誌格式

```
2025-10-18T10:30:00Z [INFO] Starting scan operation: folder=/path/to/videos
2025-10-18T10:30:05Z [INFO] Scanned 1000 files, 950 success, 50 failed
2025-10-18T10:30:10Z [WARN] Failed to extract code from: /path/to/invalid.mp4
2025-10-18T10:30:15Z [INFO] Scan complete: 10000 files in 25s
2025-10-18T10:30:15Z [ERROR] Failed to move file: /path/to/SONE-123.mp4 -> permission denied
```

---

## 錯誤處理

### 錯誤訊息格式 (stderr)

```json
{
  "error": "failed to scan folder",
  "details": "permission denied: /path/to/videos",
  "timestamp": "2025-10-18T10:30:00Z"
}
```

### 常見錯誤

| 錯誤碼 | 錯誤訊息 | 原因 | 解決方案 |
|--------|---------|------|---------|
| 1 | "failed to scan folder" | 資料夾不存在或無權限 | 檢查路徑和權限 |
| 2 | "invalid argument" | 參數格式錯誤 | 檢查命令語法 |
| 3 | "database not found" | 資料庫檔案不存在 | 指定正確的資料庫路徑 |
| 4 | "insufficient disk space" | 磁碟空間不足 | 清理空間或選擇其他目標 |
| 5 | "failed to acquire lock" | 資料庫被其他程序鎖定 | 等待其他操作完成 |

---

## Python 整合範例

### 基本呼叫

```python
import subprocess
import json

def scan_folder(folder: str) -> dict:
    result = subprocess.run(
        ["classifier", "scan", "-f", folder, "--format", "json"],
        capture_output=True,
        text=True,
        check=True
    )
    return json.loads(result.stdout)

# 使用
scan_result = scan_folder("/path/to/videos")
print(f"掃描完成: {scan_result['success_count']}/{scan_result['total_files']}")
```

### 錯誤處理

```python
try:
    result = subprocess.run(
        ["classifier", "classify-actress", "-f", folder],
        capture_output=True,
        text=True,
        check=True,
        timeout=300
    )
    data = json.loads(result.stdout)
except subprocess.CalledProcessError as e:
    print(f"錯誤: {e.stderr}")
    sys.exit(1)
except subprocess.TimeoutExpired:
    print("操作超時")
    sys.exit(1)
```

### 即時進度 (JSONL)

```python
import subprocess

process = subprocess.Popen(
    ["classifier", "scan", "-f", folder, "--format", "jsonl"],
    stdout=subprocess.PIPE,
    text=True
)

for line in process.stdout:
    data = json.loads(line)
    if data["type"] == "progress":
        print(f"進度: {data['percentage']:.1f}%")
    elif data["type"] == "file":
        print(f"掃描: {data['path']}")
```

---

## 效能考量

### 建議並行度

| 檔案數量 | 建議 workers |
|---------|-------------|
| < 1,000 | 2 |
| 1,000 - 10,000 | 4 |
| 10,000 - 50,000 | 8 |
| > 50,000 | 8 (受磁碟 I/O 限制) |

### 記憶體使用

- 每 10,000 檔案約使用 50MB 記憶體
- 最大記憶體限制: 500MB (處理 50,000 檔案)

### 超時建議

| 操作 | 建議超時 (秒) |
|------|-------------|
| scan | 300 (5 分鐘) |
| classify-actress | 600 (10 分鐘) |
| classify-studio | 300 (5 分鐘) |

---

**版本**: 1.0  
**更新日期**: 2025-10-18  
**狀態**: ✅ 已審核，可用於實作
