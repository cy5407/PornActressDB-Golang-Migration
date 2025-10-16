# -*- coding: utf-8 -*-
"""
JSON 資料庫型別定義和常數

此模組定義了 JSON 資料庫系統中使用的所有型別定義和常數。
"""

from typing import TypedDict, List, Dict, Any, Optional
from datetime import datetime

# ============================================================================
# 資料結構型別定義 (TypedDict)
# ============================================================================


class MetadataDict(TypedDict, total=False):
    """Metadata 型別定義"""
    source: str                    # 資料來源
    confidence: float              # 資訊置信度 (0.0-1.0)


class VideoDict(TypedDict, total=False):
    """影片資料結構型別定義"""
    id: str                        # 唯一識別符 (例: "123abc")
    title: str                     # 片名
    studio: str                    # 片商名稱
    release_date: str              # 發行日期 (ISO 8601: YYYY-MM-DD)
    url: str                       # 線上連結
    actresses: List[str]           # 女優 ID 清單
    search_status: str             # "success" | "partial" | "failed"
    last_search_date: str          # 最後搜尋日期 (ISO 8601)
    created_at: str                # 建立時間 (ISO 8601)
    updated_at: str                # 更新時間 (ISO 8601)
    metadata: MetadataDict         # 額外資訊


class ActressDict(TypedDict, total=False):
    """女優資料結構型別定義"""
    id: str                        # 唯一識別符 (例: "actress_123")
    name: str                      # 名字
    aliases: List[str]             # 別名清單
    video_count: int               # 出演部數
    created_at: str                # 建立時間 (ISO 8601)
    updated_at: str                # 更新時間 (ISO 8601)


class VideoActressLinkDict(TypedDict, total=False):
    """影片-女優關聯資料結構型別定義"""
    video_id: str                  # 影片 ID
    actress_id: str                # 女優 ID
    role_type: str                 # 角色類型 ("主演" | "配角" | "客串")
    timestamp: str                 # 關聯建立時間 (ISO 8601)


class ActressStatisticsDict(TypedDict, total=False):
    """女優統計快取結構型別定義"""
    actress_id: str                # 女優 ID
    total_videos: int              # 總出演部數
    studios: List[str]             # 片商清單
    latest_video_date: str         # 最新出演日期


class StudioStatisticsDict(TypedDict, total=False):
    """片商統計快取結構型別定義"""
    studio_name: str               # 片商名稱
    total_videos: int              # 總影片數
    actress_count: int             # 女優數
    date_range: Dict[str, str]     # 日期範圍 {"start": "...", "end": "..."}


class CrossStatisticsDict(TypedDict, total=False):
    """交叉統計快取結構型別定義"""
    actress_id: str                # 女優 ID
    studio: str                    # 片商名稱
    count: int                     # 該女優在該片商的出演部數


class StatisticsDict(TypedDict, total=False):
    """統計快取結構型別定義"""
    actress_stats: List[ActressStatisticsDict]
    studio_stats: List[StudioStatisticsDict]
    cross_stats: List[CrossStatisticsDict]
    last_computed: str             # 最後計算時間 (ISO 8601)


class JSONDatabaseDict(TypedDict, total=False):
    """JSON 資料庫根層結構型別定義"""
    schema_version: str            # Schema 版本 (例: "1.0.0")
    metadata: Dict[str, Any]       # 元數據
    data_hash: str                 # 資料 SHA256 雜湊
    created_at: str                # 建立時間 (ISO 8601)
    updated_at: str                # 更新時間 (ISO 8601)
    videos: Dict[str, VideoDict]   # 影片資料 {video_id: VideoDict}
    actresses: Dict[str, ActressDict]  # 女優資料 {actress_id: ActressDict}
    links: List[VideoActressLinkDict]   # 影片-女優關聯清單
    statistics: StatisticsDict     # 統計快取


# ============================================================================
# 常數定義
# ============================================================================

# 資料庫版本
SCHEMA_VERSION = "1.0.0"

# 搜尋狀態
SEARCH_STATUSES = {
    "SUCCESS": "success",
    "PARTIAL": "partial",
    "FAILED": "failed",
}

# 角色類型
ROLE_TYPES = {
    "MAIN": "主演",
    "SUPPORTING": "配角",
    "GUEST": "客串",
}

# 檔案路徑
DATA_DIR = "data/json_db"
JSON_DB_FILE = "data/json_db/data.json"
BACKUP_DIR = "data/json_db/backup"
BACKUP_MANIFEST_FILE = "data/json_db/backup/BACKUP_MANIFEST.json"

# 檔案鎖定
READ_LOCK_TIMEOUT = 30       # 秒
WRITE_LOCK_TIMEOUT = 60      # 秒

# 備份設定
MAX_BACKUP_AGE_DAYS = 30     # 天
MAX_BACKUP_COUNT = 50        # 個

# 驗證相關
MAX_STRING_LENGTH = 2000     # 字串最大長度
MAX_ACTRESSES_PER_VIDEO = 20  # 每部影片最多女優數
MAX_ALIASES_PER_ACTRESS = 10  # 每位女優最多別名數

# 日期格式
ISO_DATE_FORMAT = "%Y-%m-%d"
ISO_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# ============================================================================
# 例外類別定義
# ============================================================================


class JSONDatabaseError(Exception):
    """JSON 資料庫基礎例外類別"""
    pass


class ValidationError(JSONDatabaseError):
    """資料驗證失敗例外"""
    pass


class LockError(JSONDatabaseError):
    """檔案鎖定相關例外"""
    pass


class DataIntegrityError(JSONDatabaseError):
    """資料完整性檢查失敗例外"""
    pass


class BackupError(JSONDatabaseError):
    """備份相關操作失敗例外"""
    pass


class CorruptedDataError(JSONDatabaseError):
    """資料損壞例外"""
    pass


# ============================================================================
# 預設值和工具函式
# ============================================================================


def get_empty_json_database() -> JSONDatabaseDict:
    """
    取得空的 JSON 資料庫結構

    Returns:
        JSONDatabaseDict: 初始化的空資料庫結構
    """
    from datetime import datetime, timezone
    
    now = datetime.now(timezone.utc).strftime(ISO_DATETIME_FORMAT)
    
    return {
        "schema_version": SCHEMA_VERSION,
        "metadata": {
            "description": "Python 女優分類系統 JSON 資料庫",
            "encoding": "UTF-8",
        },
        "data_hash": "",  # 初始時為空
        "created_at": now,
        "updated_at": now,
        "videos": {},
        "actresses": {},
        "links": [],
        "statistics": {
            "actress_stats": [],
            "studio_stats": [],
            "cross_stats": [],
            "last_computed": now,
        },
    }


def get_empty_video() -> VideoDict:
    """取得空的影片資料結構"""
    from datetime import datetime, timezone
    
    now = datetime.now(timezone.utc).strftime(ISO_DATETIME_FORMAT)
    
    return {
        "id": "",
        "title": "",
        "studio": "",
        "release_date": "",
        "url": "",
        "actresses": [],
        "search_status": SEARCH_STATUSES["SUCCESS"],
        "last_search_date": now,
        "created_at": now,
        "updated_at": now,
        "metadata": {
            "source": "",
            "confidence": 0.0,
        },
    }


def get_empty_actress() -> ActressDict:
    """取得空的女優資料結構"""
    from datetime import datetime, timezone
    
    now = datetime.now(timezone.utc).strftime(ISO_DATETIME_FORMAT)
    
    return {
        "id": "",
        "name": "",
        "aliases": [],
        "video_count": 0,
        "created_at": now,
        "updated_at": now,
    }
