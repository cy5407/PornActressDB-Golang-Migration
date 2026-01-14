"""
檔案掃描器模組

支援兩種掃描模式：
1. Python 原生掃描（預設）
2. Go CLI 加速掃描（透過 classifier.exe）
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class UnifiedFileScanner:
    """
    統一檔案掃描器
    
    支援 Go CLI 加速模式，當 use_go=True 時會透過 classifier.exe 執行掃描，
    可大幅提升掃描效能（尤其是大量檔案時）。
    
    使用方式：
        # 預設 Python 掃描
        scanner = UnifiedFileScanner()
        files = scanner.scan_directory("D:\\Videos")
        
        # 啟用 Go 加速
        scanner = UnifiedFileScanner(use_go=True)
        files = scanner.scan_directory("D:\\Videos")
        
        # 掃描並同時提取番號（僅 Go 模式）
        results = scanner.scan_with_codes("D:\\Videos")
        # 返回: [{"path": "...", "code": "SONE-123"}, ...]
    """

    def __init__(
        self,
        use_go: bool = False,
        go_workers: int = 10,
        go_exe_path: Optional[str] = None,
    ):
        """
        初始化掃描器
        
        Args:
            use_go: 是否使用 Go CLI 加速
            go_workers: Go 掃描並發數
            go_exe_path: classifier.exe 路徑（留空自動偵測）
        """
        self.use_go = use_go
        self.go_workers = go_workers
        self.go_exe_path = go_exe_path
        
        self.supported_formats = [
            ".mp4",
            ".avi",
            ".mkv",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
            ".ts",
            ".m2ts",
        ]
        
        # 延遲載入 Go 橋接層
        self._go_bridge = None
    
    @property
    def go_bridge(self):
        """延遲載入 Go 橋接層"""
        if self._go_bridge is None and self.use_go:
            try:
                # 嘗試多種導入方式
                try:
                    from src.services.go_bridge import GoBridge
                except ImportError:
                    from services.go_bridge import GoBridge
                    
                self._go_bridge = GoBridge(
                    exe_path=self.go_exe_path or None,
                    default_workers=self.go_workers,
                )
                if not self._go_bridge.is_available:
                    logger.warning("⚠️ Go CLI 不可用，將使用 Python 掃描")
                    self._go_bridge = None
                    self.use_go = False
            except ImportError as e:
                logger.warning(f"⚠️ 無法載入 Go 橋接層：{e}，將使用 Python 掃描")
                self.use_go = False
        return self._go_bridge

    def scan_directory(self, path: str, recursive: bool = True) -> list[Path]:
        """
        掃描目錄中的影片檔案
        
        Args:
            path: 目錄路徑
            recursive: 是否遞迴掃描子目錄
        
        Returns:
            影片檔案路徑列表
        """
        if self.use_go and self.go_bridge:
            return self._scan_with_go(path, recursive)
        else:
            return self._scan_with_python(path, recursive)
    
    def _scan_with_python(self, path: str, recursive: bool = True) -> list[Path]:
        """Python 原生掃描"""
        video_files = []
        scan_path = Path(path)
        if not scan_path.is_dir():
            logger.error(f"掃描路徑非資料夾: {path}")
            return []
        try:
            patterns = [f"*{ext}" for ext in self.supported_formats]
            if recursive:
                for p in patterns:
                    video_files.extend(scan_path.rglob(p))
            else:
                for p in patterns:
                    video_files.extend(scan_path.glob(p))
            return list(set(video_files))
        except Exception as e:
            logger.error(f"掃描目錄失敗: {e}")
            return []
    
    def _scan_with_go(self, path: str, recursive: bool = True) -> list[Path]:
        """Go CLI 加速掃描"""
        try:
            results = self.go_bridge.scan_directory(
                path, workers=self.go_workers, recursive=recursive
            )
            logger.info(f"🚀 Go 掃描完成: {len(results)} 個檔案")
            return [Path(r.path) for r in results]
        except Exception as e:
            logger.error(f"Go 掃描失敗，回退到 Python: {e}")
            return self._scan_with_python(path, recursive=recursive)
    
    def scan_with_codes(self, path: str, recursive: bool = True) -> list[dict]:
        """
        掃描目錄並同時提取番號（Go 模式專用）
        
        Args:
            path: 目錄路徑
            recursive: 是否遞迴（僅 Python 模式有效）
        
        Returns:
            [{"path": str, "code": str}, ...]
        """
        if self.use_go and self.go_bridge:
            try:
                results = self.go_bridge.scan_directory(path, workers=self.go_workers)
                return [{"path": r.path, "code": r.code} for r in results]
            except Exception as e:
                logger.error(f"Go 掃描失敗: {e}")
        
        # 回退到 Python（不提取番號）
        files = self._scan_with_python(path, recursive)
        return [{"path": str(f), "code": ""} for f in files]
    
    @classmethod
    def from_config(cls, config) -> "UnifiedFileScanner":
        """
        從設定檔建立掃描器
        
        Args:
            config: ConfigManager 實例
        
        Returns:
            UnifiedFileScanner 實例
        """
        use_go = config.getboolean("go_integration", "enabled", fallback=False)
        go_workers = config.getint("go_integration", "scan_workers", fallback=10)
        go_exe_path = config.get("go_integration", "exe_path", fallback="") or None
        
        return cls(
            use_go=use_go,
            go_workers=go_workers,
            go_exe_path=go_exe_path,
        )

