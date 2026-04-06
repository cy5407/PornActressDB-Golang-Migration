"""Thin file scanner adapter."""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class UnifiedFileScanner:
    def __init__(self, use_go: bool = False, go_workers: int = 10, go_exe_path: Optional[str] = None):
        self.use_go, self.go_workers, self.go_exe_path, self._go_bridge = use_go, go_workers, go_exe_path, None

    @property
    def go_bridge(self):
        if self._go_bridge is None and self.use_go:
            try:
                try: from src.services.go_bridge import GoBridge
                except ImportError: from services.go_bridge import GoBridge
                bridge = GoBridge(exe_path=self.go_exe_path or None, default_workers=self.go_workers)
                self._go_bridge = bridge if bridge.is_available else None
            except ImportError:
                pass
            self.use_go = bool(self._go_bridge)
        return self._go_bridge

    def scan_directory(self, path: str, recursive: bool = True) -> list[Path]:
        if not self.go_bridge:
            raise RuntimeError("Go CLI 不可用，無法掃描目錄")
        try:
            return [Path(item.path) for item in self.go_bridge.scan_directory(path, workers=self.go_workers, recursive=recursive)]
        except Exception as e:
            raise RuntimeError(f"Go 掃描失敗: {e}") from e

    def scan_with_codes(self, path: str, recursive: bool = True) -> list[dict]:
        if not self.go_bridge: raise RuntimeError("scan_with_codes 需要 Go CLI，目前不可用")
        try: return [{"path": item.path, "code": item.code} for item in self.go_bridge.scan_directory(path, workers=self.go_workers, recursive=recursive)]
        except Exception as e: raise RuntimeError(f"Go 掃描失敗: {e}") from e

    @classmethod
    def from_config(cls, config) -> "UnifiedFileScanner":
        return cls(
            use_go=config.getboolean("go_integration", "enabled", fallback=False),
            go_workers=config.getint("go_integration", "scan_workers", fallback=10),
            go_exe_path=config.get("go_integration", "exe_path", fallback="") or None,
        )
