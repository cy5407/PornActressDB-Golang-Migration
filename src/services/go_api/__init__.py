"""Go CLI 領域 API 模組。"""

from .db import (
    db_compact_journal,
    db_delete_video,
    db_get_stats,
    db_get_video,
    db_list_videos,
    db_update_video,
)
from .identify import (
    get_studio_prefixes,
    identify_studio,
    identify_studios_batch,
    list_studios,
)
from .move import (
    BatchMoveResult,
    MoveResult,
    OperationLog,
    batch_move,
    get_operation,
    list_operations,
    move_dir,
    move_file,
    rollback,
    rollback_last,
)
from .scan import ScanResult, scan_directory

__all__ = [
    "BatchMoveResult",
    "MoveResult",
    "OperationLog",
    "ScanResult",
    "batch_move",
    "db_compact_journal",
    "db_delete_video",
    "db_get_stats",
    "db_get_video",
    "db_list_videos",
    "db_update_video",
    "get_operation",
    "get_studio_prefixes",
    "identify_studio",
    "identify_studios_batch",
    "list_operations",
    "list_studios",
    "move_dir",
    "move_file",
    "rollback",
    "rollback_last",
    "scan_directory",
]
