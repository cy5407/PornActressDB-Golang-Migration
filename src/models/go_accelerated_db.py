"""
Go 加速資料庫包裝器 (GoAcceleratedDB)

此模組提供 Go CLI 加速的資料庫操作，在 Go 不可用時自動 fallback 到 Python 實作。

設計理念：
- 優先使用 Go CLI 進行效能敏感操作（查詢、更新）
- 當 Go CLI 不可用時自動切換到 IncrementalJSONDB
- 保持與 IncrementalJSONDB 完全相同的 API
- 透明的 fallback 機制，調用者無需感知

效能差異：
- Go 查詢: ~64 ns/op（記憶體查詢）
- Go 更新: ~182 μs/op（含 journal 寫入）
- Python 查詢: ~5 ms/op
- Python 更新: ~250 ms/op

使用範例：
    from src.models.go_accelerated_db import GoAcceleratedDB

    # 優先使用 Go，不可用時 fallback 到 Python
    db = GoAcceleratedDB('data/json_db')

    # 與 IncrementalJSONDB 完全相同的 API
    video = db.get_video_info('SONE-001')
    db.update_video('SONE-001', {'title': '新標題'})
"""

import logging
from typing import Any

from src.models.incremental_json_database import IncrementalJSONDB
from src.models.json_types import VideoDict

logger = logging.getLogger(__name__)


class GoAcceleratedDB:
    """
    Go 加速資料庫包裝器

    提供與 IncrementalJSONDB 相同的介面，但優先使用 Go CLI 加速。
    當 Go CLI 不可用時自動 fallback 到 Python 實作。

    屬性：
        use_go (bool): 是否使用 Go 加速
        fallback_count (int): fallback 到 Python 的次數
    """

    def __init__(self, data_dir: str, use_go: bool = True):
        """
        初始化 Go 加速資料庫

        Args:
            data_dir: 資料目錄路徑
            use_go: 是否嘗試使用 Go 加速（預設 True）
        """
        self.data_dir = data_dir
        self._use_go = use_go
        self._go_bridge = None
        self._go_available = None
        self.fallback_count = 0

        # 始終初始化 Python 實作作為 fallback
        self._python_db = IncrementalJSONDB(data_dir)

        # 延遲檢查 Go 可用性
        if use_go:
            self._check_go_availability()

        mode = "Go 加速" if self.use_go else "Python"
        logger.info(f"✅ GoAcceleratedDB 初始化完成: {data_dir} (模式: {mode})")

    def _check_go_availability(self):
        """檢查 Go CLI 是否可用"""
        if self._go_available is not None:
            return self._go_available

        try:
            from src.services.go_bridge import GoBridge

            self._go_bridge = GoBridge()
            self._go_available = self._go_bridge.is_available

            if self._go_available:
                logger.info("🚀 Go CLI 可用，啟用加速模式")
            else:
                logger.warning("⚠️ Go CLI 不可用，使用 Python fallback")
        except ImportError as e:
            logger.warning(f"⚠️ 無法載入 Go 橋接層: {e}")
            self._go_available = False

        return self._go_available

    @property
    def use_go(self) -> bool:
        """是否正在使用 Go 加速"""
        return self._use_go and (self._go_available or False)

    @property
    def data(self) -> dict[str, Any]:
        """
        相容性屬性：取得底層資料字典

        注意：這是 fallback 行為，直接讀取 Python 資料庫的記憶體快取
        """
        return self._python_db.data

    @property
    def base_db(self):
        """相容性屬性：取得底層 JSONDBManager"""
        return self._python_db.base_db

    # ========================================================================
    # 核心資料庫操作（Go 加速 + Python fallback）
    # ========================================================================

    def get_video_info(self, code: str) -> VideoDict | None:
        """
        取得影片資訊

        優先使用 Go CLI，失敗時 fallback 到 Python。

        容錯邏輯：
            - Go 成功返回資料 → 直接回傳
            - Go 返回 None  → 影片不存在，不需要 fallback，直接回傳 None
            - Go 拋出 GoBridgeError → CLI 執行失敗，fallback 到 Python
        """
        if self.use_go:
            try:
                from src.services.go_bridge import GoBridgeError, db_get_video

                # db_get_video: 找到→回傳 dict, 不存在→回傳 None, CLI 故障→拋出 GoBridgeError
                result = db_get_video(code, self.data_dir)
                # None 表示「資料不存在」（Go CLI 正常執行但找不到），直接回傳，不需要 fallback
                return result
            except GoBridgeError as e:
                # Go CLI 執行失敗 → 記錄警告並 fallback 到 Python
                logger.warning(f"⚠️ Go 查詢失敗，fallback 到 Python (影片 {code}): {e}")  # Go CLI 執行失敗為 warning
                self.fallback_count += 1
            except Exception as e:
                # 其他意外錯誤（如 ImportError 等）→ 也 fallback
                logger.warning(f"⚠️ 查詢異常，fallback 到 Python (影片 {code}): {e}")  # 其他異常為 warning
                self.fallback_count += 1

        return self._python_db.get_video_info(code)

    def update_video(self, code: str, updates: dict[str, Any]):
        """
        更新影片資料

        優先使用 Go CLI，失敗時 fallback 到 Python。
        """
        if self.use_go:
            try:
                from src.services.go_bridge import db_update_video

                # 取得現有影片資料
                existing = self.get_video_info(code)  # 現有影片資訊
                if not existing:
                    raise ValueError(f"影片不存在: {code}")

                # 合併更新
                existing.update(updates)

                # 使用 Go 更新
                if db_update_video(code, existing, self.data_dir):
                    # Go 操作成功後重建 Python DB state，確保 dirty_videos/journal_size 等內部狀態一致
                    self._python_db = IncrementalJSONDB(self.data_dir)
                    logger.debug(f"✅ Go update_video 成功，已重建 Python 快取: {code}")
                    return

            except Exception as e:
                logger.debug(f"Go 更新失敗，fallback 到 Python: {e}")
                self.fallback_count += 1

        self._python_db.update_video(code, updates)

    def add_video(self, video: VideoDict):
        """
        新增影片

        優先使用 Go CLI，失敗時 fallback 到 Python。
        """
        if self.use_go:
            try:
                from src.services.go_bridge import db_update_video

                # Go CLI 使用 update 命令新增（不存在時自動建立）
                if db_update_video(video["code"], video, self.data_dir):
                    # Go 操作成功後重建 Python DB state，確保 dirty_videos/journal_size 等內部狀態一致
                    self._python_db = IncrementalJSONDB(self.data_dir)
                    logger.debug(f"✅ Go add_video 成功，已重建 Python 快取: {video['code']}")
                    return

            except Exception as e:
                logger.debug(f"Go 新增失敗，fallback 到 Python: {e}")
                self.fallback_count += 1

        self._python_db.add_video(video)

    def delete_video(self, code: str):
        """
        刪除影片

        優先使用 Go CLI，失敗時 fallback 到 Python。
        """
        if self.use_go:
            try:
                from src.services.go_bridge import db_delete_video

                if db_delete_video(code, self.data_dir):
                    # Go 操作成功後重建 Python DB state，確保 dirty_videos/journal_size 等內部狀態一致
                    self._python_db = IncrementalJSONDB(self.data_dir)
                    logger.debug(f"✅ Go delete_video 成功，已重建 Python 快取: {code}")
                    return

            except Exception as e:
                logger.debug(f"Go 刪除失敗，fallback 到 Python: {e}")
                self.fallback_count += 1

        self._python_db.delete_video(code)

    def get_stats(self) -> dict[str, Any]:
        """
        取得資料庫統計資訊

        優先使用 Go CLI，失敗時 fallback 到 Python。
        """
        if self.use_go:
            try:
                from src.services.go_bridge import db_get_stats

                result = db_get_stats(self.data_dir)
                if result:
                    # 增加額外的狀態資訊
                    result["go_accelerated"] = True
                    result["fallback_count"] = self.fallback_count
                    return result

            except Exception as e:
                logger.debug(f"Go 統計失敗，fallback 到 Python: {e}")
                self.fallback_count += 1

        stats = self._python_db.get_stats()
        stats["go_accelerated"] = False
        stats["fallback_count"] = self.fallback_count
        return stats

    def compact(self):
        """
        合併 journal 到主檔案

        優先使用 Go CLI，失敗時 fallback 到 Python。
        """
        if self.use_go:
            try:
                from src.services.go_bridge import db_compact_journal

                if db_compact_journal(self.data_dir):
                    # 重新載入 Python 資料庫以同步狀態
                    self._python_db = IncrementalJSONDB(self.data_dir)
                    logger.info("✅ Go compact 完成，已重新同步 Python 快取")
                    return

            except Exception as e:
                logger.debug(f"Go compact 失敗，fallback 到 Python: {e}")
                self.fallback_count += 1

        self._python_db.compact()

    def compact_if_needed(self) -> bool:
        """根據閾值自動判斷是否需要合併"""
        return self._python_db.compact_if_needed()

    # ========================================================================
    # 委派方法（直接使用 Python 實作）
    # ========================================================================

    def get_all_videos(
        self, filter_dict: dict[str, Any] | None = None
    ) -> list[VideoDict]:
        """取得所有影片清單"""
        return self._python_db.get_all_videos(filter_dict)

    def add_or_update_video(self, code: str, info: dict) -> str:
        """新增或更新影片"""
        existing = self.get_video_info(code)
        if existing:
            self.update_video(code, info)
        else:
            from src.models.json_types import ISO_DATETIME_FORMAT, UTC, get_empty_video
            from datetime import datetime  # UTC 由 json_types 提供，相容 Python 3.10

            video_dict = get_empty_video()
            video_dict["code"] = code
            video_dict.update(info)
            video_dict["updated_at"] = datetime.now(UTC).strftime(ISO_DATETIME_FORMAT)
            self.add_video(video_dict)

        return code

    def analyze_actress_primary_studio(
        self, actress_name: str, major_studios: set = None
    ) -> dict:
        """分析女優的主要片商"""
        return self._python_db.analyze_actress_primary_studio(actress_name, major_studios)


def get_database(data_dir: str = "data/json_db", use_go: bool = True) -> GoAcceleratedDB:
    """
    工廠函式：取得資料庫實例

    Args:
        data_dir: 資料目錄路徑
        use_go: 是否使用 Go 加速

    Returns:
        GoAcceleratedDB 實例
    """
    return GoAcceleratedDB(data_dir, use_go)
