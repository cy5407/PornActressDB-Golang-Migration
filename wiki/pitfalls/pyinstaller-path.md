---
category: Python
date: 2026-04-06
---
# PyInstaller 打包路徑問題

**日期**：2026-04-06
**症狀**：打包後的 EXE 片商顯示全部 UNKNOWN，但開發環境正常
**根因**：`Path("studios.json")` 讀取的是 CWD（dist/）的外部舊版，而非打包進 EXE 的版本

## 修正

```python
# src/models/studio.py
def _resolve_resource_path(filename: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / filename  # PyInstaller 打包環境
    return Path(__file__).parent.parent.parent / filename  # 開發環境

rules_file = _resolve_resource_path("studios.json")
```

## dist 同步提醒

Rebuild EXE 後必須手動：
```bash
Copy-Item classifier.exe dist\classifier.exe -Force
Copy-Item studios.json dist\studios.json -Force
```

`dist/studios.json` 是 EXE 外部的 fallback（正常不會用到），但保持同步可避免混淆。
