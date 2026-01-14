"""
統一的 sys.path 設定工具

用於工具腳本和測試腳本，確保正確匯入專案模組。
主程式 (run.py) 和 src/ 下的模組不應使用此工具。
"""

import sys
from pathlib import Path


def setup_project_paths(calling_file: str) -> Path:
    """
    設定專案路徑，使工具腳本能正確匯入 src/ 下的模組

    Args:
        calling_file: 呼叫腳本的 __file__ 變數

    Returns:
        專案根目錄的 Path 物件

    使用範例:
        # 在 tools/xxx/script.py 中
        from utils.path_setup import setup_project_paths
        project_root = setup_project_paths(__file__)

        # 現在可以匯入 src/ 下的模組
        from models.config import ConfigManager
    """
    calling_path = Path(calling_file).resolve()

    # 向上尋找專案根目錄（包含 run.py 的目錄）
    current = calling_path.parent
    project_root = None

    # 最多向上搜尋 5 層
    for _ in range(5):
        if (current / "run.py").exists():
            project_root = current
            break
        current = current.parent

    if project_root is None:
        raise RuntimeError(
            f"無法找到專案根目錄（從 {calling_path} 開始搜尋）\n"
            "請確保腳本位於專案目錄結構中"
        )

    # 將 src/ 加入路徑（如果尚未加入）
    src_path = str(project_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    return project_root


def get_project_root(calling_file: str) -> Path:
    """
    僅取得專案根目錄，不修改 sys.path

    Args:
        calling_file: 呼叫腳本的 __file__ 變數

    Returns:
        專案根目錄的 Path 物件
    """
    calling_path = Path(calling_file).resolve()
    current = calling_path.parent

    for _ in range(5):
        if (current / "run.py").exists():
            return current
        current = current.parent

    raise RuntimeError(
        f"無法找到專案根目錄（從 {calling_path} 開始搜尋）"
    )
