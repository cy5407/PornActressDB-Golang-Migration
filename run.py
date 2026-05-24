"""
女優分類系統 v6.0.0 - Wails 版主進入點

本程式已遷移至 Wails (Go + React) 桌面應用程式。
請直接執行 actress-classifier.exe 啟動應用程式。

此 run.py 保留作為：
1. 啟動 Wails 執行檔的捷徑
2. 直接呼叫 Python 爬蟲（開發用）的入口
"""

import subprocess
import sys
from pathlib import Path


def _find_wails_exe() -> Path | None:
    """尋找 Wails 編譯後的執行檔。"""
    root = Path(__file__).parent
    candidates = [
        root / "actress-classifier.exe",  # Windows
        root / "actress-classifier",       # Linux/Mac
        root / "wails-app" / "build" / "bin" / "actress-classifier.exe",
        root / "wails-app" / "build" / "bin" / "actress-classifier",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


if __name__ == "__main__":
    exe = _find_wails_exe()
    if exe:
        print(f"🚀 啟動女優分類系統 Wails 版: {exe}")
        try:
            subprocess.run([str(exe)], check=True)
        except KeyboardInterrupt:
            pass
        except subprocess.CalledProcessError as e:
            print(f"❌ 程式異常結束 (code {e.returncode})")
            sys.exit(e.returncode)
    else:
        print("❌ 找不到 actress-classifier.exe")
        print()
        print("請先執行以下指令建置 Wails 應用程式：")
        print("  cd wails-app")
        print("  wails build")
        print()
        print("或參考 README.md 的快速開始說明。")
        sys.exit(1)
