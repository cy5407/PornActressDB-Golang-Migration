"""
Go CLI 橋接層 - 統一呼叫 classifier.exe 的介面

此模組提供 Python 與 Go CLI 之間的橋接，讓 Python 程式可以透過
subprocess 呼叫 classifier.exe 執行效能敏感的操作。

功能：
- scan_directory(): 掃描目錄提取番號
- move_file(): 移動單一檔案
- batch_move(): 批次移動檔案
- list_operations(): 列出操作歷史
- rollback(): 回滾操作

使用範例：
    from services.go_bridge import GoBridge
    
    bridge = GoBridge()
    
    # 掃描目錄
    results = bridge.scan_directory("D:\\Videos")
    
    # 移動檔案
    result = bridge.move_file("source.mp4", "dest/source.mp4")
    
    # 批次移動
    items = [
        {"source": "a.mp4", "destination": "dest/a.mp4"},
        {"source": "b.mp4", "destination": "dest/b.mp4"},
    ]
    result = bridge.batch_move(items)
"""

import json
import logging
import os
import platform  # 用於跨平台執行權限檢查
import subprocess  # 僅供型別註記使用
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from src.services.go_runner import GoBridgeError, GoCommandRunner, run_subprocess
except ImportError:
    from services.go_runner import GoBridgeError, GoCommandRunner, run_subprocess

logger = logging.getLogger(__name__)


def _cleanup_temp_file(path: str | None, context: str) -> None:
    """清理暫存檔，避免清理失敗覆蓋主流程結果。"""
    if not path:
        return

    try:
        os.unlink(path)
    except FileNotFoundError:
        return
    except Exception as e:
        logger.warning(f"⚠️ 無法清理 {context} 暫存檔 {path}: {e}")


@dataclass
class ScanResult:
    """掃描結果"""
    path: str
    code: str


@dataclass
class MoveResult:
    """移動結果"""
    source: str
    destination: str
    success: bool
    error: Optional[str] = None
    skipped: bool = False
    renamed: Optional[str] = None


@dataclass
class BatchMoveResult:
    """批次移動結果"""
    operation_id: Optional[str]
    total_items: int
    success_count: int
    failed_count: int
    skipped_count: int
    results: list[MoveResult]
    status: str
    summary: str
    duration: str


@dataclass
class OperationLog:
    """操作日誌"""
    id: str
    timestamp: str
    type: str
    status: str
    items: list[dict]
    total_items: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0

class GoBridge:
    """
    Go CLI 橋接層
    
    提供 Python 與 classifier.exe 之間的介面。
    自動偵測 exe 位置，支援 fallback 機制。
    """
    
    def __init__(
        self,
        exe_path: Optional[str] = None,
        log_dir: str = "logs",
        default_workers: int = 10,
        default_strategy: str = "skip",
    ):
        """
        初始化 Go 橋接層
        
        Args:
            exe_path: classifier.exe 路徑，留空自動偵測
            log_dir: 操作日誌目錄
            default_workers: 預設掃描並發數
            default_strategy: 預設衝突策略 (skip, overwrite, rename)
        """
        self.exe_path = exe_path or self._find_exe()
        self.log_dir = log_dir
        self.default_workers = default_workers
        self.default_strategy = default_strategy
        self._available = None  # 延遲檢查
        self._runner = GoCommandRunner(self.exe_path)
        
        logger.debug(f"GoBridge 初始化: exe_path={self.exe_path}")
    
    def _find_exe(self) -> str:
        """自動偵測 classifier.exe 位置"""
        # 搜尋順序：
        # 1. 專案根目錄
        # 2. 當前目錄
        # 3. PATH 環境變數
        
        possible_paths = [
            # PyInstaller 打包後的解壓目錄 (sys._MEIPASS)
            Path(getattr(sys, "_MEIPASS", "")) / "classifier.exe",
            # 專案根目錄 (相對於此檔案)
            Path(__file__).parent.parent.parent / "classifier.exe",
            # 當前工作目錄
            Path.cwd() / "classifier.exe",
            # Windows 系統路徑
            Path(os.environ.get("PROGRAMFILES", "")) / "classifier" / "classifier.exe",
        ]
        
        for path in possible_paths:
            if path.exists():
                resolved = str(path.resolve())
                # Linux/macOS 需額外確認執行權限（Windows 上 os.X_OK 行為不一致，僅檢查存在性）
                if platform.system() != "Windows" and not os.access(resolved, os.X_OK):
                    logger.warning(
                        f"⚠️ 找到 {resolved} 但缺少執行權限（+x），"
                        "請執行 `chmod +x <path>` 後重試"
                    )
                    continue  # 跳過無執行權限的路徑
                logger.info(f"🔍 找到 classifier.exe: {resolved}")
                return resolved
        
        # 嘗試在 PATH 中找
        import shutil
        exe_in_path = shutil.which("classifier.exe") or shutil.which("classifier")
        if exe_in_path:
            # shutil.which 本身已隱含執行權限檢查，此處無需再次驗證
            logger.info(f"🔍 在 PATH 中找到: {exe_in_path}")
            return exe_in_path
        
        logger.warning("⚠️ 找不到 classifier.exe，Go 加速功能將不可用")
        return "classifier.exe"  # 返回預設名稱，讓後續檢查失敗
    
    @property
    def is_available(self) -> bool:
        """檢查 Go CLI 是否可用"""
        if self._available is None:
            self._available = self._check_availability()
        return self._available
    
    def _check_availability(self) -> bool:
        """實際檢查 Go CLI 是否可用"""
        try:
            result = self._runner.run(["help"], timeout=5, check=False)
            available = result.returncode == 0
            if available:
                logger.info("✅ Go CLI 可用")
            else:
                logger.warning(f"⚠️ Go CLI 執行失敗: {result.stderr}")
            return available
        except GoBridgeError as e:
            logger.warning(f"⚠️ Go CLI 檢查失敗: {e}")
            return False
    
    def _run_command(
        self,
        args: list[str],
        timeout: int = 60,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        執行 Go CLI 命令
        
        Args:
            args: 命令參數（不含 exe 路徑）
            timeout: 超時秒數
            check: 是否檢查返回碼
        
        Returns:
            subprocess.CompletedProcess
        
        Raises:
            GoBridgeError: 執行失敗時
        """
        return self._runner.run(args, timeout=timeout, check=check)
    
    def _parse_json(self, output: str) -> dict | list:
        """解析 JSON 輸出"""
        return self._runner.parse_json(output)

    def _run_json(
        self,
        args: list[str],
        timeout: int = 60,
        check: bool = True,
    ) -> dict | list:
        """執行命令並直接回傳解析後的 JSON。"""
        return self._runner.run_json(args, timeout=timeout, check=check)

    def _build_batch_move_result(
        self,
        data: dict,
        default_total_items: int = 0,
    ) -> BatchMoveResult:
        results = [
            MoveResult(
                source=r.get("source", ""),
                destination=r.get("destination", ""),
                success=r.get("success", False),
                error=r.get("error"),
                skipped=r.get("skipped", False),
                renamed=r.get("renamed"),
            )
            for r in data.get("results", [])
        ]

        return BatchMoveResult(
            operation_id=data.get("operation_id"),
            total_items=data.get("total_items", default_total_items),
            success_count=data.get("success_count", 0),
            failed_count=data.get("failed_count", 0),
            skipped_count=data.get("skipped_count", 0),
            results=results,
            status=data.get("status", ""),
            summary=data.get("summary", ""),
            duration=data.get("duration", ""),
        )

    def _build_operation_log(
        self,
        data: dict,
        default_operation_id: str = "",
    ) -> OperationLog:
        return OperationLog(
            id=data.get("id", default_operation_id),
            timestamp=data.get("timestamp", ""),
            type=self._normalize_operation_type(data.get("type", "")),
            status=data.get("status", ""),
            items=data.get("items", []),
            total_items=data.get("total_items", len(data.get("items", []))),
            success_count=data.get("success_count", 0),
            failed_count=data.get("failed_count", 0),
            skipped_count=data.get("skipped_count", 0),
        )
    
    # === 掃描功能 ===
    
    def scan_directory(
        self,
        directory: str,
        workers: Optional[int] = None,
        recursive: bool = True,
    ) -> list[ScanResult]:
        """
        掃描目錄中的影片檔案，提取番號
        
        Args:
            directory: 要掃描的目錄路徑
            workers: 並發工作數（預設使用 default_workers）
            recursive: 是否遞迴掃描子目錄（預設 True）
        
        Returns:
            list[ScanResult]: 掃描結果列表
        
        Raises:
            GoBridgeError: 掃描失敗時
        """
        workers = workers or self.default_workers
        
        args = ["scan", "-dir", directory, "-workers", str(workers)]
        if not recursive:
            args.append("-recursive=false")
        
        data = self._run_json(args)
        
        return [
            ScanResult(path=item["path"], code=item["code"])
            for item in data
        ]
    
    # === 檔案移動功能 ===
    
    def move_file(
        self,
        source: str,
        destination: str,
        strategy: Optional[str] = None,
        dry_run: bool = False,
    ) -> MoveResult:
        """
        移動單一檔案
        
        Args:
            source: 來源路徑
            destination: 目標路徑
            strategy: 衝突策略 (skip, overwrite, rename)
            dry_run: 模擬執行模式
        
        Returns:
            MoveResult: 移動結果
        
        Raises:
            GoBridgeError: 移動失敗時
        """
        strategy = strategy or self.default_strategy
        
        args = [
            "move",
            "-src", source,
            "-dst", destination,
            "-strategy", strategy,
            "-log-dir", self.log_dir,
        ]
        
        if dry_run:
            args.append("-dry-run")
        
        data = self._run_json(args, check=False)
        
        return MoveResult(
            source=data.get("source", source),
            destination=data.get("destination", destination),
            success=data.get("success", False),
            error=data.get("error"),
            skipped=data.get("skipped", False),
            renamed=data.get("renamed"),
        )

    def move_dir(
        self,
        source: str,
        destination: str,
        strategy: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict:
        """移動整個目錄。"""
        strategy = strategy or self.default_strategy

        args = [
            "move",
            "-kind", "dir",
            "-src", source,
            "-dst", destination,
            "-strategy", strategy,
            "-log-dir", self.log_dir,
        ]

        if dry_run:
            args.append("-dry-run")

        result = self._run_command(args, check=False)
        data = self._parse_json(result.stdout)

        return {
            "source": data.get("source_dir", source),
            "destination": data.get("dest_dir", destination),
            "success": data.get("success", False),
            "files_moved": data.get("files_moved", 0),
            "files_total": data.get("files_total", 0),
            "deleted_source": data.get("deleted_src", False),
            "errors": data.get("errors", []),
            "error": "; ".join(
                err.get("error", "")
                for err in data.get("errors", [])
                if err.get("error")
            ) or None,
            "skipped": False,
        }
    
    def batch_move(
        self,
        items: list[dict],
        strategy: Optional[str] = None,
        dry_run: bool = False,
    ) -> BatchMoveResult:
        """
        批次移動檔案
        
        Args:
            items: 移動項目列表，每個項目包含 source 和 destination
            strategy: 衝突策略 (skip, overwrite, rename)
            dry_run: 模擬執行模式
        
        Returns:
            BatchMoveResult: 批次移動結果
        
        Raises:
            GoBridgeError: 移動失敗時
        
        Example:
            items = [
                {"source": "a.mp4", "destination": "dest/a.mp4"},
                {"source": "b.mp4", "destination": "dest/b.mp4"},
            ]
            result = bridge.batch_move(items)
        """
        strategy = strategy or self.default_strategy
        
        # 建立暫存 JSON 檔案
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as f:
            # 設定預設衝突策略
            for item in items:
                if "on_conflict" not in item:
                    item["on_conflict"] = strategy
            
            json.dump(items, f, ensure_ascii=False, indent=2)
            batch_file = f.name
        
        try:
            args = [
                "move",
                "-batch", batch_file,
                "-log-dir", self.log_dir,
            ]
            
            if dry_run:
                args.append("-dry-run")

            result = self._run_command(args, check=False, timeout=300)
            if result.returncode != 0:
                error_msg = result.stderr.strip() or f"命令失敗，返回碼: {result.returncode}"
                raise GoBridgeError(error_msg)
            data = self._parse_json(result.stdout)
            return self._build_batch_move_result(data, default_total_items=len(items))
            
        finally:
            _cleanup_temp_file(batch_file, "batch_move")

    def _normalize_operation_type(self, operation_type: str) -> str:
        """正規化操作類型，保留舊日誌相容性。"""
        if operation_type == "move_batch":
            return "batch_move"
        return operation_type
    
    # === 操作歷史功能 ===
    
    def list_operations(self, limit: Optional[int] = None) -> list[OperationLog]:
        """
        列出操作歷史
        
        Returns:
            list[OperationLog]: 操作日誌列表
        """
        args = ["history", "list", "-log-dir", self.log_dir, "-json"]

        try:
            result = self._run_command(args, check=False)
            if result.returncode != 0:
                raise GoBridgeError(
                    result.stderr.strip() or f"命令失敗，返回碼: {result.returncode}"
                )

            data = self._parse_json(result.stdout)
            logs = [self._build_operation_log(item) for item in data]

            if limit is not None:
                return logs[:limit]
            return logs
             
        except GoBridgeError:
            return []
    
    def get_operation(self, operation_id: str) -> Optional[OperationLog]:
        """
        取得指定操作的詳細資訊
        
        Args:
            operation_id: 操作 ID
        
        Returns:
            OperationLog 或 None
        """
        args = ["history", "show", "-log-dir", self.log_dir, "-json", operation_id]
        
        try:
            result = self._run_command(args)
            data = self._parse_json(result.stdout)
            return self._build_operation_log(data, default_operation_id=operation_id)
             
        except GoBridgeError:
            return None
    
    def rollback(self, operation_id: str) -> BatchMoveResult:
        """
        回滾指定的操作
        
        Args:
            operation_id: 操作 ID，或 "--last" 回滾最近一次
        
        Returns:
            BatchMoveResult: 回滾結果
        
        Raises:
            GoBridgeError: 回滾失敗時
        """
        args = ["history", "rollback", "-log-dir", self.log_dir, "-json", operation_id]

        result = self._run_command(args, check=False)
        if result.returncode != 0:
            error_msg = result.stderr.strip() or f"命令失敗，返回碼: {result.returncode}"
            raise GoBridgeError(error_msg)
        data = self._parse_json(result.stdout)
        return self._build_batch_move_result(data)
    
    def rollback_last(self) -> BatchMoveResult:
        """回滾最近一次操作"""
        return self.rollback("--last")


# === 便捷函式 ===

_default_bridge: Optional[GoBridge] = None


def get_bridge() -> GoBridge:
    """取得預設的 GoBridge 實例（單例）"""
    global _default_bridge
    if _default_bridge is None:
        _default_bridge = GoBridge()
    return _default_bridge


def scan_directory_go(directory: str, workers: int = 10) -> list[dict]:
    """
    便捷函式：掃描目錄
    
    向後相容 go_integration.py 的介面
    """
    bridge = get_bridge()
    results = bridge.scan_directory(directory, workers)
    return [{"path": r.path, "code": r.code} for r in results]


def move_file_go(source: str, destination: str, strategy: str = "skip") -> dict:
    """便捷函式：移動檔案"""
    bridge = get_bridge()
    result = bridge.move_file(source, destination, strategy)
    return {
        "source": result.source,
        "destination": result.destination,
        "success": result.success,
        "error": result.error,
        "skipped": result.skipped,
        "renamed": result.renamed,
    }


try:
    from src.services.go_api.db import (
        db_compact_journal,
        db_delete_video,
        db_get_stats,
        db_get_video,
        db_list_videos,
        db_update_video,
    )
    from src.services.go_api.identify import (
        get_studio_prefixes,
        identify_studio,
        identify_studios_batch,
        list_studios,
    )
except ImportError:
    from services.go_api.db import (
        db_compact_journal,
        db_delete_video,
        db_get_stats,
        db_get_video,
        db_list_videos,
        db_update_video,
    )
    from services.go_api.identify import (
        get_studio_prefixes,
        identify_studio,
        identify_studios_batch,
        list_studios,
    )
