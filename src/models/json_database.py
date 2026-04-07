"""
JSON 資料庫管理器 (JSONDBManager)

此模組提供 JSON 檔案型資料庫的核心管理功能，包括：
- 資料的載入和保存
- 基本 CRUD 操作
- 資料驗證和完整性檢查
"""

import hashlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import orjson
# Python 3.10 相容性：UTC 在 3.11+ 才新增，改用 timezone.utc
UTC = timezone.utc


from src.models.json_types import (
    ISO_DATETIME_FORMAT,
    SCHEMA_VERSION,
    ActressDict,
    CorruptedDataError,
    DataIntegrityError,
    JSONDatabaseDict,
    JSONDatabaseError,
    ValidationError,
    VideoDict,
    get_empty_json_database,
    get_empty_video,
)

# 設定日誌
logger = logging.getLogger(__name__)

try:
    from src.services.go_cli import (
        GoError as _GoBridgeError,
        GoNotFoundError as _GoBridgeNotFoundError,
        db_backup_cleanup as _go_db_backup_cleanup,
        db_backup_create as _go_db_backup_create,
        db_backup_list as _go_db_backup_list,
        db_backup_restore as _go_db_backup_restore,
        db_delete_actress as _go_db_delete_actress,
        db_delete_video as _go_db_delete_video,
        db_get_actress as _go_db_get_actress,
        db_get_all_videos as _go_db_get_all_videos,
        db_get_video as _go_db_get_video,
        db_update_actress as _go_db_update_actress,
        db_update_video as _go_db_update_video,
    )
except ImportError:
    def _go_db_backup_cleanup(*a, **kw): return {}  # noqa: E731
    def _go_db_backup_create(*a, **kw): return {}  # noqa: E731
    def _go_db_backup_list(*a, **kw): return []  # noqa: E731
    def _go_db_backup_restore(*a, **kw): return {}  # noqa: E731
    def _go_db_delete_actress(*a, **kw): return {}  # noqa: E731
    def _go_db_delete_video(*a, **kw): return {}  # noqa: E731
    def _go_db_get_actress(*a, **kw): return {}  # noqa: E731
    def _go_db_get_all_videos(*a, **kw): return []  # noqa: E731
    def _go_db_get_video(*a, **kw): return {}  # noqa: E731
    def _go_db_update_actress(*a, **kw): return {}  # noqa: E731
    def _go_db_update_video(*a, **kw): return {}  # noqa: E731

    class _GoBridgeError(Exception): pass  # noqa: E701
    class _GoBridgeNotFoundError(_GoBridgeError): pass  # noqa: E701


class JSONDBManager:
    """JSON 資料庫管理器類別

    提供 JSON 檔案型資料庫的管理功能。

    Attributes:
        data_file: JSON 資料庫檔案路徑
        backup_dir: 備份目錄路徑
        data: 記憶體中的資料快取
    """

    # 常數定義
    BACKUP_PATTERN = "backup_*.json"
    DEFAULT_BACKUP_DAYS = 30
    DEFAULT_BACKUP_MAX_COUNT = 50

    def __init__(self, data_dir: str = "data/json_db"):
        """
        初始化 JSONDBManager

        Args:
            data_dir: JSON 資料庫目錄路徑 (預設: "data/json_db")

        Raises:
            JSONDatabaseError: 若初始化失敗
        """
        try:
            # 設定檔案路徑
            self.data_dir = Path(data_dir)
            self.db_dir = self.data_dir  # 舊版測試/呼叫端相容別名
            self.data_file = self.data_dir / "data.json"
            self.backup_dir = self.data_dir / "backup"

            # 建立必需的目錄
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.backup_dir.mkdir(parents=True, exist_ok=True)

            # 初始化記憶體快取
            self.data: JSONDatabaseDict = get_empty_json_database()

            # 確保資料檔案存在
            self._ensure_data_file_exists()

            # 載入資料到記憶體
            self._load_all_data()

            logger.info(f"✅ JSONDBManager 初始化成功: {self.data_file}")

        except Exception as e:
            logger.error(f"❌ JSONDBManager 初始化失敗: {e}")
            raise JSONDatabaseError(f"初始化失敗: {e}") from e

    def _ensure_data_file_exists(self) -> None:
        """
        確保 JSON 資料檔案存在

        如果檔案不存在，建立初始的空資料庫。
        """
        if not self.data_file.exists():
            logger.info(f"建立新的 JSON 資料庫檔案: {self.data_file}")
            initial_data = get_empty_json_database()
            self._save_all_data(initial_data)

    def _load_all_data(self) -> None:
        """
        從磁碟載入所有資料到記憶體

        包含驗證檢查。

        Raises:
            CorruptedDataError: 若資料損壞或無法解析
        """
        try:
            self._load_data_internal()

        except CorruptedDataError:
            raise
        except Exception as e:
            logger.error(f"❌ 資料載入失敗: {e}")
            raise CorruptedDataError(f"載入失敗: {e}") from e

    def _load_data_internal(self) -> None:
        """
        內部載入方法（不獲取鎖）

        用於在已獲取鎖的情況下重新載入資料。

        Raises:
            CorruptedDataError: 若資料損壞或無法解析
        """
        try:
            if not self.data_file.exists():
                self._ensure_data_file_exists()
                return

            with open(self.data_file, "rb") as f:
                file_content = f.read()

            # 檢查檔案是否為空，若為空則初始化
            if not file_content:
                logger.warning(f"⚠️ JSON 資料檔案為空: {self.data_file}，正在初始化...")
                initial_data = get_empty_json_database()
                self._save_all_data(initial_data)
                self.data = initial_data
                return

            # 試圖解析 JSON (使用 orjson 加速)
            try:
                loaded_data = orjson.loads(file_content)
            except orjson.JSONDecodeError as e:
                logger.error(f"❌ JSON 解析失敗: {e}")
                raise CorruptedDataError(f"JSON 格式錯誤: {e}") from e

            loaded_data = self._normalize_loaded_data(loaded_data)

            # 驗證資料結構
            self._validate_json_format(loaded_data)

            # 驗證完整性
            self._validate_referential_integrity(loaded_data)

            self.data = loaded_data
            logger.debug(
                f"✅ 資料載入成功: {len(loaded_data.get('videos', {}))} 部影片"
            )

        except CorruptedDataError:
            raise
        except Exception as e:
            logger.error(f"❌ 內部資料載入失敗: {e}")
            raise CorruptedDataError(f"內部載入失敗: {e}") from e

    def _normalize_loaded_data(self, loaded_data: Any) -> JSONDatabaseDict:
        """
        將舊版資料結構補齊為目前 schema。

        支援缺少 `schema_version` / `links` / `statistics` 的舊資料，
        並將早期的 `video_actress_links` 轉為目前使用的 `links` 清單。
        """
        if not isinstance(loaded_data, dict):
            raise ValidationError("根層必須是字典")

        default_data = get_empty_json_database()
        normalized: JSONDatabaseDict = default_data.copy()
        normalized.update(loaded_data)

        legacy_links = loaded_data.get("video_actress_links")
        if "links" not in loaded_data and legacy_links is not None:
            normalized["links"] = self._normalize_legacy_links(legacy_links)
        elif isinstance(normalized.get("links"), dict):
            normalized["links"] = self._normalize_legacy_links(normalized["links"])

        statistics = normalized.get("statistics")
        if not isinstance(statistics, dict):
            normalized["statistics"] = default_data["statistics"]
        else:
            merged_statistics = default_data["statistics"].copy()
            merged_statistics.update(statistics)
            normalized["statistics"] = merged_statistics

        return normalized

    @staticmethod
    def _normalize_legacy_links(legacy_links: Any) -> list[dict[str, Any]]:
        """將舊版 link 結構統一為目前的 list 格式。"""
        if legacy_links is None:
            return []

        if isinstance(legacy_links, list):
            return legacy_links

        if not isinstance(legacy_links, dict):
            raise ValidationError("'links' 必須是清單")

        normalized_links: list[dict[str, Any]] = []
        for video_code, actress_ids in legacy_links.items():
            if not isinstance(actress_ids, list):
                continue
            for actress_id in actress_ids:
                if isinstance(actress_id, str):
                    normalized_links.append(
                        {
                            "video_code": video_code,
                            "actress_id": actress_id,
                        }
                    )

        return normalized_links

    def _save_all_data(self, data: JSONDatabaseDict) -> None:
        """
        原子寫入資料到磁碟（支援重試）

        包含資料雜湊計算和備份，並處理 OneDrive 鎖定問題。

        Args:
            data: 要儲存的資料字典

        Raises:
            DataIntegrityError: 若寫入驗證失敗
        """
        max_retries = 5
        retry_delay = 0.5  # 秒

        for attempt in range(max_retries):
            try:
                # 驗證資料
                self._validate_json_format(data)
                self._validate_referential_integrity(data)

                # 計算資料雜湊 (使用 orjson 加速)
                data_copy = data.copy()
                data_copy["data_hash"] = ""  # 暫時清空以計算雜湊
                data_bytes = orjson.dumps(data_copy, option=orjson.OPT_SORT_KEYS)
                data_hash = hashlib.sha256(data_bytes).hexdigest()
                data["data_hash"] = data_hash

                # 更新時間戳
                data["updated_at"] = datetime.now(UTC).strftime(ISO_DATETIME_FORMAT)

                # 原子寫入
                temp_file = self.data_file.parent / f"{self.data_file.name}.tmp"

                # 確保 temp 檔案不存在
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except Exception as e:
                        logger.debug(f"清理暫存檔失敗: {e}")

                with open(temp_file, "wb") as f:
                    # 使用 orjson 加速，OPT_INDENT_2 提供格式化輸出
                    f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))

                # 在替換前確保原檔案可訪問
                if self.data_file.exists():
                    # 在 Windows OneDrive 環境下，需要等待檔案完全釋放
                    try:
                        self.data_file.unlink()
                    except PermissionError as pe:
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"檔案被鎖定（嘗試 {attempt + 1}/{max_retries}），等待後重試: {pe}"
                            )
                            time.sleep(retry_delay * (attempt + 1))
                            continue
                        raise

                # 重新命名 temp 檔案
                temp_file.rename(self.data_file)

                logger.info(f"✅ 資料儲存成功: {self.data_file}")
                return  # 成功，退出循環

            except PermissionError as pe:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"PermissionError（嘗試 {attempt + 1}/{max_retries}），等待後重試: {pe}"
                    )
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                logger.error(f"❌ 資料儲存失敗（所有重試已用盡）: {pe}")
                raise DataIntegrityError(f"儲存失敗: {pe}") from pe
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"儲存失敗（嘗試 {attempt + 1}/{max_retries}），等待後重試: {e}"
                    )
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                logger.error(f"❌ 資料儲存失敗: {e}")
                raise DataIntegrityError(f"儲存失敗: {e}") from e

        # 如果所有重試都失敗
        raise DataIntegrityError("儲存失敗: 所有重試都已用盡")

    def _validate_json_format(self, data: Any) -> None:
        """
        驗證 JSON 格式和必需欄位

        Args:
            data: 要驗證的資料

        Raises:
            ValidationError: 若格式不正確
        """
        if not isinstance(data, dict):
            raise ValidationError("根層必須是字典")

        required_keys = {"schema_version", "videos", "actresses", "links", "statistics"}
        missing_keys = required_keys - set(data.keys())

        if missing_keys:
            raise ValidationError(f"遺失必需鍵: {missing_keys}")

        # 驗證 schema 版本
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValidationError(
                f"Schema 版本不符: 預期 {SCHEMA_VERSION}, 實際 {data.get('schema_version')}"
            )

        logger.debug("✅ JSON 格式驗證通過")

    def _validate_referential_integrity(self, data: dict[str, Any]) -> None:
        """
        驗證參照完整性（外鍵約束）

        Args:
            data: 要驗證的資料

        Raises:
            DataIntegrityError: 若完整性檢查失敗
        """
        videos = data.get("videos", {})
        actresses = data.get("actresses", {})
        links = data.get("links", [])

        # 檢查連結中的 video_code 和 actress_id 是否存在
        for link in links:
            video_code = link.get("video_code")
            actress_id = link.get("actress_id")

            if video_code and video_code not in videos:
                raise DataIntegrityError(f"連結中的 video_code '{video_code}' 不存在")

            if actress_id and actress_id not in actresses:
                raise DataIntegrityError(f"連結中的 actress_id '{actress_id}' 不存在")

        # 檢查影片中的 actresses 清單是否有效
        for code, video in videos.items():
            actresses_list = video.get("actresses", [])
            # actresses 現在儲存的是女優名稱列表(字串),而非 ID
            # 所以不需要驗證是否存在於 actresses 字典中
            # 只需要驗證格式是否正確
            if not isinstance(actresses_list, list):
                raise DataIntegrityError(f"影片 '{code}' 的 actresses 必須是列表")

        logger.debug("✅ 參照完整性驗證通過")

    # ========================================================================
    # 備份和恢復 (將在 T006 實現)
    # ========================================================================

    def create_backup(self) -> str:
        """
        建立備份

        建立當前資料的時間戳備份檔案。

        Returns:
            建立的備份檔案路徑

        Raises:
            BackupError: 若備份失敗
        """
        result = _go_db_backup_create(data_dir=str(self.data_dir))
        if result:
            return result
        raise RuntimeError("Go backup-create 回傳空結果")

    def restore_from_backup(self, backup_path: str) -> bool:
        """
        還原備份

        從備份檔案恢復資料。

        Args:
            backup_path: 備份檔案路徑

        Returns:
            成功則 True

        Raises:
            BackupError: 若還原失敗
        """
        result = _go_db_backup_restore(backup_path=backup_path, data_dir=str(self.data_dir))
        if result:
            # 重新載入記憶體
            self._load_data_internal()
            return True
        raise RuntimeError("Go backup-restore 回傳失敗")

    def get_backup_list(self) -> list[str]:
        """
        列出可用備份

        Returns:
            備份檔案路徑清單 (按時間排序)
        """
        result = _go_db_backup_list(data_dir=str(self.data_dir))
        if result is not None:
            return result
        raise RuntimeError("Go backup-list 回傳空結果")

    def cleanup_old_backups(self, days: int = None, max_count: int = None) -> int:
        """
        清理舊備份

        按日期和數量限制清理備份。

        Args:
            days: 保留天數 (預設: 30)
            max_count: 最大備份數 (預設: 50)

        Returns:
            刪除的備份數
        """
        if days is None:
            days = self.DEFAULT_BACKUP_DAYS
        if max_count is None:
            max_count = self.DEFAULT_BACKUP_MAX_COUNT

        deleted = _go_db_backup_cleanup(
            data_dir=str(self.data_dir), days=days, max_count=max_count
        )
        return deleted

    # ========================================================================
    # ========================================================================
    # CRUD 操作 (T010 實現)
    # ========================================================================

    def add_or_update_video(
        self, code: str | VideoDict, info: dict[str, Any] | None = None
    ) -> str:
        """
        新增或更新影片（優先委派至 Go CLI，不可用時 fallback 到 Python）。

        Args:
            code: 影片番號，或直接傳入包含 `code` 的影片資訊字典
            info: 影片資訊字典（當第一個參數為番號時必填）

        Returns:
            影片番號 (新建或已更新)
        """
        # 先建構 merged dict
        try:
            if isinstance(code, dict):
                if info is not None:
                    raise ValidationError("傳入影片字典時不可同時提供 info")
                video_info = code.copy()
                video_code = video_info.get("code")
            else:
                if not isinstance(info, dict):
                    raise ValidationError("影片資訊必須是字典")
                video_code = code
                video_info = info.copy()

            if not isinstance(video_code, str) or not video_code:
                raise ValidationError("影片番號必須存在")

            merged_dict = get_empty_video()
            merged_dict["code"] = video_code
            merged_dict.update(video_info)
            merged_dict["updated_at"] = datetime.now(UTC).strftime(
                ISO_DATETIME_FORMAT
            )

            success = _go_db_update_video(
                video_code, merged_dict, data_dir=str(self.data_dir)
            )
            if success:
                # 同步記憶體快取
                self.data["videos"][video_code] = merged_dict
                logger.info(f"✅ 影片已新增/更新 (Go): {video_code}")
                return video_code
            raise RuntimeError(f"Go db_update_video 回傳失敗: {video_code}")
        except (ValidationError, DataIntegrityError):
            raise
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Go 委派 add_or_update_video 失敗: {e}") from e

    def get_video_info(self, code: str) -> VideoDict | None:
        """
        查詢影片資訊（優先委派至 Go CLI，不可用時 fallback 到 Python）。

        Args:
            code: 影片番號

        Returns:
            影片資訊，若不存在則返回 None
        """
        try:
            result = _go_db_get_video(code, data_dir=str(self.data_dir))
            if result is not None:
                logger.debug(f"✅ 查詢影片成功 (Go): {code}")
            else:
                logger.debug(f"⚠️ 影片不存在 (Go): {code}")
            return result
        except _GoBridgeNotFoundError:
            logger.debug(f"⚠️ 影片不存在 (Go): {code}")
            return None
        except _GoBridgeError as e:
            raise RuntimeError(f"Go CLI 執行失敗: {e}") from e

    def get_all_videos(
        self, filter_dict: dict[str, Any] | None = None
    ) -> list[VideoDict]:
        """
        取得所有影片清單（優先委派至 Go CLI，不可用時 fallback 到 Python）。

        Args:
            filter_dict: 過濾條件 (例如: {'studio': 'ABC'})
                        支援的鍵: 'studio', 'release_date_after', 'release_date_before'

        Returns:
            影片清單
        """
        try:
            videos = _go_db_get_all_videos(data_dir=str(self.data_dir))
            # 確保每個影片有 code 欄位（與 Python 實作一致）
            for v in videos:
                if "code" not in v and "id" in v:
                    v["code"] = v["id"]
            if filter_dict:
                videos = self._apply_video_filters(videos, filter_dict)
            logger.debug(f"✅ 取得 {len(videos)} 個影片 (Go)")
            return videos
        except Exception as e:
            logger.warning(f"⚠️ Go 委派 get_all_videos 失敗，從記憶體返回: {e}")

        videos = self.data.get("videos", {})
        video_list = [
            {**v, "code": v.get("code") or v.get("id") or k}
            for k, v in videos.items()
        ]
        if filter_dict:
            video_list = self._apply_video_filters(video_list, filter_dict)
        return video_list

    def delete_video(self, code: str) -> bool:
        """
        刪除影片（優先委派至 Go CLI，不可用時 fallback 到 Python）。

        同時刪除相關的影片-女優關聯記錄。

        Args:
            code: 影片番號

        Returns:
            成功則返回 True，若影片不存在則返回 False
        """
        try:
            result = _go_db_delete_video(code, data_dir=str(self.data_dir))
            if result:
                # 同步記憶體快取：移除影片和相關關聯
                self.data["videos"].pop(code, None)
                links = self.data.get("links", [])
                self.data["links"] = [
                    link for link in links if link.get("video_code") != code
                ]
                logger.info(f"✅ 影片已刪除 (Go): {code}")
            else:
                logger.warning(f"⚠️ 影片不存在或刪除失敗 (Go): {code}")
            return result
        except Exception as e:
            logger.warning(f"⚠️ Go 委派 delete_video 失敗: {e}")
            raise RuntimeError(f"Go delete_video 失敗: {code}: {e}") from e

    def add_or_update_actress(self, actress_info: ActressDict) -> str:
        """
        新增或更新女優

        若女優 ID 已存在則更新，否則建立新記錄。

        Args:
            actress_info: 女優資訊 (ActressDict)

        Returns:
            女優 ID (新建或已更新)

        Raises:
            ValidationError: 若女優資訊無效
            CorruptedDataError: 若寫入失敗
        """
        if not isinstance(actress_info, dict):
            raise ValidationError("女優資訊必須是字典")
        if "id" not in actress_info:
            raise ValidationError("女優 ID 必須存在")

        actress_id = actress_info.get("id")

        if not actress_id:
            raise ValidationError("女優 ID 不得為空")

        try:
            success = _go_db_update_actress(actress_id, actress_info, data_dir=str(self.data_dir))
            if success:
                self.data["actresses"][actress_id] = actress_info
                logger.info(f"✅ 女優已新增/更新（Go）: {actress_id}")
                return actress_id
        except (ValidationError, DataIntegrityError):
            raise
        except Exception as e:
            logger.warning(f"⚠️ Go 委派 add_or_update_actress 失敗: {e}")
            raise RuntimeError(f"Go add_or_update_actress 失敗: {actress_id}: {e}") from e

        raise RuntimeError(f"Go db_update_actress 回傳失敗: {actress_id}")

    def get_actress_info(self, actress_id: str) -> ActressDict | None:
        """
        查詢女優資訊

        Args:
            actress_id: 女優 ID

        Returns:
            女優資訊，若不存在則返回 None
        """
        # Go 委派
        try:
            result = _go_db_get_actress(actress_id, data_dir=str(self.data_dir))
            if result is not None:
                logger.debug(f"✅ 查詢女優成功 (Go): {actress_id}")
            else:
                logger.debug(f"⚠️ 女優不存在 (Go): {actress_id}")
            return result
        except _GoBridgeNotFoundError:
            logger.debug(f"⚠️ 女優不存在 (Go): {actress_id}")
            return None
        except _GoBridgeError as e:
            raise RuntimeError(f"Go CLI 執行失敗: {e}") from e

    def delete_actress(self, actress_id: str) -> bool:
        """
        刪除女優

        同時刪除相關的影片-女優關聯記錄。

        Args:
            actress_id: 女優 ID

        Returns:
            成功則返回 True，若女優不存在則返回 False

        Raises:
            CorruptedDataError: 若刪除失敗
        """
        # Go 委派
        try:
            result = _go_db_delete_actress(actress_id, data_dir=str(self.data_dir))
            if result:
                self.data["actresses"].pop(actress_id, None)
                links = self.data.get("links", [])
                self.data["links"] = [
                    link for link in links if link.get("actress_id") != actress_id
                ]
                logger.info(f"✅ 女優已刪除 (Go): {actress_id}")
            else:
                logger.warning(f"⚠️ 女優不存在或刪除失敗 (Go): {actress_id}")
            return result
        except Exception as e:
            logger.warning(f"⚠️ Go 委派 delete_actress 失敗: {e}")
            raise RuntimeError(f"Go delete_actress 失敗: {actress_id}: {e}") from e

    # ========================================================================
    # 輔助方法
    # ========================================================================

    @staticmethod
    def _apply_video_filters(
        videos: list[VideoDict], filter_dict: dict[str, Any]
    ) -> list[VideoDict]:
        """
        應用過濾條件到影片清單

        支援的過濾鍵:
        - studio: 片商名稱 (精確匹配)
        - release_date_after: 發行日期下限 (ISO 8601)
        - release_date_before: 發行日期上限 (ISO 8601)

        Args:
            videos: 影片清單
            filter_dict: 過濾條件

        Returns:
            過濾後的影片清單
        """
        filtered = videos

        if "studio" in filter_dict:
            studio = filter_dict["studio"]
            filtered = [v for v in filtered if v.get("studio") == studio]

        if "release_date_after" in filter_dict:
            date_after = filter_dict["release_date_after"]
            filtered = [v for v in filtered if v.get("release_date", "") >= date_after]

        if "release_date_before" in filter_dict:
            date_before = filter_dict["release_date_before"]
            filtered = [v for v in filtered if v.get("release_date", "") <= date_before]

        return filtered

    def analyze_actress_primary_studio(
        self, actress_name: str, major_studios: set = None
    ) -> dict:
        """
        分析女優的主要片商（三層分類策略）

        根據女優的影片分布分析其主要片商，並提供分類建議。
        採用三層分類策略：
        1. 專屬女優快速通道：單一片商且 >= 3 部影片
        2. 高忠誠度女優：大片商占比 >= 70% 且 >= 5 部
        3. 跨片商女優：5+ 片商或 3+ 片商且無主導（< 40%）

        Args:
            actress_name: 女優名稱
            major_studios: 大片商集合 (可選)

        Returns:
            包含以下鍵值的字典:
            - actress_name: 女優名稱
            - primary_studio: 主要片商
            - confidence: 信心度 (0-100)
            - total_videos: 總影片數
            - studio_distribution: 片商分布統計
            - recommendation: 分類建議 ('studio_classification' 或 'solo_artist')
            - classification_type: 分類類型 ('exclusive', 'high_loyalty', 'multi_studio', 'standard')
            - studio_count: 片商數量
        """
        try:
            videos = self.data.get("videos", {})

            # 找出該女優的所有影片
            actress_videos = []
            for _code, video in videos.items():
                actresses = video.get("actresses", [])
                if actress_name in actresses:
                    actress_videos.append(video)

            # 統計片商分布
            studio_stats = {}
            total_videos = 0

            for video in actress_videos:
                studio = video.get("studio")
                if not studio or studio == "UNKNOWN":
                    continue

                studio_code = video.get("studio_code", "")
                total_videos += 1

                if studio not in studio_stats:
                    studio_stats[studio] = {
                        "studio_code": studio_code,
                        "primary_count": 1,  # JSON 資料庫中沒有 association_type,全部視為 primary
                        "collaboration_count": 0,
                        "total_count": 0,
                        "codes": [],
                    }

                studio_stats[studio]["total_count"] += 1
                studio_stats[studio]["codes"].append(video.get("code", ""))

            # 如果沒有影片資料
            if not studio_stats:
                return {
                    "actress_name": actress_name,
                    "primary_studio": "UNKNOWN",
                    "confidence": 0.0,
                    "total_videos": 0,
                    "studio_distribution": {},
                    "recommendation": "solo_artist",
                    "classification_type": "no_data",
                    "studio_count": 0,
                }

            studio_count = len(studio_stats)

            # ========== 第一層：專屬女優快速通道 ==========
            # 條件：只有 1 個片商且至少 3 部影片
            if studio_count == 1 and total_videos >= 3:
                studio = list(studio_stats.keys())[0]
                is_major = major_studios and studio in major_studios
                logger.debug(
                    f"🎯 專屬女優: {actress_name} → {studio} "
                    f"({total_videos} 部, 大片商: {is_major})"
                )
                return {
                    "actress_name": actress_name,
                    "primary_studio": studio,
                    "confidence": 100.0,
                    "total_videos": total_videos,
                    "studio_distribution": studio_stats,
                    "recommendation": "studio_classification" if is_major else "solo_artist",
                    "classification_type": "exclusive",
                    "studio_count": 1,
                }

            # 找出作品數最多的片商
            best_studio = max(
                studio_stats.items(), key=lambda x: x[1]["total_count"]
            )[0]
            best_stats = studio_stats[best_studio]

            # 計算最高占比
            max_ratio = best_stats["total_count"] / total_videos if total_videos > 0 else 0

            # ========== 第二層：高忠誠度女優 ==========
            # 條件：大片商占比 >= 70% 且至少 5 部作品
            if major_studios:
                for studio, stats in studio_stats.items():
                    if studio in major_studios:
                        studio_ratio = stats["total_count"] / total_videos
                        if studio_ratio >= 0.70 and stats["total_count"] >= 5:
                            confidence = round(studio_ratio * 100, 1)
                            logger.debug(
                                f"💎 高忠誠度女優: {actress_name} → {studio} "
                                f"({stats['total_count']}/{total_videos} = {confidence}%)"
                            )
                            return {
                                "actress_name": actress_name,
                                "primary_studio": studio,
                                "confidence": confidence,
                                "total_videos": total_videos,
                                "studio_distribution": studio_stats,
                                "recommendation": "studio_classification",
                                "classification_type": "high_loyalty",
                                "studio_count": studio_count,
                            }

            # ========== 第三層：跨片商女優判定 ==========
            # 條件 A：跨 5+ 片商，直接歸入單體企劃
            if studio_count >= 5:
                confidence = round(max_ratio * 100, 1)
                logger.debug(
                    f"🎭 跨片商女優 (5+): {actress_name} "
                    f"({studio_count} 片商, 主要 {best_studio} {confidence}%)"
                )
                return {
                    "actress_name": actress_name,
                    "primary_studio": best_studio,
                    "confidence": confidence,
                    "total_videos": total_videos,
                    "studio_distribution": studio_stats,
                    "recommendation": "solo_artist",
                    "classification_type": "multi_studio",
                    "studio_count": studio_count,
                }

            # 條件 B：跨 3+ 片商且最高占比 < 40%
            if studio_count >= 3 and max_ratio < 0.40:
                confidence = round(max_ratio * 100, 1)
                logger.debug(
                    f"🎭 跨片商女優 (無主導): {actress_name} "
                    f"({studio_count} 片商, 最高 {best_studio} {confidence}%)"
                )
                return {
                    "actress_name": actress_name,
                    "primary_studio": best_studio,
                    "confidence": confidence,
                    "total_videos": total_videos,
                    "studio_distribution": studio_stats,
                    "recommendation": "solo_artist",
                    "classification_type": "multi_studio",
                    "studio_count": studio_count,
                }

            # ========== 第四層：標準分類邏輯 ==========
            confidence = round(max_ratio * 100, 1)
            recommendation = "solo_artist"
            has_major_studio_work = False
            major_studio_work_count = 0
            minor_studio_work_count = 0
            best_major_studio = None
            best_major_count = 0

            if major_studios:
                for studio, stats in studio_stats.items():
                    if studio in major_studios:
                        has_major_studio_work = True
                        major_studio_work_count += stats["total_count"]
                        if stats["total_count"] > best_major_count:
                            best_major_count = stats["total_count"]
                            best_major_studio = studio
                    else:
                        minor_studio_work_count += stats["total_count"]

            # 標準分類邏輯
            if has_major_studio_work:
                if best_major_studio and best_major_studio == best_studio:
                    # 最佳片商就是大片商
                    if best_stats["total_count"] >= 3 and confidence >= 70:
                        recommendation = "studio_classification"
                    elif (
                        best_stats["total_count"] >= 1
                        and minor_studio_work_count < 10
                    ):
                        recommendation = "studio_classification"
                        confidence = max(confidence, 60.0)
                elif best_major_studio and major_studio_work_count >= 1 and minor_studio_work_count < 10:
                    # 最佳片商不是大片商,但有大片商作品
                    recommendation = "studio_classification"
                    best_studio = best_major_studio
                    major_studio_confidence = (
                        studio_stats[best_major_studio]["total_count"]
                        / total_videos
                    ) * 100
                    confidence = max(round(major_studio_confidence, 1), 60.0)

            logger.debug(
                f"📊 標準分類: {actress_name} → {best_studio} "
                f"({confidence}%, {recommendation})"
            )

            return {
                "actress_name": actress_name,
                "primary_studio": best_studio or "UNKNOWN",
                "confidence": round(confidence, 1),
                "total_videos": total_videos,
                "studio_distribution": studio_stats,
                "recommendation": recommendation,
                "classification_type": "standard",
                "studio_count": studio_count,
            }

        except Exception as e:
            logger.error(f"❌ 分析女優主要片商失敗: {e}")
            raise
