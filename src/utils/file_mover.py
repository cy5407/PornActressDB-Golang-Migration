import logging
from pathlib import Path
from typing import Optional

from src.services import go_cli

logger = logging.getLogger(__name__)


class FileMover:
    def __init__(
        self,
        use_go: bool = False,
        conflict_strategy: str = "skip",
        enable_log: bool = True,
        log_dir: str = "logs",
        go_exe_path: Optional[str] = None,
    ):
        self.use_go = use_go
        self.conflict_strategy = conflict_strategy
        self.enable_log = enable_log
        self.log_dir = log_dir
        self.go_exe_path = go_exe_path
        self._go_available: Optional[bool] = None
        self._last_operation_id: Optional[str] = None

    @property
    def go_bridge(self):
        """相容性屬性：回傳 self（可用）或 None（不可用）。"""
        if not self.use_go:
            return None
        if self._go_available is None:
            try:
                self._go_available = go_cli.is_available(self.go_exe_path)
            except Exception:
                self._go_available = False
            if not self._go_available:
                logger.warning("Go CLI 不可用，改走 Python 降級搬移")
                self.use_go = False
        return self if self._go_available else None

    def _go_cli(self):
        return go_cli

    def move_file(self, source: str | Path, destination: str | Path, create_dirs: bool = True) -> dict:
        src, dst = str(source), str(destination)
        if not self.go_bridge:
            return {"success": False, "source": src, "destination": dst, "error": "Go CLI 不可用，無法搬移檔案", "skipped": False, "renamed": None}
        result = self._go_cli().move_file(
            src, dst, self.conflict_strategy, exe_path=self.go_exe_path
        )
        self._last_operation_id = result.get("operation_id") or self._last_operation_id
        return result

    def move_dir(self, source: str | Path, destination: str | Path) -> dict:
        src, dst = str(source), str(destination)
        if not self.go_bridge:
            return {"success": False, "source": src, "destination": dst, "error": "Go CLI 不可用，無法搬移目錄", "skipped": False}
        return self._go_cli().move_dir(
            src, dst, self.conflict_strategy, exe_path=self.go_exe_path
        )

    def batch_move(self, moves: list[tuple[str | Path, str | Path]]) -> dict:
        if not self.go_bridge:
            return {
                "total": len(moves), "success": 0, "failed": len(moves), "skipped": 0,
                "results": [{"success": False, "source": str(s), "destination": str(d), "error": "Go CLI 不可用，無法搬移檔案", "skipped": False, "renamed": None} for s, d in moves],
            }
        if len(moves) > 1:
            items = [{"source": str(s), "destination": str(d)} for s, d in moves]
            result = self._go_cli().batch_move(
                items,
                self.conflict_strategy,
                self.log_dir,
                exe_path=self.go_exe_path,
            )
            self._last_operation_id = result.get("operation_id") or self._last_operation_id
            return result
        results = [self.move_file(s, d) for s, d in moves]
        return {
            "total": len(results),
            "success": sum(1 for r in results if r["success"] and not r["skipped"]),
            "failed": sum(1 for r in results if not r["success"]),
            "skipped": sum(1 for r in results if r["skipped"]),
            "results": results,
        }

    def rollback(self, operation_id: Optional[str] = None) -> dict:
        if not self.go_bridge:
            return {"success": False, "error": "回滾功能僅在 Go 模式下可用"}
        op_id = operation_id or self._last_operation_id
        if not op_id:
            return {"success": False, "error": "沒有可回滾的操作"}
        return self._go_cli().rollback(
            op_id, self.log_dir, exe_path=self.go_exe_path
        )

    def list_operations(self, limit: int = 10) -> list[dict]:
        if not self.go_bridge:
            return []
        return self._go_cli().list_operations(
            limit=limit, log_dir=self.log_dir, exe_path=self.go_exe_path
        )

    @classmethod
    def from_config(cls, config) -> "FileMover":
        return cls(
            use_go=config.getboolean("go_integration", "enabled", fallback=True),
            conflict_strategy=config.get("go_integration", "move_conflict_strategy", fallback="skip"),
            enable_log=config.getboolean("go_integration", "enable_operation_log", fallback=True),
            log_dir=config.get("go_integration", "log_dir", fallback="logs"),
            go_exe_path=config.get("go_integration", "exe_path", fallback=None) or None,
        )
