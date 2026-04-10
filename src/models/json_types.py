"""
JSON 資料庫型別定義和常數

此模組定義了 JSON 資料庫系統中使用的所有型別定義和常數。
"""

from datetime import datetime, timezone
from typing import Any, TypedDict

# Python 3.10 相容性：UTC 在 3.11+ 才新增，改用 timezone.utc
UTC = timezone.utc

# ============================================================================
# 資料結構型別定義 (TypedDict)
# ============================================================================


class MetadataDict(TypedDict, total=False):
    """Metadata 型別定義"""

    source: str  # 資料來源
    confidence: float  # 資訊置信度 (0.0-1.0)


class VideoDict(TypedDict, total=False):
    """影片資料結構型別定義"""

    code: str  # 影片番號 (例: "DOCZ-004")
    title: str  # 片名
    studio: str  # 片商名稱
    release_date: str  # 發行日期 (ISO 8601: YYYY-MM-DD)
    url: str  # 線上連結
    actresses: list[str]  # 女優名稱清單
    search_status: str  # "imported" | "searched_found" | "searched_not_found" | "search_error"
    search_method: str  # "legacy-import" | "AV-WIKI" | "JAVDB" | "cascade"
    last_search_date: str  # 最後搜尋日期 (ISO 8601)
    avwiki_actress_status: str  # AV-WIKI 女優搜尋狀態
    avwiki_last_search_date: str  # AV-WIKI 最後女優搜尋日期 (ISO 8601)
    javdb_actress_status: str  # JAVDB 女優搜尋狀態
    javdb_last_search_date: str  # JAVDB 最後女優搜尋日期 (ISO 8601)
    created_at: str  # 建立時間 (ISO 8601)
    updated_at: str  # 更新時間 (ISO 8601)
    original_filename: str  # 原始檔名
    file_path: str  # 原始檔案完整路徑
    search_error_reason: str  # 搜尋失敗原因（選填）
    original_actress_count: int  # 原始解析到的女優數量（選填）
    metadata: MetadataDict  # 額外資訊


class ActressDict(TypedDict, total=False):
    """女優資料結構型別定義"""

    id: str  # 唯一識別符 (例: "actress_123")
    name: str  # 名字
    aliases: list[str]  # 別名清單
    video_count: int  # 出演部數
    created_at: str  # 建立時間 (ISO 8601)
    updated_at: str  # 更新時間 (ISO 8601)


class VideoActressLinkDict(TypedDict, total=False):
    """影片-女優關聯資料結構型別定義"""

    video_code: str  # 影片番號
    actress_id: str  # 女優 ID
    role_type: str  # 角色類型 ("主演" | "配角" | "客串")
    timestamp: str  # 關聯建立時間 (ISO 8601)


class ActressStatisticsDict(TypedDict, total=False):
    """女優統計快取結構型別定義"""

    actress_id: str  # 女優 ID
    total_videos: int  # 總出演部數
    studios: list[str]  # 片商清單
    latest_video_date: str  # 最新出演日期


class StudioStatisticsDict(TypedDict, total=False):
    """片商統計快取結構型別定義"""

    studio_name: str  # 片商名稱
    total_videos: int  # 總影片數
    actress_count: int  # 女優數
    date_range: dict[str, str]  # 日期範圍 {"start": "...", "end": "..."}


class CrossStatisticsDict(TypedDict, total=False):
    """交叉統計快取結構型別定義"""

    actress_id: str  # 女優 ID
    studio: str  # 片商名稱
    count: int  # 該女優在該片商的出演部數


class StatisticsDict(TypedDict, total=False):
    """統計快取結構型別定義"""

    actress_statistics: list[ActressStatisticsDict]  # 女優統計清單
    studio_statistics: list[StudioStatisticsDict]  # 片商統計清單
    enhanced_actress_studio_statistics: list[CrossStatisticsDict]  # 增強交叉統計清單
    computed_at: str  # 最後計算時間 (ISO 8601)


class JSONDatabaseDict(TypedDict, total=False):
    """JSON 資料庫根層結構型別定義"""

    schema_version: str  # Schema 版本 (例: "1.0.0")
    metadata: dict[str, Any]  # 元數據
    data_hash: str  # 資料 SHA256 雜湊
    created_at: str  # 建立時間 (ISO 8601)
    updated_at: str  # 更新時間 (ISO 8601)
    videos: dict[str, VideoDict]  # 影片資料 {code: VideoDict}
    actresses: dict[str, ActressDict]  # 女優資料 {actress_id: ActressDict}
    links: list[VideoActressLinkDict]  # 影片-女優關聯清單
    statistics: StatisticsDict  # 統計快取


# ============================================================================
# 常數定義
# ============================================================================

# 資料庫版本
SCHEMA_VERSION = "1.0.0"

# 搜尋狀態
SEARCH_STATUSES = {
    "IMPORTED": "imported",
    "SEARCHED_FOUND": "searched_found",
    "SEARCHED_NOT_FOUND": "searched_not_found",
    "SEARCH_ERROR": "search_error",
}

# 搜尋來源
SEARCH_METHODS = {
    "LEGACY_IMPORT": "legacy-import",
    "AV_WIKI": "AV-WIKI",
    "JAVDB": "JAVDB",
    "CASCADE": "cascade",
}

VIDEO_ALLOWED_FIELDS = {
    "code",
    "title",
    "studio",
    "release_date",
    "url",
    "actresses",
    "search_status",
    "search_method",
    "last_search_date",
    "avwiki_actress_status",
    "avwiki_last_search_date",
    "javdb_actress_status",
    "javdb_last_search_date",
    "created_at",
    "updated_at",
    "original_filename",
    "file_path",
    "search_error_reason",
    "original_actress_count",
    "metadata",
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
READ_LOCK_TIMEOUT = 30  # 秒
WRITE_LOCK_TIMEOUT = 60  # 秒

# 備份設定
MAX_BACKUP_AGE_DAYS = 30  # 天
MAX_BACKUP_COUNT = 50  # 個

# 驗證相關
MAX_STRING_LENGTH = 2000  # 字串最大長度
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
    now = datetime.now(UTC).strftime(ISO_DATETIME_FORMAT)

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
            "actress_statistics": [],  # 女優統計清單
            "studio_statistics": [],  # 片商統計清單
            "enhanced_actress_studio_statistics": [],  # 增強交叉統計清單
            "computed_at": now,  # 計算時間
        },
    }


def get_empty_video() -> VideoDict:
    """取得空的影片資料結構"""
    now = datetime.now(UTC).strftime(ISO_DATETIME_FORMAT)

    return {
        "code": "",
        "title": "",
        "studio": "",
        "release_date": "",
        "url": "",
        "actresses": [],
        "search_status": SEARCH_STATUSES["IMPORTED"],
        "search_method": SEARCH_METHODS["LEGACY_IMPORT"],
        "last_search_date": now,
        "avwiki_actress_status": "",
        "avwiki_last_search_date": "",
        "javdb_actress_status": "",
        "javdb_last_search_date": "",
        "created_at": now,
        "updated_at": now,
        "original_filename": "",
        "file_path": "",
        "metadata": {
            "source": "",
            "confidence": 0.0,
        },
    }


def get_empty_actress() -> ActressDict:
    """取得空的女優資料結構"""
    now = datetime.now(UTC).strftime(ISO_DATETIME_FORMAT)

    return {
        "id": "",
        "name": "",
        "aliases": [],
        "video_count": 0,
        "created_at": now,
        "updated_at": now,
    }
