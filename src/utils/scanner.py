"""Thin file scanner adapter."""

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class UnifiedFileScanner:
    def __init__(self, use_go: bool = False, go_workers: int = 10, go_exe_path: Optional[str] = None):
        self.use_go, self.go_workers, self.go_exe_path = use_go, go_workers, go_exe_path
        self._go_available: Optional[bool] = None

    @property
    def go_bridge(self):
        """相容性屬性：回傳 self（可用）或 None（不可用）。"""
        if not self.use_go:
            return None
        if self._go_available is None:
            self._go_available = self._check_go_available()
            if not self._go_available:
                self.use_go = False
        return self if self._go_available else None

    @property
    def is_available(self) -> bool:
        return bool(self._go_available)

    def _check_go_available(self) -> bool:
        try:
            try:
                from services.go_cli import is_available
            except ImportError:
                from src.services.go_cli import is_available
            if self.go_exe_path:
                import os
                return os.path.isfile(self.go_exe_path) and os.access(self.go_exe_path, os.X_OK)
            return is_available()
        except Exception:
            return False

    def scan_directory(self, path: str, recursive: bool = True) -> list[Path]:
        if not self.go_bridge:
            raise RuntimeError("Go CLI 不可用，無法掃描目錄")
        try:
            try:
                from services.go_cli import run as go_run
            except ImportError:
                from src.services.go_cli import run as go_run
            cmd = ["scan", "-dir", path, "-workers", str(self.go_workers)]
            if not recursive:
                cmd.append("-recursive=false")
            results = go_run(cmd)
            if isinstance(results, list):
                return [Path(item["path"]) for item in results if "path" in item]
            return []
        except Exception as e:
            raise RuntimeError(f"Go 掃描失敗: {e}") from e

    def scan_with_codes(self, path: str, recursive: bool = True) -> list[dict]:
        if not self.go_bridge:
            raise RuntimeError("scan_with_codes 需要 Go CLI，目前不可用")
        try:
            try:
                from services.go_cli import run as go_run
            except ImportError:
                from src.services.go_cli import run as go_run
            cmd = ["scan", "-dir", path, "-workers", str(self.go_workers)]
            if not recursive:
                cmd.append("-recursive=false")
            results = go_run(cmd)
            if isinstance(results, list):
                return [{"path": item["path"], "code": item.get("code", "")} for item in results]
            return []
        except Exception as e:
            raise RuntimeError(f"Go 掃描失敗: {e}") from e

    @classmethod
    def from_config(cls, config) -> "UnifiedFileScanner":
        return cls(
            use_go=config.getboolean("go_integration", "enabled", fallback=False),
            go_workers=config.getint("go_integration", "scan_workers", fallback=10),
            go_exe_path=config.get("go_integration", "exe_path", fallback="") or None,
        )

