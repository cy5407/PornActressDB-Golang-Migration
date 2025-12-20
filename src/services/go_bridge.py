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
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


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
    total_items: int
    success_count: int
    failed_count: int
    skipped_count: int
    results: list[MoveResult]
    duration: str


@dataclass
class OperationLog:
    """操作日誌"""
    id: str
    timestamp: str
    type: str
    status: str
    items: list[dict]


class GoBridgeError(Exception):
    """Go 橋接層錯誤"""
    pass


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
        
        logger.debug(f"GoBridge 初始化: exe_path={self.exe_path}")
    
    def _find_exe(self) -> str:
        """自動偵測 classifier.exe 位置"""
        # 搜尋順序：
        # 1. 專案根目錄
        # 2. 當前目錄
        # 3. PATH 環境變數
        
        possible_paths = [
            # 專案根目錄 (相對於此檔案)
            Path(__file__).parent.parent.parent / "classifier.exe",
            # 當前工作目錄
            Path.cwd() / "classifier.exe",
            # Windows 系統路徑
            Path(os.environ.get("PROGRAMFILES", "")) / "classifier" / "classifier.exe",
        ]
        
        for path in possible_paths:
            if path.exists():
                logger.info(f"🔍 找到 classifier.exe: {path}")
                return str(path.resolve())
        
        # 嘗試在 PATH 中找
        import shutil
        exe_in_path = shutil.which("classifier.exe") or shutil.which("classifier")
        if exe_in_path:
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
            result = subprocess.run(
                [self.exe_path, "help"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            available = result.returncode == 0
            if available:
                logger.info("✅ Go CLI 可用")
            else:
                logger.warning(f"⚠️ Go CLI 執行失敗: {result.stderr}")
            return available
        except FileNotFoundError:
            logger.warning(f"⚠️ 找不到執行檔: {self.exe_path}")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("⚠️ Go CLI 執行超時")
            return False
        except Exception as e:
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
        cmd = [self.exe_path] + args
        logger.debug(f"執行命令: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
            )
            
            if check and result.returncode != 0:
                error_msg = result.stderr.strip() or f"命令失敗，返回碼: {result.returncode}"
                raise GoBridgeError(error_msg)
            
            return result
            
        except subprocess.TimeoutExpired:
            raise GoBridgeError(f"命令執行超時 ({timeout}s)")
        except FileNotFoundError:
            raise GoBridgeError(f"找不到執行檔: {self.exe_path}")
    
    def _parse_json(self, output: str) -> dict | list:
        """解析 JSON 輸出"""
        try:
            return json.loads(output)
        except json.JSONDecodeError as e:
            raise GoBridgeError(f"JSON 解析失敗: {e}\n輸出: {output[:200]}")
    
    # === 掃描功能 ===
    
    def scan_directory(
        self,
        directory: str,
        workers: Optional[int] = None,
    ) -> list[ScanResult]:
        """
        掃描目錄中的影片檔案，提取番號
        
        Args:
            directory: 要掃描的目錄路徑
            workers: 並發工作數（預設使用 default_workers）
        
        Returns:
            list[ScanResult]: 掃描結果列表
        
        Raises:
            GoBridgeError: 掃描失敗時
        """
        workers = workers or self.default_workers
        
        args = ["scan", "-dir", directory, "-workers", str(workers)]
        result = self._run_command(args)
        
        data = self._parse_json(result.stdout)
        
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
        
        result = self._run_command(args, check=False)
        data = self._parse_json(result.stdout)
        
        return MoveResult(
            source=data.get("source", source),
            destination=data.get("destination", destination),
            success=data.get("success", False),
            error=data.get("error"),
            skipped=data.get("skipped", False),
            renamed=data.get("renamed"),
        )
    
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
            data = self._parse_json(result.stdout)
            
            # 解析結果
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
                total_items=data.get("total_items", len(items)),
                success_count=data.get("success_count", 0),
                failed_count=data.get("failed_count", 0),
                skipped_count=data.get("skipped_count", 0),
                results=results,
                duration=data.get("duration", ""),
            )
            
        finally:
            # 清理暫存檔
            try:
                os.unlink(batch_file)
            except Exception:
                pass
    
    # === 操作歷史功能 ===
    
    def list_operations(self) -> list[OperationLog]:
        """
        列出操作歷史
        
        Returns:
            list[OperationLog]: 操作日誌列表
        """
        args = ["history", "list", "-log-dir", self.log_dir]
        
        try:
            result = self._run_command(args, check=False)
            
            # 檢查是否為 "沒有操作記錄" 的訊息
            if "沒有操作記錄" in result.stdout:
                return []
            
            # 解析表格輸出（非 JSON）
            # 格式: ID        時間                 類型        狀態
            lines = result.stdout.strip().split("\n")
            logs = []
            
            for line in lines[2:]:  # 跳過標題行
                parts = line.split()
                if len(parts) >= 4:
                    logs.append(OperationLog(
                        id=parts[0],
                        timestamp=f"{parts[1]} {parts[2]}",
                        type=parts[3],
                        status=parts[4] if len(parts) > 4 else "",
                        items=[],
                    ))
            
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
        args = ["history", "show", operation_id, "-log-dir", self.log_dir]
        
        try:
            result = self._run_command(args)
            data = self._parse_json(result.stdout)
            
            return OperationLog(
                id=data.get("id", operation_id),
                timestamp=data.get("timestamp", ""),
                type=data.get("type", ""),
                status=data.get("status", ""),
                items=data.get("items", []),
            )
            
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
        args = ["history", "rollback", operation_id, "-log-dir", self.log_dir]
        
        result = self._run_command(args, check=False)
        
        # 解析輸出（可能包含狀態訊息 + JSON）
        lines = result.stdout.strip().split("\n")
        json_start = None
        
        for i, line in enumerate(lines):
            if line.startswith("{"):
                json_start = i
                break
        
        if json_start is not None:
            json_str = "\n".join(lines[json_start:])
            data = self._parse_json(json_str)
            
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
                total_items=data.get("total_items", 0),
                success_count=data.get("success_count", 0),
                failed_count=data.get("failed_count", 0),
                skipped_count=data.get("skipped_count", 0),
                results=results,
                duration=data.get("duration", ""),
            )
        
        # 如果沒有 JSON 輸出，返回空結果
        return BatchMoveResult(
            total_items=0,
            success_count=0,
            failed_count=0,
            skipped_count=0,
            results=[],
            duration="",
        )
    
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
