"""
檔案移動器模組

提供統一的檔案移動介面，支援兩種模式：
1. Python 原生移動（使用 shutil）
2. Go CLI 加速移動（透過 classifier.exe）

Go 模式提供額外功能：
- 操作日誌記錄
- 回滾功能
- 批次移動優化
"""

import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FileMover:
    """
    統一檔案移動器
    
    支援 Go CLI 加速模式，提供操作日誌和回滾功能。
    
    使用方式：
        # 預設 Python 移動
        mover = FileMover()
        mover.move_file("source.mp4", "dest/source.mp4")
        
        # 啟用 Go 加速
        mover = FileMover(use_go=True)
        mover.move_file("source.mp4", "dest/source.mp4")
        
        # 批次移動（Go 專用優化）
        mover.batch_move([
            ("a.mp4", "dest/a.mp4"),
            ("b.mp4", "dest/b.mp4"),
        ])
        
        # 回滾操作（Go 專用）
        mover.rollback()
    """

    def __init__(
        self,
        use_go: bool = False,
        conflict_strategy: str = "skip",
        enable_log: bool = True,
        log_dir: str = "logs",
        go_exe_path: Optional[str] = None,
    ):
        """
        初始化檔案移動器
        
        Args:
            use_go: 是否使用 Go CLI 加速
            conflict_strategy: 衝突策略 (skip, overwrite, rename)
            enable_log: 是否啟用操作日誌（僅 Go 模式）
            log_dir: 日誌目錄
            go_exe_path: classifier.exe 路徑（留空自動偵測）
        """
        self.use_go = use_go
        self.conflict_strategy = conflict_strategy
        self.enable_log = enable_log
        self.log_dir = log_dir
        self.go_exe_path = go_exe_path
        
        # 延遲載入 Go 橋接層
        self._go_bridge = None
        
        # 追蹤最近的操作（用於回滾）
        self._last_operation_id: Optional[str] = None
    
    @property
    def go_bridge(self):
        """延遲載入 Go 橋接層"""
        if self._go_bridge is None and self.use_go:
            try:
                try:
                    from src.services.go_bridge import GoBridge
                except ImportError:
                    from services.go_bridge import GoBridge
                    
                self._go_bridge = GoBridge(
                    exe_path=self.go_exe_path or None,
                    log_dir=self.log_dir,
                    default_strategy=self.conflict_strategy,
                )
                if not self._go_bridge.is_available:
                    logger.warning("⚠️ Go CLI 不可用，將使用 Python 移動")
                    self._go_bridge = None
                    self.use_go = False
            except ImportError as e:
                logger.warning(f"⚠️ 無法載入 Go 橋接層：{e}，將使用 Python 移動")
                self.use_go = False
        return self._go_bridge
    
    def move_file(
        self,
        source: str | Path,
        destination: str | Path,
        create_dirs: bool = True,
    ) -> dict:
        """
        移動單個檔案
        
        Args:
            source: 來源檔案路徑
            destination: 目標路徑
            create_dirs: 是否自動建立目標目錄
        
        Returns:
            dict: {
                "success": bool,
                "source": str,
                "destination": str,
                "error": str | None,
                "skipped": bool,
                "renamed": str | None,  # 如果發生重命名
            }
        """
        source = Path(source)
        destination = Path(destination)
        
        if self.use_go and self.go_bridge:
            return self._move_with_go(source, destination, create_dirs)
        else:
            return self._move_with_python(source, destination, create_dirs)
    
    def _move_with_python(
        self,
        source: Path,
        destination: Path,
        create_dirs: bool,
    ) -> dict:
        """使用 Python shutil 執行移動"""
        result = {
            "success": False,
            "source": str(source),
            "destination": str(destination),
            "error": None,
            "skipped": False,
            "renamed": None,
        }
        
        try:
            # 檢查來源是否存在
            if not source.exists():
                result["error"] = f"來源檔案不存在: {source}"
                return result
            
            # 處理衝突
            if destination.exists():
                if self.conflict_strategy == "skip":
                    result["skipped"] = True
                    result["success"] = True
                    logger.debug(f"跳過已存在: {destination}")
                    return result
                    
                elif self.conflict_strategy == "rename":
                    # 找一個不衝突的名稱
                    destination = self._get_unique_path(destination)
                    result["destination"] = str(destination)
                    result["renamed"] = destination.name
                    
                elif self.conflict_strategy == "overwrite":
                    destination.unlink()
            
            # 建立目標目錄
            if create_dirs:
                destination.parent.mkdir(parents=True, exist_ok=True)
            
            # 執行移動
            shutil.move(str(source), str(destination))
            result["success"] = True
            logger.debug(f"移動成功: {source} → {destination}")
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"移動失敗: {source} → {destination}: {e}")
        
        return result
    
    def _move_with_go(
        self,
        source: Path,
        destination: Path,
        create_dirs: bool,
    ) -> dict:
        """使用 Go CLI 執行移動"""
        try:
            # 如果需要建立目錄，先用 Python 建立（Go CLI 不支援此功能）
            if create_dirs:
                destination.parent.mkdir(parents=True, exist_ok=True)
            
            go_result = self.go_bridge.move_file(
                source=str(source),
                destination=str(destination),
                strategy=self.conflict_strategy,
            )
            
            # 記錄操作 ID（用於回滾）
            if hasattr(go_result, 'operation_id'):
                self._last_operation_id = go_result.operation_id
            
            return {
                "success": go_result.success,
                "source": go_result.source,
                "destination": go_result.destination,
                "error": go_result.error,
                "skipped": go_result.skipped,
                "renamed": go_result.renamed,
            }
            
        except Exception as e:
            logger.warning(f"⚠️ Go 移動失敗，回退到 Python: {e}")
            return self._move_with_python(source, destination, create_dirs)
    
    def _get_unique_path(self, path: Path) -> Path:
        """取得不衝突的唯一路徑"""
        if not path.exists():
            return path
        
        base = path.stem
        suffix = path.suffix
        parent = path.parent
        counter = 1
        
        while True:
            new_name = f"{base}_{counter}{suffix}"
            new_path = parent / new_name
            if not new_path.exists():
                return new_path
            counter += 1
            if counter > 1000:  # 防止無限迴圈
                raise RuntimeError(f"無法找到唯一檔案名稱: {path}")
    
    def move_dir(
        self,
        source: str | Path,
        destination: str | Path,
    ) -> dict:
        """
        移動整個目錄
        
        Args:
            source: 來源目錄路徑
            destination: 目標路徑
        
        Returns:
            dict: 移動結果
        """
        source = Path(source)
        destination = Path(destination)
        
        result = {
            "success": False,
            "source": str(source),
            "destination": str(destination),
            "error": None,
            "skipped": False,
        }
        
        try:
            if not source.exists():
                result["error"] = f"來源目錄不存在: {source}"
                return result
            
            if not source.is_dir():
                result["error"] = f"來源不是目錄: {source}"
                return result
            
            # 處理衝突
            if destination.exists():
                if self.conflict_strategy == "skip":
                    result["skipped"] = True
                    result["success"] = True
                    return result
                elif self.conflict_strategy == "overwrite":
                    shutil.rmtree(destination)
                elif self.conflict_strategy == "rename":
                    destination = self._get_unique_path(destination)
                    result["destination"] = str(destination)
            
            # 建立父目錄
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            # 使用 Go 或 Python 移動
            if self.use_go and self.go_bridge:
                try:
                    go_result = self.go_bridge.move_file(
                        source=str(source),
                        destination=str(destination),
                        strategy=self.conflict_strategy,
                        log_operation=self.enable_log,
                    )
                    result["success"] = go_result.success
                    if go_result.error:
                        result["error"] = go_result.error
                except Exception as e:
                    # 回退到 Python
                    shutil.move(str(source), str(destination))
                    result["success"] = True
            else:
                shutil.move(str(source), str(destination))
                result["success"] = True
                
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"移動目錄失敗: {source} → {destination}: {e}")
        
        return result
    
    def batch_move(
        self,
        moves: list[tuple[str | Path, str | Path]],
    ) -> dict:
        """
        批次移動多個檔案
        
        Args:
            moves: 移動清單 [(source, destination), ...]
        
        Returns:
            dict: {
                "total": int,
                "success": int,
                "failed": int,
                "skipped": int,
                "results": list[dict],
            }
        """
        if self.use_go and self.go_bridge and len(moves) > 1:
            return self._batch_move_with_go(moves)
        else:
            return self._batch_move_with_python(moves)
    
    def _batch_move_with_python(
        self,
        moves: list[tuple[str | Path, str | Path]],
    ) -> dict:
        """使用 Python 批次移動"""
        results = []
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        for source, destination in moves:
            result = self.move_file(source, destination)
            results.append(result)
            
            if result["success"]:
                if result["skipped"]:
                    skipped_count += 1
                else:
                    success_count += 1
            else:
                failed_count += 1
        
        return {
            "total": len(moves),
            "success": success_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "results": results,
        }
    
    def _batch_move_with_go(
        self,
        moves: list[tuple[str | Path, str | Path]],
    ) -> dict:
        """使用 Go CLI 批次移動"""
        try:
            # 轉換為 Go 格式
            go_moves = [
                {"source": str(s), "destination": str(d)}
                for s, d in moves
            ]
            
            go_result = self.go_bridge.batch_move(
                items=go_moves,
                strategy=self.conflict_strategy,
            )
            
            # 記錄操作 ID
            if getattr(go_result, "operation_id", None):
                self._last_operation_id = go_result.operation_id
            
            return {
                "total": go_result.total_items,
                "success": go_result.success_count,
                "failed": go_result.failed_count,
                "skipped": go_result.skipped_count,
                "operation_id": go_result.operation_id,
                "status": go_result.status,
                "summary": go_result.summary,
                "results": [
                    {
                        "success": r.success,
                        "source": r.source,
                        "destination": r.destination,
                        "error": r.error,
                        "skipped": r.skipped,
                        "renamed": r.renamed,
                    }
                    for r in go_result.results
                ],
            }
            
        except Exception as e:
            logger.warning(f"⚠️ Go 批次移動失敗，回退到 Python: {e}")
            return self._batch_move_with_python(moves)
    
    def rollback(self, operation_id: Optional[str] = None) -> dict:
        """
        回滾操作（僅 Go 模式）
        
        Args:
            operation_id: 要回滾的操作 ID（留空使用最後一次操作）
        
        Returns:
            dict: 回滾結果
        """
        if not self.use_go or not self.go_bridge:
            return {
                "success": False,
                "error": "回滾功能僅在 Go 模式下可用",
            }
        
        op_id = operation_id or self._last_operation_id
        if not op_id:
            return {
                "success": False,
                "error": "沒有可回滾的操作",
            }
        
        try:
            result = self.go_bridge.rollback(op_id)
            return {
                "success": result.failed_count == 0,
                "operation_id": op_id,
                "rolled_back": result.success_count,
                "failed": result.failed_count,
                "skipped": result.skipped_count,
                "status": result.status,
                "summary": result.summary,
                "error": result.summary if result.failed_count > 0 else None,
                "results": [
                    {
                        "success": item.success,
                        "source": item.source,
                        "destination": item.destination,
                        "error": item.error,
                        "skipped": item.skipped,
                        "renamed": item.renamed,
                    }
                    for item in result.results
                ],
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    def list_operations(self, limit: int = 10) -> list[dict]:
        """
        列出操作歷史（僅 Go 模式）
        
        Args:
            limit: 最多返回的操作數量
        
        Returns:
            list[dict]: 操作列表
        """
        if not self.use_go or not self.go_bridge:
            return []
        
        try:
            operations = self.go_bridge.list_operations(limit=limit)
            return [
                {
                    "id": op.id,
                    "timestamp": op.timestamp,
                    "type": op.type,
                    "status": op.status,
                    "items": op.items,
                    "total_items": op.total_items,
                    "success_count": op.success_count,
                    "failed_count": op.failed_count,
                    "skipped_count": op.skipped_count,
                }
                for op in operations
            ]
        except Exception:
            return []
    
    @classmethod
    def from_config(cls, config) -> "FileMover":
        """
        從設定檔建立 FileMover 實例
        
        Args:
            config: ConfigManager 實例
        
        Returns:
            FileMover 實例
        """
        return cls(
            use_go=config.getboolean("go_integration", "enabled", fallback=True),
            conflict_strategy=config.get("go_integration", "move_conflict_strategy", fallback="skip"),
            enable_log=config.getboolean("go_integration", "enable_operation_log", fallback=True),
            log_dir=config.get("go_integration", "log_dir", fallback="logs"),
            go_exe_path=config.get("go_integration", "exe_path", fallback=None) or None,
        )


# === 便捷函式 ===

_default_mover: Optional[FileMover] = None


def get_mover(use_go: bool = False) -> FileMover:
    """取得預設的 FileMover 實例（單例模式）"""
    global _default_mover
    if _default_mover is None or _default_mover.use_go != use_go:
        _default_mover = FileMover(use_go=use_go)
    return _default_mover


def move_file(
    source: str | Path,
    destination: str | Path,
    use_go: bool = False,
) -> dict:
    """便捷函式：移動單個檔案"""
    return get_mover(use_go).move_file(source, destination)


def move_dir(
    source: str | Path,
    destination: str | Path,
    use_go: bool = False,
) -> dict:
    """便捷函式：移動目錄"""
    return get_mover(use_go).move_dir(source, destination)
