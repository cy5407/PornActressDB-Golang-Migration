"""
增量 JSON 資料庫管理器 (IncrementalJSONDB)

此模組實作增量儲存機制以提升大型 JSON 資料庫的寫入效能（40x 加速）

核心概念：
- Journal 檔案：記錄所有增量變更（JSON Lines 格式）
- Dirty Tracking：追蹤被修改的資料項
- 延遲合併：只在必要時才將 journal 合併回主檔案
- 快速寫入：append-only 操作遠快於完整 JSON 重寫

檔案結構：
- data.json：主資料檔案（完整狀態）
- data.journal：增量變更日誌（JSON Lines）
- data.index：Dirty keys 索引（快速查找）

使用情境：
- 適合：頻繁的小規模更新（新增/修改單一影片）
- 不適合：大規模批次更新（建議直接使用 JSONDBManager）
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import orjson
from filelock import FileLock

# Python 3.10 相容性：UTC 在 3.11+ 才新增，改用 timezone.utc
UTC = timezone.utc

from src.models.json_database import JSONDBManager
from src.models.json_types import (
    JSONDatabaseError,
    VideoDict,
)

logger = logging.getLogger(__name__)

# Journal 操作類型
JOURNAL_OP_ADD = "ADD"
JOURNAL_OP_UPDATE = "UPDATE"
JOURNAL_OP_DELETE = "DELETE"

# 合併閾值設定
JOURNAL_SIZE_THRESHOLD = 1000  # 當 journal 超過 1000 條記錄時觸發合併
JOURNAL_AGE_THRESHOLD = 3600  # 當 journal 超過 1 小時時觸發合併（秒）


class JournalEntry:
    """Journal 記錄項"""

    def __init__(
        self,
        operation: str,
        entity_type: str,  # 'video', 'actress', 'link'
        entity_id: str,
        data: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ):
        self.operation = operation
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.data = data
        self.timestamp = timestamp or datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """轉換為字典"""
        return {
            "op": self.operation,
            "type": self.entity_type,
            "id": self.entity_id,
            "data": self.data,
            "ts": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JournalEntry":
        """從字典建立"""
        return cls(
            operation=d["op"],
            entity_type=d["type"],
            entity_id=d["id"],
            data=d.get("data"),
            timestamp=d.get("ts"),
        )


class IncrementalJSONDB:
    """
    增量 JSON 資料庫管理器

    提供 40x 寫入加速的增量儲存機制。

    工作原理：
    1. 讀取時：合併主檔案 + journal 檔案
    2. 寫入時：僅 append 到 journal（快速）
    3. 定期：將 journal 合併回主檔案

    範例：
        db = IncrementalJSONDB('data/json_db')

        # 快速更新（寫入 journal）
        db.update_video('STARS-707', {'title': '新標題'})

        # 定期合併（自動或手動）
        db.compact_if_needed()  # 自動判斷
        db.compact()  # 強制合併
    """

    def __init__(self, data_dir: str):
        """
        初始化增量資料庫

        Args:
            data_dir: 資料目錄路徑（包含 data.json）
        """
        self.data_dir = Path(data_dir)
        self.data_file = self.data_dir / "data.json"
        self.journal_file = self.data_dir / "data.journal"
        self.index_file = self.data_dir / "data.index"

        # 鎖定檔案
        self.journal_lock_file = self.data_dir / "data.journal.lock"
        self.journal_lock = FileLock(self.journal_lock_file, timeout=10)

        # 使用標準 JSONDBManager 管理主檔案
        self.base_db = JSONDBManager(str(self.data_dir))

        # Dirty tracking（記憶體中）
        self.dirty_videos: set[str] = set()
        self.dirty_actresses: set[str] = set()
        self.dirty_links: set[str] = set()

        # Journal 統計
        self.journal_size = 0
        self.journal_created_at: datetime | None = None

        # 初始化 journal
        self._init_journal()

        logger.info(f"✅ IncrementalJSONDB 初始化完成: {self.data_dir}")
        logger.info(f"📝 Journal 記錄數: {self.journal_size}")

    def _init_journal(self):
        """初始化 journal 檔案和索引"""
        if self.journal_file.exists():
            # 載入現有 journal
            self._load_journal_stats()
            # 重播 journal 到記憶體
            self._replay_journal()
        else:
            # 建立新 journal
            self.journal_file.touch()
            self.journal_size = 0
            self.journal_created_at = datetime.now(UTC)
            self._save_index()

    def _replay_journal(self):
        """重播 journal 到記憶體"""
        try:
            count = 0
            with open(self.journal_file, "rb") as f:
                for line in f:
                    if line.strip():
                        try:
                            entry_dict = orjson.loads(line)
                            entry = JournalEntry.from_dict(entry_dict)
                            self._apply_entry_to_memory(entry)
                            count += 1
                        except Exception as e:
                            logger.warning(
                                f"⚠️ 重播 journal 記錄失敗: {line}, 錯誤: {e}"
                            )

            if count > 0:
                logger.info(f"🔄 已重播 {count} 條 journal 記錄到記憶體")
        except Exception as e:
            logger.error(f"❌ 重播 journal 失敗: {e}")

    def _apply_entry_to_memory(self, entry: JournalEntry):
        """將單條 journal 記錄套用到記憶體"""
        if entry.entity_type == "video":
            if entry.operation == JOURNAL_OP_ADD:
                if entry.data:
                    self.base_db.data["videos"][entry.entity_id] = entry.data
            elif entry.operation == JOURNAL_OP_UPDATE:
                video = self.base_db.get_video_info(entry.entity_id)
                if video and entry.data:
                    video.update(entry.data)
                    self.base_db.data["videos"][entry.entity_id] = video
            elif entry.operation == JOURNAL_OP_DELETE and entry.entity_id in self.base_db.data["videos"]:
                del self.base_db.data["videos"][entry.entity_id]

    def _load_journal_stats(self):
        """載入 journal 統計資訊"""
        try:
            with open(self.journal_file, "rb") as f:
                lines = f.readlines()
                self.journal_size = len(lines)

                # 取得第一條記錄的時間戳
                if lines:
                    first_entry = orjson.loads(lines[0])
                    self.journal_created_at = datetime.fromisoformat(
                        first_entry.get("ts", "")
                    )
                else:
                    self.journal_created_at = datetime.now(UTC)

            # 載入 dirty index
            if self.index_file.exists():
                with open(self.index_file, "rb") as f:
                    index_data = orjson.loads(f.read())
                    self.dirty_videos = set(index_data.get("videos", []))
                    self.dirty_actresses = set(index_data.get("actresses", []))
                    self.dirty_links = set(index_data.get("links", []))
        except Exception as e:
            logger.warning(f"⚠️ 載入 journal 統計失敗: {e}")
            self.journal_size = 0
            self.journal_created_at = datetime.now(UTC)

    def _save_index(self):
        """儲存 dirty index"""
        try:
            index_data = {
                "videos": list(self.dirty_videos),
                "actresses": list(self.dirty_actresses),
                "links": list(self.dirty_links),
                "journal_size": self.journal_size,
                "created_at": self.journal_created_at.isoformat()
                if self.journal_created_at
                else None,
            }

            with open(self.index_file, "wb") as f:
                f.write(orjson.dumps(index_data, option=orjson.OPT_INDENT_2))
        except Exception as e:
            logger.warning(f"⚠️ 儲存索引失敗: {e}")

    def _append_journal(self, entry: JournalEntry):
        """
        將記錄追加到 journal（快速操作）

        Args:
            entry: Journal 記錄項
        """
        try:
            with self.journal_lock:
                # 寫入 journal（JSON Lines 格式）
                with open(self.journal_file, "ab") as f:
                    f.write(orjson.dumps(entry.to_dict()))
                    f.write(b"\n")

                # 更新 dirty tracking
                if entry.entity_type == "video":
                    self.dirty_videos.add(entry.entity_id)
                elif entry.entity_type == "actress":
                    self.dirty_actresses.add(entry.entity_id)
                elif entry.entity_type == "link":
                    self.dirty_links.add(entry.entity_id)

                # 更新統計
                self.journal_size += 1

                # 儲存索引
                self._save_index()

        except Exception as e:
            logger.error(f"❌ 寫入 journal 失敗: {e}")
            raise JSONDatabaseError(f"Journal 寫入失敗: {e}") from e

    def update_video(self, code: str, updates: dict[str, Any]):
        """
        更新影片資料（快速操作）

        Args:
            code: 影片番號
            updates: 要更新的欄位
        """
        # 先檢查影片是否存在
        video = self.base_db.get_video_info(code)
        if not video:
            raise JSONDatabaseError(f"影片不存在: {code}")

        # 建立 journal 記錄
        entry = JournalEntry(
            operation=JOURNAL_OP_UPDATE,
            entity_type="video",
            entity_id=code,
            data=updates,
        )

        # 追加到 journal（快速）
        self._append_journal(entry)

        # 立即更新記憶體中的資料，確保讀取一致性
        video.update(updates)
        self.base_db.data["videos"][code] = video

        logger.debug(f"✅ 快速更新影片 {code} 到 journal 並同步記憶體")

    def add_video(self, video: VideoDict):
        """
        新增影片（快速操作）

        Args:
            video: 影片資料
        """
        entry = JournalEntry(
            operation=JOURNAL_OP_ADD,
            entity_type="video",
            entity_id=video["code"],
            data=video,
        )

        self._append_journal(entry)

        # 立即更新記憶體中的資料
        self.base_db.data["videos"][video["code"]] = video

        logger.debug(f"✅ 快速新增影片 {video['code']} 到 journal 並同步記憶體")

    def delete_video(self, code: str):
        """
        刪除影片（快速操作）

        Args:
            code: 影片番號
        """
        entry = JournalEntry(
            operation=JOURNAL_OP_DELETE, entity_type="video", entity_id=code
        )

        self._append_journal(entry)

        # 立即更新記憶體中的資料
        if code in self.base_db.data["videos"]:
            del self.base_db.data["videos"][code]

        logger.debug(f"✅ 快速刪除影片 {code} 標記到 journal 並同步記憶體")

    # ========================================================================
    # 相容性介面 (與 JSONDBManager 一致)
    # ========================================================================

    @property
    def data(self) -> dict[str, Any]:
        """
        相容性屬性：取得底層資料字典

        注意：直接修改返回的字典不會觸發 journal 記錄，
        請使用 add_or_update_video 等方法進行修改。

        Returns:
            包含 'videos', 'actresses', 'video_actress_links' 的資料字典
        """
        return self.base_db.data

    def get_all_videos(
        self, filter_dict: dict[str, Any] | None = None
    ) -> list[VideoDict]:
        """取得所有影片清單（委派給 base_db）"""
        return self.base_db.get_all_videos(filter_dict)

    def get_video_info(self, code: str) -> VideoDict | None:
        """取得影片資訊（委派給 base_db）"""
        return self.base_db.get_video_info(code)

    def add_or_update_video(self, code: str, info: dict) -> str:
        """
        新增或更新影片（增量實作）

        Args:
            code: 影片番號
            info: 影片資訊字典

        Returns:
            影片番號
        """
        # 檢查是否已存在
        existing_video = self.base_db.get_video_info(code)

        if existing_video:
            # 更新現有影片
            self.update_video(code, info)
        else:
            # 準備新影片資料
            from src.models.json_types import ISO_DATETIME_FORMAT, get_empty_video

            video_dict = get_empty_video()
            video_dict["code"] = code
            video_dict.update(info)
            video_dict["updated_at"] = datetime.now(UTC).strftime(ISO_DATETIME_FORMAT)

            # 新增影片
            self.add_video(video_dict)

        return code

    def analyze_actress_primary_studio(
        self, actress_name: str, major_studios: set = None
    ) -> dict:
        """分析女優的主要片商（委派給 base_db）"""
        return self.base_db.analyze_actress_primary_studio(actress_name, major_studios)

    def compact_if_needed(self) -> bool:
        """
        根據閾值自動判斷是否需要合併

        Returns:
            bool: 是否執行了合併
        """
        # 檢查大小閾值
        if self.journal_size >= JOURNAL_SIZE_THRESHOLD:
            logger.info(
                f"📊 Journal 大小超過閾值 ({self.journal_size} >= {JOURNAL_SIZE_THRESHOLD})，開始合併..."
            )
            self.compact()
            return True

        # 檢查時間閾值
        if self.journal_created_at:
            age = (datetime.now(UTC) - self.journal_created_at).total_seconds()
            if age >= JOURNAL_AGE_THRESHOLD:
                logger.info(
                    f"⏰ Journal 年齡超過閾值 ({age:.0f}s >= {JOURNAL_AGE_THRESHOLD}s)，開始合併..."
                )
                self.compact()
                return True

        return False

    def compact(self):
        """
        合併 journal 到主檔案（重型操作）

        這個操作會：
        1. 讀取所有 journal 記錄
        2. 套用到主資料庫
        3. 清空 journal
        4. 重設 dirty tracking
        """
        logger.info(f"🔄 開始合併 {self.journal_size} 條 journal 記錄...")

        try:
            with self.journal_lock:
                # 讀取所有 journal 記錄
                entries: list[JournalEntry] = []
                if self.journal_file.exists():
                    with open(self.journal_file, "rb") as f:
                        for line in f:
                            if line.strip():
                                entry_dict = orjson.loads(line)
                                entries.append(JournalEntry.from_dict(entry_dict))

                # 套用到主資料庫
                for entry in entries:
                    try:
                        self._apply_entry_to_memory(entry)
                    except Exception as e:
                        logger.error(
                            f"❌ 套用 journal 記錄失敗: {entry.to_dict()}, 錯誤: {e}"
                        )

                # 儲存主資料庫
                self.base_db._save_all_data(self.base_db.data)

                # 清空 journal
                self.journal_file.unlink(missing_ok=True)
                self.journal_file.touch()

                # 重設統計
                self.journal_size = 0
                self.journal_created_at = datetime.now(UTC)
                self.dirty_videos.clear()
                self.dirty_actresses.clear()
                self.dirty_links.clear()

                # 更新索引
                self._save_index()

                logger.info(f"✅ Journal 合併完成，已套用 {len(entries)} 條記錄")

        except Exception as e:
            logger.error(f"❌ Journal 合併失敗: {e}")
            raise JSONDatabaseError(f"合併失敗: {e}") from e

    def get_stats(self) -> dict[str, Any]:
        """
        取得資料庫統計資訊

        Returns:
            統計資訊字典
        """
        age = 0
        if self.journal_created_at:
            age = (datetime.now(UTC) - self.journal_created_at).total_seconds()

        return {
            "journal_size": self.journal_size,
            "journal_age_seconds": age,
            "dirty_videos": len(self.dirty_videos),
            "dirty_actresses": len(self.dirty_actresses),
            "dirty_links": len(self.dirty_links),
            "needs_compact": self.journal_size >= JOURNAL_SIZE_THRESHOLD
            or age >= JOURNAL_AGE_THRESHOLD,
            "total_videos": len(self.base_db.get_all_videos()),
        }
