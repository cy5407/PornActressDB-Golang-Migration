"""Go CLI facade。"""

import logging, os, platform, sys, tempfile
from pathlib import Path
from typing import Optional

try:
    from . import go_api as api
    from .go_runner import GoBridgeError, GoCommandRunner, _cleanup_temp_file
except ImportError:
    import services.go_api as api
    from services.go_runner import GoBridgeError, GoCommandRunner, _cleanup_temp_file

logger = logging.getLogger(__name__)
BatchMoveResult = api.BatchMoveResult
MoveResult = api.MoveResult
OperationLog = api.OperationLog
ScanResult = api.ScanResult
db_compact_journal = api.db_compact_journal
db_delete_video = api.db_delete_video
db_get_stats = api.db_get_stats
db_get_video = api.db_get_video
db_list_videos = api.db_list_videos
db_update_video = api.db_update_video
get_studio_prefixes = api.get_studio_prefixes
identify_studio = api.identify_studio
identify_studios_batch = api.identify_studios_batch
list_studios = api.list_studios


class GoBridge:
    """Go CLI facade，保留 runtime 與 delegation。"""

    def __init__(self, exe_path: Optional[str] = None, log_dir: str = "logs", default_workers: int = 10, default_strategy: str = "skip"):
        self.exe_path = exe_path or self._find_exe()
        self.log_dir = log_dir
        self.default_workers = default_workers
        self.default_strategy = default_strategy
        self._available = None
        self._runner = GoCommandRunner(self.exe_path)
    
    def _find_exe(self) -> str:
        """自動偵測 classifier.exe 位置"""
        possible_paths = [
            Path(getattr(sys, "_MEIPASS", "")) / "classifier.exe",
            Path(__file__).parent.parent.parent / "classifier.exe",
            Path.cwd() / "classifier.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "classifier" / "classifier.exe",
        ]
        
        for path in possible_paths:
            if path.exists():
                resolved = str(path.resolve())
                if platform.system() != "Windows" and not os.access(resolved, os.X_OK):
                    logger.warning(f"⚠️ 找到 {resolved} 但缺少執行權限（+x）")
                    continue
                return resolved
        
        import shutil

        exe_in_path = shutil.which("classifier.exe") or shutil.which("classifier")
        if exe_in_path:
            return exe_in_path
        
        return "classifier.exe"  # 返回預設名稱，讓後續檢查失敗
    
    @property
    def is_available(self) -> bool:
        if self._available is None:
            self._available = self._check_availability()
        return self._available
    
    def _check_availability(self) -> bool:
        try:
            result = self._runner.run(["help"], timeout=5, check=False)
            return result.returncode == 0
        except GoBridgeError:
            return False

    def _run_command(self, args: list[str], timeout: int = 60, check: bool = True):
        return self._runner.run(args, timeout=timeout, check=check)

    def _parse_json(self, output: str) -> dict | list:
        return self._runner.parse_json(output)

    def _run_json(self, args: list[str], timeout: int = 60, check: bool = True) -> dict | list: return self._runner.run_json(args, timeout=timeout, check=check)
    def scan_directory(self, directory: str, workers: Optional[int] = None, recursive: bool = True) -> list[ScanResult]: return api.scan_directory(directory, workers, recursive, runner=self._runner, default_workers=self.default_workers)
    def move_file(self, source: str, destination: str, strategy: Optional[str] = None, dry_run: bool = False) -> MoveResult: return api.move_file(source, destination, strategy, dry_run, runner=self._runner, log_dir=self.log_dir, default_strategy=self.default_strategy)
    def move_dir(self, source: str, destination: str, strategy: Optional[str] = None, dry_run: bool = False) -> dict: return api.move_dir(source, destination, strategy, dry_run, runner=self._runner, log_dir=self.log_dir, default_strategy=self.default_strategy)
    def batch_move(self, items: list[dict], strategy: Optional[str] = None, dry_run: bool = False) -> BatchMoveResult: return api.batch_move(items, strategy, dry_run, runner=self._runner, log_dir=self.log_dir, default_strategy=self.default_strategy)
    def list_operations(self, limit: Optional[int] = None) -> list[OperationLog]: return api.list_operations(limit, runner=self._runner, log_dir=self.log_dir)
    def get_operation(self, operation_id: str) -> Optional[OperationLog]: return api.get_operation(operation_id, runner=self._runner, log_dir=self.log_dir)
    def rollback(self, operation_id: str) -> BatchMoveResult: return api.rollback(operation_id, runner=self._runner, log_dir=self.log_dir)
    def rollback_last(self) -> BatchMoveResult: return api.rollback_last(runner=self._runner, log_dir=self.log_dir)

    # DB instance methods — pass self._runner so tests can inject a mock runner
    def db_get_video(self, code: str, data_dir: str = "data/json_db") -> Optional[dict]: return api.db_get_video(code, data_dir, runner=self._runner)
    def db_update_video(self, code: str, video: dict, data_dir: str = "data/json_db") -> bool: return api.db_update_video(code, video, data_dir, runner=self._runner)
    def db_delete_video(self, code: str, data_dir: str = "data/json_db") -> bool: return api.db_delete_video(code, data_dir, runner=self._runner)
    def db_list_videos(self, data_dir: str = "data/json_db") -> list[str]: return api.db_list_videos(data_dir, runner=self._runner)
    def db_get_stats(self, data_dir: str = "data/json_db") -> dict: return api.db_get_stats(data_dir, runner=self._runner)
    def db_compact_journal(self, data_dir: str = "data/json_db") -> bool: return api.db_compact_journal(data_dir, runner=self._runner)

    # Identify instance methods — pass self._runner
    def identify_studio(self, code: str, check_major: bool = False) -> dict: return api.identify_studio(code, check_major, runner=self._runner)
    def identify_studios_batch(self, codes: list[str], check_major: bool = False) -> list[dict]: return api.identify_studios_batch(codes, check_major, runner=self._runner)
    def list_studios(self) -> list[str]: return api.list_studios(runner=self._runner)
    def get_studio_prefixes(self, studio_name: str) -> list[str]: return api.get_studio_prefixes(studio_name, runner=self._runner)


_default_bridge: Optional[GoBridge] = None


def get_bridge() -> GoBridge:
    global _default_bridge
    if _default_bridge is None:
        _default_bridge = GoBridge()
    return _default_bridge


def scan_directory_go(directory: str, workers: int = 10) -> list[dict]:
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
