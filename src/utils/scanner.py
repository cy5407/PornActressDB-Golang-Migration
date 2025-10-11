# -*- coding: utf-8 -*-
"""
檔案掃描器模組
"""
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class UnifiedFileScanner:
    """統一檔案掃描器"""
    
    def __init__(self):
        self.supported_formats = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.m2ts']
    
    def scan_directory(self, path: str, recursive: bool = True) -> List[Path]:
        video_files = []
        scan_path = Path(path)
        if not scan_path.is_dir(): 
            logger.error(f"掃描路徑非資料夾: {path}")
            return []
        try:
            patterns = [f'*{ext}' for ext in self.supported_formats]
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
