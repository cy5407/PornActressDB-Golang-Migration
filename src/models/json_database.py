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

# 設定日誌
logger = logging.getLogger(__name__)


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
        但不再接受舊版 `video_actress_links` 或 dict 型別的 `links`。
        """
        if not isinstance(loaded_data, dict):
            raise ValidationError("根層必須是字典")

        if "video_actress_links" in loaded_data:
            raise ValidationError(
                "已不再支援舊版 video_actress_links，請先遷移資料後再載入"
            )

        default_data = get_empty_json_database()
        normalized: JSONDatabaseDict = default_data.copy()
        normalized.update(loaded_data)

        if isinstance(normalized.get("links"), dict):
            raise ValidationError("'links' 必須是清單")

        statistics = normalized.get("statistics")
        if not isinstance(statistics, dict):
            normalized["statistics"] = default_data["statistics"]
        else:
            merged_statistics = default_data["statistics"].copy()
            merged_statistics.update(statistics)
            normalized["statistics"] = merged_statistics

        return normalized

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
                self._prepare_data_for_save(data)
                temp_file = self._write_temp_data_file(data)
                if not self._replace_data_file(
                    temp_file, attempt, max_retries, retry_delay
                ):
                    continue

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

    def _prepare_data_for_save(self, data: JSONDatabaseDict) -> None:
        self._validate_json_format(data)
        self._validate_referential_integrity(data)
        data["data_hash"] = self._calculate_data_hash(data)
        data["updated_at"] = datetime.now(UTC).strftime(ISO_DATETIME_FORMAT)

    @staticmethod
    def _calculate_data_hash(data: JSONDatabaseDict) -> str:
        data_copy = data.copy()
        data_copy["data_hash"] = ""
        data_bytes = orjson.dumps(data_copy, option=orjson.OPT_SORT_KEYS)
        return hashlib.sha256(data_bytes).hexdigest()

    def _write_temp_data_file(self, data: JSONDatabaseDict) -> Path:
        temp_file = self.data_file.parent / f"{self.data_file.name}.tmp"
        self._cleanup_existing_temp_file(temp_file)
        with open(temp_file, "wb") as file_obj:
            file_obj.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))
        return temp_file

    @staticmethod
    def _cleanup_existing_temp_file(temp_file: Path) -> None:
        if not temp_file.exists():
            return
        try:
            temp_file.unlink()
        except Exception as error:
            logger.debug(f"清理暫存檔失敗: {error}")

    def _replace_data_file(
        self,
        temp_file: Path,
        attempt: int,
        max_retries: int,
        retry_delay: float,
    ) -> bool:
        if self.data_file.exists():
            try:
                self.data_file.unlink()
            except PermissionError as error:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"檔案被鎖定（嘗試 {attempt + 1}/{max_retries}），等待後重試: {error}"
                    )
                    time.sleep(retry_delay * (attempt + 1))
                    return False
                raise
        temp_file.rename(self.data_file)
        return True

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
        if isinstance(result, dict) and result.get("path"):
            return result["path"]
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
        result = _go_db_backup_restore(
            backup_file=backup_path,
            data_dir=str(self.data_dir),
        )
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
        新增或更新影片（委派至 Go CLI）。

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
        查詢影片資訊（委派至 Go CLI）。

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
        取得所有影片清單（委派至 Go CLI）。

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
            raise RuntimeError(f"Go get_all_videos 失敗: {e}") from e

    def delete_video(self, code: str) -> bool:
        """
        刪除影片（委派至 Go CLI）。

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
            actress_videos = self._collect_actress_videos(actress_name)
            studio_stats, total_videos = self._build_studio_stats(actress_videos)
            if not studio_stats:
                return self._build_studio_analysis_result(
                    actress_name=actress_name,
                    primary_studio="UNKNOWN",
                    confidence=0.0,
                    total_videos=0,
                    studio_distribution={},
                    recommendation="solo_artist",
                    classification_type="no_data",
                    studio_count=0,
                )

            studio_count = len(studio_stats)
            if studio_count == 1 and total_videos >= 3:
                studio = next(iter(studio_stats))
                is_major = major_studios and studio in major_studios
                logger.debug(
                    f"🎯 專屬女優: {actress_name} → {studio} "
                    f"({total_videos} 部, 大片商: {is_major})"
                )
                return self._build_studio_analysis_result(
                    actress_name=actress_name,
                    primary_studio=studio,
                    confidence=100.0,
                    total_videos=total_videos,
                    studio_distribution=studio_stats,
                    recommendation="studio_classification"
                    if is_major
                    else "solo_artist",
                    classification_type="exclusive",
                    studio_count=1,
                )

            best_studio = max(
                studio_stats.items(), key=lambda item: item[1]["total_count"]
            )[0]
            best_stats = studio_stats[best_studio]
            max_ratio = best_stats["total_count"] / total_videos if total_videos > 0 else 0

            high_loyalty_result = self._find_high_loyalty_studio(
                actress_name, studio_stats, total_videos, studio_count, major_studios
            )
            if high_loyalty_result:
                return high_loyalty_result

            if studio_count >= 5 or (studio_count >= 3 and max_ratio < 0.40):
                confidence = round(max_ratio * 100, 1)
                logger.debug(
                    f"🎭 跨片商女優: {actress_name} "
                    f"({studio_count} 片商, 最高 {best_studio} {confidence}%)"
                )
                return self._build_studio_analysis_result(
                    actress_name=actress_name,
                    primary_studio=best_studio,
                    confidence=confidence,
                    total_videos=total_videos,
                    studio_distribution=studio_stats,
                    recommendation="solo_artist",
                    classification_type="multi_studio",
                    studio_count=studio_count,
                )

            best_studio, confidence, recommendation = self._determine_standard_classification(
                best_studio,
                best_stats,
                studio_stats,
                total_videos,
                max_ratio,
                major_studios,
            )
            logger.debug(
                f"📊 標準分類: {actress_name} → {best_studio} "
                f"({confidence}%, {recommendation})"
            )
            return self._build_studio_analysis_result(
                actress_name=actress_name,
                primary_studio=best_studio or "UNKNOWN",
                confidence=round(confidence, 1),
                total_videos=total_videos,
                studio_distribution=studio_stats,
                recommendation=recommendation,
                classification_type="standard",
                studio_count=studio_count,
            )
        except Exception as e:
            logger.error(f"❌ 分析女優主要片商失敗: {e}")
            raise

    def _collect_actress_videos(self, actress_name: str) -> list[VideoDict]:
        return [
            video
            for video in self.data.get("videos", {}).values()
            if actress_name in video.get("actresses", [])
        ]

    def _build_studio_stats(
        self, actress_videos: list[VideoDict]
    ) -> tuple[dict[str, dict[str, Any]], int]:
        studio_stats: dict[str, dict[str, Any]] = {}
        total_videos = 0
        for video in actress_videos:
            studio = video.get("studio")
            if not studio or studio == "UNKNOWN":
                continue
            total_videos += 1
            stats = studio_stats.setdefault(
                studio,
                {
                    "studio_code": video.get("studio_code", ""),
                    "primary_count": 0,
                    "collaboration_count": 0,
                    "total_count": 0,
                    "codes": [],
                },
            )
            stats["primary_count"] += 1
            stats["total_count"] += 1
            stats["codes"].append(video.get("code", ""))
        return studio_stats, total_videos

    @staticmethod
    def _build_studio_analysis_result(**kwargs) -> dict:
        return dict(kwargs)

    def _find_high_loyalty_studio(
        self,
        actress_name: str,
        studio_stats: dict[str, dict[str, Any]],
        total_videos: int,
        studio_count: int,
        major_studios: set | None,
    ) -> dict | None:
        if not major_studios:
            return None
        for studio, stats in studio_stats.items():
            if studio not in major_studios:
                continue
            studio_ratio = stats["total_count"] / total_videos
            if studio_ratio < 0.70 or stats["total_count"] < 5:
                continue
            confidence = round(studio_ratio * 100, 1)
            logger.debug(
                f"💎 高忠誠度女優: {actress_name} → {studio} "
                f"({stats['total_count']}/{total_videos} = {confidence}%)"
            )
            return self._build_studio_analysis_result(
                actress_name=actress_name,
                primary_studio=studio,
                confidence=confidence,
                total_videos=total_videos,
                studio_distribution=studio_stats,
                recommendation="studio_classification",
                classification_type="high_loyalty",
                studio_count=studio_count,
            )
        return None

    @staticmethod
    def _determine_standard_classification(
        best_studio: str,
        best_stats: dict[str, Any],
        studio_stats: dict[str, dict[str, Any]],
        total_videos: int,
        max_ratio: float,
        major_studios: set | None,
    ) -> tuple[str, float, str]:
        confidence = round(max_ratio * 100, 1)
        recommendation = "solo_artist"
        major_studio_stats = {
            studio: stats
            for studio, stats in studio_stats.items()
            if major_studios and studio in major_studios
        }
        if not major_studio_stats:
            return best_studio, confidence, recommendation

        major_studio_work_count = sum(
            stats["total_count"] for stats in major_studio_stats.values()
        )
        minor_studio_work_count = total_videos - major_studio_work_count
        best_major_studio, best_major_stats = max(
            major_studio_stats.items(), key=lambda item: item[1]["total_count"]
        )

        if best_major_studio == best_studio:
            if best_stats["total_count"] >= 3 and confidence >= 70:
                return best_studio, confidence, "studio_classification"
            if best_stats["total_count"] >= 1 and minor_studio_work_count < 10:
                return best_studio, max(confidence, 60.0), "studio_classification"
            return best_studio, confidence, recommendation

        if major_studio_work_count >= 1 and minor_studio_work_count < 10:
            major_confidence = (best_major_stats["total_count"] / total_videos) * 100
            return (
                best_major_studio,
                max(round(major_confidence, 1), 60.0),
                "studio_classification",
            )
        return best_studio, confidence, recommendation
