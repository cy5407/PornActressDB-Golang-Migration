import logging
from importlib import import_module
from pathlib import Path; from typing import Optional
logger = logging.getLogger(__name__)
class FileMover:
    def __init__(self, use_go: bool = False, conflict_strategy: str = "skip", enable_log: bool = True, log_dir: str = "logs", go_exe_path: Optional[str] = None):
        self.use_go, self.conflict_strategy, self.enable_log, self.log_dir, self.go_exe_path, self._go_bridge, self._last_operation_id = use_go, conflict_strategy, enable_log, log_dir, go_exe_path, None, None

    @property
    def go_bridge(self):
        if self._go_bridge is None and self.use_go:
            try:
                try: GoBridge = import_module("src.services.go_bridge").GoBridge
                except ImportError: GoBridge = import_module("services.go_bridge").GoBridge
                bridge = GoBridge(exe_path=self.go_exe_path or None, log_dir=self.log_dir, default_strategy=self.conflict_strategy)
                self._go_bridge = bridge if bridge.is_available else None
                if not self._go_bridge: logger.warning("Go CLI 不可用，改走 Python 降級搬移")
            except ImportError as e: logger.warning(f"無法載入 Go 橋接層，改走 Python 降級搬移: {e}")
            self.use_go = bool(self._go_bridge)
        return self._go_bridge

    def move_file(self, source: str | Path, destination: str | Path, create_dirs: bool = True) -> dict:
        src, dst = Path(source), Path(destination)
        if not self.go_bridge:
            return {"success": False, "source": str(src), "destination": str(dst), "error": "Go CLI 不可用，無法搬移檔案", "skipped": False, "renamed": None}
        try:
            r = self.go_bridge.move_file(str(src), str(dst), self.conflict_strategy)
            self._last_operation_id = getattr(r, "operation_id", None) or self._last_operation_id
            return {"success": r.success, "source": r.source, "destination": r.destination, "error": r.error, "skipped": r.skipped, "renamed": r.renamed}
        except Exception as e:
            return {"success": False, "source": str(src), "destination": str(dst), "error": str(e), "skipped": False, "renamed": None}

    def move_dir(self, source: str | Path, destination: str | Path) -> dict:
        src, dst = Path(source), Path(destination)
        if not self.go_bridge:
            return {"success": False, "source": str(src), "destination": str(dst), "error": "Go CLI 不可用，無法搬移目錄", "skipped": False}
        try:
            return self.go_bridge.move_dir(str(src), str(dst), self.conflict_strategy)
        except Exception as e:
            return {"success": False, "source": str(src), "destination": str(dst), "error": str(e), "skipped": False}

    def batch_move(self, moves: list[tuple[str | Path, str | Path]]) -> dict:
        if not self.go_bridge:
            return {"total": len(moves), "success": 0, "failed": len(moves), "skipped": 0, "results": [{"success": False, "source": str(s), "destination": str(d), "error": "Go CLI 不可用，無法搬移檔案", "skipped": False, "renamed": None} for s, d in moves]}
        if len(moves) > 1:
            try:
                r = self.go_bridge.batch_move([{"source": str(src), "destination": str(dst)} for src, dst in moves], self.conflict_strategy)
                self._last_operation_id = r.operation_id or self._last_operation_id
                return {"total": r.total_items, "success": r.success_count, "failed": r.failed_count, "skipped": r.skipped_count, "operation_id": r.operation_id, "status": r.status, "summary": r.summary, "results": [{"success": i.success, "source": i.source, "destination": i.destination, "error": i.error, "skipped": i.skipped, "renamed": i.renamed} for i in r.results]}
            except Exception as e:
                return {"total": len(moves), "success": 0, "failed": len(moves), "skipped": 0, "error": str(e), "results": []}
        results = [self.move_file(src, dst) for src, dst in moves]
        return {"total": len(moves), "success": sum(1 for i in results if i["success"] and not i["skipped"]), "failed": sum(1 for i in results if not i["success"]), "skipped": sum(1 for i in results if i["skipped"]), "results": results}

    def rollback(self, operation_id: Optional[str] = None) -> dict:
        if not self.go_bridge: return {"success": False, "error": "回滾功能僅在 Go 模式下可用"}
        op_id = operation_id or self._last_operation_id
        if not op_id: return {"success": False, "error": "沒有可回滾的操作"}
        try:
            r = self.go_bridge.rollback(op_id)
            return {"success": r.failed_count == 0, "operation_id": op_id, "rolled_back": r.success_count, "failed": r.failed_count, "skipped": r.skipped_count, "status": r.status, "summary": r.summary, "error": r.summary if r.failed_count > 0 else None, "results": [{"success": i.success, "source": i.source, "destination": i.destination, "error": i.error, "skipped": i.skipped, "renamed": i.renamed} for i in r.results]}
        except Exception as e: return {"success": False, "error": str(e)}

    def list_operations(self, limit: int = 10) -> list[dict]:
        if not self.go_bridge: return []
        try: return [{"id": o.id, "timestamp": o.timestamp, "type": o.type, "status": o.status, "items": o.items, "total_items": o.total_items, "success_count": o.success_count, "failed_count": o.failed_count, "skipped_count": o.skipped_count} for o in self.go_bridge.list_operations(limit=limit)]
        except Exception: return []

    @classmethod
    def from_config(cls, config) -> "FileMover":
        return cls(config.getboolean("go_integration", "enabled", fallback=True), config.get("go_integration", "move_conflict_strategy", fallback="skip"), config.getboolean("go_integration", "enable_operation_log", fallback=True), config.get("go_integration", "log_dir", fallback="logs"), config.get("go_integration", "exe_path", fallback=None) or None)
