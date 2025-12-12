"""
JSON 資料庫管理器 (JSONDBManager)

此模組提供 JSON 檔案型資料庫的核心管理功能，包括：
- 檔案鎖定機制（讀寫並行控制）
- 資料的載入和保存
- 基本 CRUD 操作
- 資料驗證和完整性檢查
"""

import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson
from filelock import FileLock

from src.models.json_types import (
    ISO_DATETIME_FORMAT,
    READ_LOCK_TIMEOUT,
    SCHEMA_VERSION,
    WRITE_LOCK_TIMEOUT,
    ActressDict,
    BackupError,
    CorruptedDataError,
    DataIntegrityError,
    JSONDatabaseDict,
    JSONDatabaseError,
    LockError,
    ValidationError,
    VideoDict,
    get_empty_actress,
    get_empty_json_database,
    get_empty_video,
)

# 設定日誌
logger = logging.getLogger(__name__)


class JSONDBManager:
    """JSON 資料庫管理器類別

    提供 JSON 檔案型資料庫的管理功能，支援並行讀寫操作。

    Attributes:
        data_file: JSON 資料庫檔案路徑
        backup_dir: 備份目錄路徑
        read_lock: 讀操作鎖定物件
        write_lock: 寫操作鎖定物件
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
            self.data_file = self.data_dir / "data.json"
            self.backup_dir = self.data_dir / "backup"

            # 建立必需的目錄
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.backup_dir.mkdir(parents=True, exist_ok=True)

            # 初始化鎖定機制
            lock_file = self.data_dir / "db.lock"
            self.read_lock = FileLock(str(lock_file), timeout=READ_LOCK_TIMEOUT)
            self.write_lock = FileLock(str(lock_file), timeout=WRITE_LOCK_TIMEOUT)

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
            with self.read_lock:
                self._load_data_internal()

        except LockError as e:
            logger.error(f"❌ 讀鎖定失敗: {e}")
            raise
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

            # 試圖解析 JSON (使用 orjson 加速)
            try:
                loaded_data = orjson.loads(file_content)
            except orjson.JSONDecodeError as e:
                logger.error(f"❌ JSON 解析失敗: {e}")
                raise CorruptedDataError(f"JSON 格式錯誤: {e}") from e

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

    def _save_all_data(self, data: JSONDatabaseDict) -> None:
        """
        原子寫入資料到磁碟（支援重試）

        包含資料雜湊計算和備份，並處理 OneDrive 鎖定問題。

        Args:
            data: 要儲存的資料字典

        Raises:
            LockError: 若無法獲得寫鎖定
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

                with self.write_lock:
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
            except LockError as e:
                logger.error(f"❌ 寫鎖定失敗: {e}")
                raise
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

    def _validate_structure(self, data: dict[str, Any]) -> None:
        """
        驗證資料結構和欄位類型（第二層驗證）

        Args:
            data: 要驗證的資料

        Raises:
            ValidationError: 若結構或欄位類型不正確
        """
        # 驗證 videos 結構
        videos = data.get("videos", {})
        if not isinstance(videos, dict):
            raise ValidationError("'videos' 必須是字典")

        for code, video in videos.items():
            if not isinstance(video, dict):
                raise ValidationError(f"影片 '{code}' 必須是字典")

            # 必需欄位
            required_video_fields = {"code", "title", "studio", "release_date"}
            missing = required_video_fields - set(video.keys())
            if missing:
                raise ValidationError(f"影片 '{code}' 缺少欄位: {missing}")

            # 欄位類型檢查
            if not isinstance(video.get("code"), str):
                raise ValidationError(f"影片 '{code}' 的 'code' 必須是字串")
            if not isinstance(video.get("actresses"), list):
                raise ValidationError(f"影片 '{code}' 的 'actresses' 必須是清單")

        # 驗證 actresses 結構
        actresses = data.get("actresses", {})
        if not isinstance(actresses, dict):
            raise ValidationError("'actresses' 必須是字典")

        for actress_id, actress in actresses.items():
            if not isinstance(actress, dict):
                raise ValidationError(f"女優 '{actress_id}' 必須是字典")

            required_actress_fields = {"id", "name"}
            missing = required_actress_fields - set(actress.keys())
            if missing:
                raise ValidationError(f"女優 '{actress_id}' 缺少欄位: {missing}")

        # 驗證 links 結構
        links = data.get("links", [])
        if not isinstance(links, list):
            raise ValidationError("'links' 必須是清單")

        for idx, link in enumerate(links):
            if not isinstance(link, dict):
                raise ValidationError(f"連結 {idx} 必須是字典")

            required_link_fields = {"video_code", "actress_id"}
            missing = required_link_fields - set(link.keys())
            if missing:
                raise ValidationError(f"連結 {idx} 缺少欄位: {missing}")

        logger.debug("✅ 資料結構驗證通過")

    def _validate_consistency(self) -> bool:
        """
        驗證統計快取一致性（第四層驗證）

        驗證快取統計是否與實際資料一致。

        Returns:
            bool: 一致則 True
        """
        try:
            data = self.data
            actresses = data.get("actresses", {})
            links = data.get("links", [])

            # 計算實際的女優出演部數
            actual_actress_counts = {}
            for link in links:
                actress_id = link.get("actress_id")
                if actress_id:
                    actual_actress_counts[actress_id] = (
                        actual_actress_counts.get(actress_id, 0) + 1
                    )

            # 驗證 actresses 的 video_count 是否一致
            for actress_id, actress in actresses.items():
                expected_count = actual_actress_counts.get(actress_id, 0)
                actual_count = actress.get("video_count", 0)

                if expected_count != actual_count:
                    logger.warning(
                        f"女優 '{actress_id}' 的 video_count 不一致: "
                        f"預期 {expected_count}, 實際 {actual_count}"
                    )
                    return False

            logger.debug("✅ 一致性驗證通過")
            return True

        except Exception as e:
            logger.error(f"❌ 一致性檢查失敗: {e}")
            return False

    def validate_data(self) -> dict[str, Any]:
        """
        執行全面的資料驗證

        Returns:
            驗證結果字典，包含:
            - 'valid' (bool): 是否有效
            - 'errors' (List[str]): 錯誤訊息清單
        """
        result = {
            "valid": True,
            "errors": [],
        }

        try:
            self._validate_json_format(self.data)
        except ValidationError as e:
            result["valid"] = False
            result["errors"].append(f"格式驗證失敗: {e}")

        try:
            self._validate_referential_integrity(self.data)
        except DataIntegrityError as e:
            result["valid"] = False
            result["errors"].append(f"完整性驗證失敗: {e}")

        if not self._validate_consistency():
            result["valid"] = False
            result["errors"].append("一致性驗證失敗")

        return result

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
        try:
            from datetime import datetime

            timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
            backup_filename = f"backup_{timestamp}.json"
            backup_path = self.backup_dir / backup_filename

            # 複製資料
            with open(self.data_file, encoding="utf-8") as src:
                content = src.read()

            with open(backup_path, "w", encoding="utf-8") as dst:
                dst.write(content)

            logger.info(f"✅ 備份建立成功: {backup_path}")
            return str(backup_path)

        except Exception as e:
            logger.error(f"❌ 備份失敗: {e}")
            raise BackupError(f"備份失敗: {e}") from e

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
        try:
            backup_file = Path(backup_path)

            if not backup_file.exists():
                raise BackupError(f"備份檔案不存在: {backup_path}")

            # 載入備份資料
            with open(backup_file, encoding="utf-8") as f:
                backup_data = json.load(f)

            # 驗證備份資料
            self._validate_json_format(backup_data)
            self._validate_referential_integrity(backup_data)

            # 寫入
            self._save_all_data(backup_data)
            self.data = backup_data

            logger.info(f"✅ 備份還原成功: {backup_path}")
            return True

        except json.JSONDecodeError as e:
            logger.error(f"❌ 備份檔案損壞: {e}")
            raise BackupError(f"備份檔案損壞: {e}") from e
        except Exception as e:
            logger.error(f"❌ 還原失敗: {e}")
            raise BackupError(f"還原失敗: {e}") from e

    def get_backup_list(self) -> list[str]:
        """
        列出可用備份

        Returns:
            備份檔案路徑清單 (按時間排序)
        """
        try:
            backup_files = sorted(self.backup_dir.glob(self.BACKUP_PATTERN))
            return [str(f) for f in backup_files]
        except Exception as e:
            logger.error(f"❌ 無法列出備份: {e}")
            return []

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

        try:
            from datetime import timedelta

            deleted_count = 0
            cutoff_date = datetime.now(UTC) - timedelta(days=days)

            # 按時間刪除
            backup_files = list(self.backup_dir.glob(self.BACKUP_PATTERN))
            for backup_file in backup_files:
                if self._is_backup_expired(backup_file, cutoff_date):
                    backup_file.unlink()
                    deleted_count += 1
                    logger.info(f"刪除舊備份: {backup_file}")

            # 按數量刪除
            backup_files = sorted(self.backup_dir.glob(self.BACKUP_PATTERN))
            while len(backup_files) > max_count:
                oldest = backup_files[0]
                oldest.unlink()
                deleted_count += 1
                logger.info(f"刪除超限備份: {oldest}")
                backup_files = sorted(self.backup_dir.glob(self.BACKUP_PATTERN))

            logger.info(f"✅ 備份清理完成，刪除 {deleted_count} 個備份")
            return deleted_count

        except Exception as e:
            logger.error(f"❌ 備份清理失敗: {e}")
            return 0

    @staticmethod
    def _is_backup_expired(backup_file: Path, cutoff_date: datetime) -> bool:
        """檢查備份是否過期"""
        try:
            date_str = backup_file.stem.replace("backup_", "")
            date_part = date_str.split("_")[0]  # YYYY-MM-DD
            file_date = datetime.strptime(date_part, "%Y-%m-%d").replace(tzinfo=UTC)
            return file_date < cutoff_date
        except Exception as e:
            logger.warning(f"無法解析備份檔案日期: {backup_file}, {e}")
            return False

    # ========================================================================
    # 並行鎖定 (已在 __init__ 實現)
    # ========================================================================

    def _acquire_read_lock(self, timeout: int = READ_LOCK_TIMEOUT) -> None:
        """
        獲取讀鎖定

        允許多個讀操作並行執行。

        Args:
            timeout: 等待超時 (秒)

        Raises:
            LockError: 若無法獲取鎖定
        """
        try:
            self.read_lock.acquire(timeout=timeout)
            logger.debug("✅ 讀鎖定已獲取")
        except Exception as e:
            logger.error(f"❌ 無法獲得讀鎖定: {e}")
            raise LockError(f"無法獲得讀鎖定: {e}") from e

    def _acquire_write_lock(self, timeout: int = WRITE_LOCK_TIMEOUT) -> None:
        """
        獲取寫鎖定

        獨佔鎖定，確保寫操作不被干擾。

        Args:
            timeout: 等待超時 (秒)

        Raises:
            LockError: 若無法獲取鎖定
        """
        try:
            self.write_lock.acquire(timeout=timeout)
            logger.debug("✅ 寫鎖定已獲取")
        except Exception as e:
            logger.error(f"❌ 無法獲得寫鎖定: {e}")
            raise LockError(f"無法獲得寫鎖定: {e}") from e

    def _release_locks(self) -> None:
        """
        釋放所有鎖定

        在操作完成後釋放已獲取的鎖定。
        安全處理已釋放的鎖定物件。
        """
        try:
            if self.read_lock.is_locked:
                self.read_lock.release()
                logger.debug("✅ 讀鎖定已釋放")
        except Exception as e:
            logger.warning(f"⚠️ 釋放讀鎖定時發生錯誤: {e}")

        try:
            if self.write_lock.is_locked:
                self.write_lock.release()
                logger.debug("✅ 寫鎖定已釋放")
        except Exception as e:
            logger.warning(f"⚠️ 釋放寫鎖定時發生錯誤: {e}")

    def __enter__(self):
        """上下文管理器進入"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self._release_locks()
        return False

    # ========================================================================
    # CRUD 操作 (T010 實現)
    # ========================================================================

    def add_or_update_video(self, code: str, info: dict) -> str:
        """
        新增或更新影片

        若影片番號已存在則更新，否則建立新記錄。

        Args:
            code: 影片番號 (例如: "DOCZ-004")
            info: 影片資訊字典

        Returns:
            影片番號 (新建或已更新)

        Raises:
            ValidationError: 若影片資訊無效
            LockError: 若無法獲得寫鎖定
            CorruptedDataError: 若寫入失敗
        """
        try:
            # 驗證輸入
            if not isinstance(info, dict):
                raise ValidationError("影片資訊必須是字典")

            if not code:
                raise ValidationError("影片番號必須存在")

            # 獲取寫鎖定
            self._acquire_write_lock()

            try:
                # 重新載入最新資料
                self._load_data_internal()

                # 準備影片資料
                video_dict = get_empty_video()
                video_dict["code"] = code
                video_dict.update(info)
                video_dict["updated_at"] = datetime.now(UTC).strftime(
                    ISO_DATETIME_FORMAT
                )

                # 新增或更新
                self.data["videos"][code] = video_dict

                # 驗證完整性
                self._validate_referential_integrity(self.data)

                # 更新統計快取（快取失效策略）
                self._cache_statistics()

                # 保存
                self._save_all_data(self.data)

                logger.info(f"✅ 影片已新增/更新: {code}")
                return code

            finally:
                self._release_locks()

        except (ValidationError, DataIntegrityError, LockError) as e:
            logger.error(f"❌ 新增/更新影片失敗: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 未預期的錯誤: {e}")
            raise CorruptedDataError(f"新增/更新影片失敗: {e}") from e

    def get_video_info(self, code: str) -> VideoDict | None:
        """
        查詢影片資訊

        Args:
            code: 影片番號

        Returns:
            影片資訊，若不存在則返回 None

        Raises:
            LockError: 若無法獲得讀鎖定
        """
        try:
            # 獲取讀鎖定
            self._acquire_read_lock()

            try:
                videos = self.data.get("videos", {})
                video = videos.get(code)

                if video:
                    logger.debug(f"✅ 查詢影片成功: {code}")
                    return video
                else:
                    logger.debug(f"⚠️ 影片不存在: {code}")
                    return None

            finally:
                self._release_locks()

        except LockError as e:
            logger.error(f"❌ 無法獲取讀鎖定: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 查詢影片失敗: {e}")
            raise

    def get_all_videos(
        self, filter_dict: dict[str, Any] | None = None
    ) -> list[VideoDict]:
        """
        取得所有影片清單（支援過濾）

        Args:
            filter_dict: 過濾條件 (例如: {'studio': 'ABC'})
                        支援的鍵: 'studio', 'release_date_after', 'release_date_before'

        Returns:
            影片清單

        Raises:
            LockError: 若無法獲得讀鎖定
        """
        try:
            # 獲取讀鎖定
            self._acquire_read_lock()

            try:
                videos = self.data.get("videos", {})
                video_list = []

                # 處理每個影片，確保有 code 欄位（統一格式）
                for code, video in videos.items():
                    # 如果影片字典中沒有 code 欄位，但有 id 欄位，則使用 id 或鍵值作為 code
                    if "code" not in video:
                        if "id" in video:
                            video["code"] = video["id"]
                        else:
                            video["code"] = code
                    video_list.append(video)

                # 應用過濾
                if filter_dict:
                    video_list = self._apply_video_filters(video_list, filter_dict)

                logger.debug(f"✅ 取得 {len(video_list)} 個影片")
                return video_list

            finally:
                self._release_locks()

        except LockError as e:
            logger.error(f"❌ 無法獲取讀鎖定: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 取得影片清單失敗: {e}")
            raise

    def delete_video(self, code: str) -> bool:
        """
        刪除影片

        同時刪除相關的影片-女優關聯記錄。

        Args:
            code: 影片番號

        Returns:
            成功則返回 True，若影片不存在則返回 False

        Raises:
            LockError: 若無法獲得寫鎖定
            CorruptedDataError: 若刪除失敗
        """
        try:
            # 獲取寫鎖定
            self._acquire_write_lock()

            try:
                # 重新載入最新資料
                self._load_data_internal()

                videos = self.data.get("videos", {})

                # 檢查影片是否存在
                if code not in videos:
                    logger.warning(f"⚠️ 影片不存在: {code}")
                    return False

                # 刪除影片
                del videos[code]

                # 刪除相關的影片-女優關聯
                links = self.data.get("links", [])
                self.data["links"] = [
                    link for link in links if link.get("video_code") != code
                ]

                # 驗證完整性
                self._validate_referential_integrity(self.data)

                # 更新統計快取（快取失效策略）
                self._cache_statistics()

                # 保存
                self._save_all_data(self.data)

                logger.info(f"✅ 影片已刪除: {code}")
                return True

            finally:
                self._release_locks()

        except (DataIntegrityError, LockError) as e:
            logger.error(f"❌ 刪除影片失敗: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 未預期的錯誤: {e}")
            raise CorruptedDataError(f"刪除影片失敗: {e}") from e

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
            LockError: 若無法獲得寫鎖定
            CorruptedDataError: 若寫入失敗
        """
        try:
            # 驗證輸入
            if not isinstance(actress_info, dict):
                raise ValidationError("女優資訊必須是字典")

            if "id" not in actress_info:
                raise ValidationError("女優 ID 必須存在")

            actress_id = actress_info.get("id")

            # 獲取寫鎖定
            self._acquire_write_lock()

            try:
                # 重新載入最新資料
                self._load_data_internal()

                # 準備女優資料
                actress_dict = get_empty_actress()
                actress_dict.update(actress_info)
                actress_dict["updated_at"] = datetime.now(UTC).strftime(
                    ISO_DATETIME_FORMAT
                )

                # 新增或更新
                self.data["actresses"][actress_id] = actress_dict

                # 驗證完整性
                self._validate_referential_integrity(self.data)

                # 更新統計快取（快取失效策略）
                self._cache_statistics()

                # 保存
                self._save_all_data(self.data)

                logger.info(f"✅ 女優已新增/更新: {actress_id}")
                return actress_id

            finally:
                self._release_locks()

        except (ValidationError, DataIntegrityError, LockError) as e:
            logger.error(f"❌ 新增/更新女優失敗: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 未預期的錯誤: {e}")
            raise CorruptedDataError(f"新增/更新女優失敗: {e}") from e

    def get_actress_info(self, actress_id: str) -> ActressDict | None:
        """
        查詢女優資訊

        Args:
            actress_id: 女優 ID

        Returns:
            女優資訊，若不存在則返回 None

        Raises:
            LockError: 若無法獲得讀鎖定
        """
        try:
            # 獲取讀鎖定
            self._acquire_read_lock()

            try:
                actresses = self.data.get("actresses", {})
                actress = actresses.get(actress_id)

                if actress:
                    logger.debug(f"✅ 查詢女優成功: {actress_id}")
                    return actress
                else:
                    logger.debug(f"⚠️ 女優不存在: {actress_id}")
                    return None

            finally:
                self._release_locks()

        except LockError as e:
            logger.error(f"❌ 無法獲取讀鎖定: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 查詢女優失敗: {e}")
            raise

    def delete_actress(self, actress_id: str) -> bool:
        """
        刪除女優

        同時刪除相關的影片-女優關聯記錄。

        Args:
            actress_id: 女優 ID

        Returns:
            成功則返回 True，若女優不存在則返回 False

        Raises:
            LockError: 若無法獲得寫鎖定
            CorruptedDataError: 若刪除失敗
        """
        try:
            # 獲取寫鎖定
            self._acquire_write_lock()

            try:
                # 重新載入最新資料
                self._load_data_internal()

                actresses = self.data.get("actresses", {})

                # 檢查女優是否存在
                if actress_id not in actresses:
                    logger.warning(f"⚠️ 女優不存在: {actress_id}")
                    return False

                # 刪除女優
                del actresses[actress_id]

                # 刪除相關的影片-女優關聯
                links = self.data.get("links", [])
                self.data["links"] = [
                    link for link in links if link.get("actress_id") != actress_id
                ]

                # 驗證完整性
                self._validate_referential_integrity(self.data)

                # 更新統計快取（快取失效策略）
                self._cache_statistics()

                # 保存
                self._save_all_data(self.data)

                logger.info(f"✅ 女優已刪除: {actress_id}")
                return True

            finally:
                self._release_locks()

        except (DataIntegrityError, LockError) as e:
            logger.error(f"❌ 刪除女優失敗: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 未預期的錯誤: {e}")
            raise CorruptedDataError(f"刪除女優失敗: {e}") from e

    # ========================================================================
    # 輔助方法
    # ========================================================================

    # ========================================================================
    # 統計查詢快取機制 (T025)
    # ========================================================================

    def _compute_statistics(self) -> dict[str, Any]:
        """
        計算統計資訊 (T025)

        計算所有統計指標並返回統計字典。

        Returns:
            統計字典，包含:
            - actress_statistics: 女優統計清單
            - studio_statistics: 片商統計清單
            - enhanced_actress_studio_statistics: 增強交叉統計清單
            - total_videos: 總影片數
            - total_actresses: 總女優數
            - total_studios: 總片商數
            - computed_at: 計算時間
        """
        try:
            # 計算各種統計
            actress_stats = self._compute_actress_statistics_internal()
            studio_stats = self._compute_studio_statistics_internal()
            enhanced_stats = self._compute_enhanced_actress_studio_statistics_internal()

            # 基本統計
            total_videos = len(self.data.get("videos", {}))
            total_actresses = len(self.data.get("actresses", {}))

            # 計算片商數 (去重)
            studios = set()
            for video in self.data.get("videos", {}).values():
                studio = video.get("studio")
                if studio and studio != "UNKNOWN":
                    studios.add(studio)
            total_studios = len(studios)

            computed_at = datetime.now(UTC).strftime(ISO_DATETIME_FORMAT)

            statistics = {
                "actress_statistics": actress_stats,
                "studio_statistics": studio_stats,
                "enhanced_actress_studio_statistics": enhanced_stats,
                "total_videos": total_videos,
                "total_actresses": total_actresses,
                "total_studios": total_studios,
                "computed_at": computed_at,
            }

            logger.info(
                f"✅ 統計計算完成: {total_videos} 部影片, {total_actresses} 位女優, {total_studios} 間片商"
            )
            return statistics

        except Exception as e:
            logger.error(f"❌ 統計計算失敗: {e}")
            raise

    def _cache_statistics(self) -> None:
        """
        更新統計快取 (T025)

        計算統計並更新到 self.data['statistics']。
        在新增/修改影片時自動呼叫此方法。

        Raises:
            LockError: 若無法獲得寫鎖定
        """
        try:
            # 計算統計
            statistics = self._compute_statistics()

            # 更新快取
            self.data["statistics"] = statistics

            logger.info("✅ 統計快取已更新")

        except Exception as e:
            logger.error(f"❌ 統計快取更新失敗: {e}")
            raise

    def get_cached_statistics(self, force_refresh: bool = False) -> dict[str, Any]:
        """
        獲取快取的統計資訊 (T025)

        從快取中取得統計資訊，若快取不存在或需要重新整理則重新計算。

        Args:
            force_refresh: 是否強制重新計算統計 (預設: False)

        Returns:
            統計字典，包含所有統計資訊

        Raises:
            LockError: 若無法獲得鎖定
        """
        try:
            # 獲取讀鎖定
            self._acquire_read_lock()

            try:
                statistics = self.data.get("statistics", {})

                # 檢查快取是否存在且有效
                has_valid_cache = (
                    statistics
                    and "computed_at" in statistics
                    and "total_videos" in statistics
                )

                if not has_valid_cache or force_refresh:
                    # 釋放讀鎖，獲取寫鎖以更新快取
                    self._release_locks()
                    self._acquire_write_lock()

                    try:
                        # 重新載入最新資料
                        self._load_data_internal()

                        # 重新計算統計
                        self._cache_statistics()

                        # 保存到磁碟
                        self._save_all_data(self.data)

                        statistics = self.data.get("statistics", {})

                    finally:
                        # 寫鎖會在外層 with 區塊結束時自動釋放
                        logger.debug("統計快取操作完成")

                logger.info("✅ 取得統計快取成功")
                return statistics

            finally:
                self._release_locks()

        except LockError as e:
            logger.error(f"❌ 無法獲取鎖定: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 取得統計快取失敗: {e}")
            raise

    def refresh_statistics_cache(self) -> bool:
        """
        手動重新整理統計快取 (T025)

        強制重新計算所有統計並更新快取。

        Returns:
            成功則返回 True

        Raises:
            LockError: 若無法獲得寫鎖定
        """
        try:
            self.get_cached_statistics(force_refresh=True)
            logger.info("✅ 統計快取手動重新整理成功")
            return True

        except Exception as e:
            logger.error(f"❌ 統計快取重新整理失敗: {e}")
            raise

    # ========================================================================
    # 統計查詢方法 (T022, T023, T024)
    # ========================================================================

    def get_actress_statistics(self) -> list[dict[str, Any]]:
        """
        取得女優統計資訊，包含片商分佈 (T022)

        遍歷所有女優，計算每位女優的出演部數、片商清單等。
        結果格式與 SQLite 版本相同。

        Returns:
            女優統計清單，每項包含:
            - actress_name: 女優名稱
            - video_count: 出演部數
            - studios: 片商清單 (去重)
            - studio_codes: 片商代碼清單 (去重)

        Raises:
            LockError: 若無法獲得讀鎖定
        """
        try:
            # 獲取讀鎖定
            self._acquire_read_lock()

            try:
                return self._compute_actress_statistics_internal()

            finally:
                self._release_locks()

        except LockError as e:
            logger.error(f"❌ 無法獲取讀鎖定: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 女優統計查詢失敗: {e}")
            raise

    def _compute_actress_statistics_internal(self) -> list[dict[str, Any]]:
        """
        內部女優統計計算方法（不獲取鎖）

        在已獲取鎖的情況下計算女優統計。

        Returns:
            女優統計清單
        """
        actresses = self.data.get("actresses", {})
        videos = self.data.get("videos", {})
        links = self.data.get("links", [])

        # 建立 actress_id → codes 映射
        actress_video_map: dict[str, list[str]] = {}
        for link in links:
            actress_id = link.get("actress_id")
            video_code = link.get("video_code")
            if actress_id and video_code:
                if actress_id not in actress_video_map:
                    actress_video_map[actress_id] = []
                actress_video_map[actress_id].append(video_code)

        # 統計每位女優的資訊
        statistics = []
        for actress_id, actress in actresses.items():
            actress_name = actress.get("name", "")

            # 取得該女優的所有影片
            video_codes = actress_video_map.get(actress_id, [])
            video_count = len(video_codes)

            # 收集片商資訊
            studios = set()
            studio_codes = set()

            for code in video_codes:
                video = videos.get(code)
                if video:
                    studio = video.get("studio")
                    studio_code = video.get("studio_code")
                    if studio:
                        studios.add(studio)
                    if studio_code:
                        studio_codes.add(studio_code)

            statistics.append(
                {
                    "actress_name": actress_name,
                    "video_count": video_count,
                    "studios": sorted(studios),
                    "studio_codes": sorted(studio_codes),
                }
            )

        # 按出演部數降序排序
        statistics.sort(key=lambda x: x["video_count"], reverse=True)

        logger.debug(f"✅ 女優統計計算完成: {len(statistics)} 位女優")
        return statistics

    def get_studio_statistics(self) -> list[dict[str, Any]]:
        """
        取得片商統計資訊 (T023)

        遍歷所有影片按片商分組，計算每間片商的影片數、女優數等。
        結果格式與 SQLite 版本相同。

        Returns:
            片商統計清單，每項包含:
            - studio: 片商名稱
            - studio_code: 片商代碼
            - video_count: 影片數
            - actress_count: 女優數 (去重)

        Raises:
            LockError: 若無法獲得讀鎖定
        """
        try:
            # 獲取讀鎖定
            self._acquire_read_lock()

            try:
                return self._compute_studio_statistics_internal()

            finally:
                self._release_locks()

        except LockError as e:
            logger.error(f"❌ 無法獲取讀鎖定: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 片商統計查詢失敗: {e}")
            raise

    def _compute_studio_statistics_internal(self) -> list[dict[str, Any]]:
        """
        內部片商統計計算方法（不獲取鎖）

        在已獲取鎖的情況下計算片商統計。

        Returns:
            片商統計清單
        """
        videos = self.data.get("videos", {})
        links = self.data.get("links", [])

        # 建立片商統計映射 {(studio, studio_code): {...}}
        studio_stats: dict[tuple, dict[str, Any]] = {}

        # 建立 code → actress_ids 映射
        video_actress_map: dict[str, set] = {}
        for link in links:
            video_code = link.get("video_code")
            actress_id = link.get("actress_id")
            if video_code and actress_id:
                if video_code not in video_actress_map:
                    video_actress_map[video_code] = set()
                video_actress_map[video_code].add(actress_id)

        # 遍歷所有影片
        for code, video in videos.items():
            studio = video.get("studio")
            studio_code = video.get("studio_code", "")

            # 過濾掉無片商的影片
            if not studio:
                continue

            # 使用 (studio, studio_code) 作為鍵
            key = (studio, studio_code)

            if key not in studio_stats:
                studio_stats[key] = {
                    "studio": studio,
                    "studio_code": studio_code,
                    "video_count": 0,
                    "actress_ids": set(),
                }

            # 增加影片計數
            studio_stats[key]["video_count"] += 1

            # 收集女優 ID
            if code in video_actress_map:
                studio_stats[key]["actress_ids"].update(video_actress_map[code])

        # 轉換為結果格式
        statistics = []
        for _, stats in studio_stats.items():
            statistics.append(
                {
                    "studio": stats["studio"],
                    "studio_code": stats["studio_code"],
                    "video_count": stats["video_count"],
                    "actress_count": len(stats["actress_ids"]),
                }
            )

        # 按影片數降序排序
        statistics.sort(key=lambda x: x["video_count"], reverse=True)

        logger.debug(f"✅ 片商統計計算完成: {len(statistics)} 間片商")
        return statistics

    def get_enhanced_actress_studio_statistics(
        self, actress_name: str | None = None
    ) -> list[dict[str, Any]]:
        """
        取得增強版女優片商統計資訊（包含檔案關聯類型分析） (T024)

        遍歷關聯表，建立 (actress_id, studio) 組合計數。
        支援多維聚合，結果格式與 SQLite 版本相同。

        Args:
            actress_name: 篩選特定女優名稱（可選）

        Returns:
            交叉統計清單，每項包含:
            - actress_name: 女優名稱
            - studio: 片商名稱
            - studio_code: 片商代碼
            - association_type: 關聯類型 (role_type)
            - video_count: 該組合的影片數
            - video_codes: 影片代碼清單
            - first_appearance: 首次出現日期
            - latest_appearance: 最新出現日期

        Raises:
            LockError: 若無法獲得讀鎖定
        """
        try:
            # 獲取讀鎖定
            self._acquire_read_lock()

            try:
                return self._compute_enhanced_actress_studio_statistics_internal(
                    actress_name
                )

            finally:
                self._release_locks()

        except LockError as e:
            logger.error(f"❌ 無法獲取讀鎖定: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 增強女優片商統計查詢失敗: {e}")
            raise

    def _compute_enhanced_actress_studio_statistics_internal(
        self, actress_name: str | None = None
    ) -> list[dict[str, Any]]:
        """
        內部增強女優片商統計計算方法（不獲取鎖）

        在已獲取鎖的情況下計算增強交叉統計。

        Args:
            actress_name: 篩選特定女優名稱（可選）

        Returns:
            增強交叉統計清單
        """
        actresses = self.data.get("actresses", {})
        videos = self.data.get("videos", {})
        links = self.data.get("links", [])

        # 建立 actress_id → actress_name 映射
        actress_id_to_name = {
            actress_id: actress.get("name", "")
            for actress_id, actress in actresses.items()
        }

        # 建立統計映射 {(actress_id, studio, studio_code, role_type): {...}}
        stats_map: dict[tuple, dict[str, Any]] = {}

        # 遍歷所有關聯
        for link in links:
            actress_id = link.get("actress_id")
            video_code = link.get("video_code")
            role_type = link.get("role_type", "primary")  # 預設為 primary
            timestamp = link.get("timestamp", "")

            if not actress_id or not video_code:
                continue

            # 取得女優名稱
            name = actress_id_to_name.get(actress_id, "")

            # 如果指定了 actress_name，則過濾
            if actress_name and name != actress_name:
                continue

            # 取得影片資訊
            video = videos.get(video_code)
            if not video:
                continue

            studio = video.get("studio", "")
            studio_code = video.get("studio_code", "")
            video.get("code", "")

            # 過濾掉無片商或 UNKNOWN 的影片
            if not studio or studio == "UNKNOWN":
                continue

            # 使用 (actress_id, studio, studio_code, role_type) 作為鍵
            key = (actress_id, studio, studio_code, role_type)

            if key not in stats_map:
                stats_map[key] = {
                    "actress_name": name,
                    "studio": studio,
                    "studio_code": studio_code,
                    "association_type": role_type,
                    "video_count": 0,
                    "video_codes": [],
                    "first_appearance": timestamp,
                    "latest_appearance": timestamp,
                }

            # 更新統計
            stats = stats_map[key]
            stats["video_count"] += 1
            stats["video_codes"].append(video_code)

            # 更新日期範圍
            if timestamp:
                if (
                    not stats["first_appearance"]
                    or timestamp < stats["first_appearance"]
                ):
                    stats["first_appearance"] = timestamp
                if (
                    not stats["latest_appearance"]
                    or timestamp > stats["latest_appearance"]
                ):
                    stats["latest_appearance"] = timestamp

        # 轉換為結果格式
        statistics = list(stats_map.values())

        # 排序：如果指定女優則按影片數降序，否則按女優名稱+影片數
        if actress_name:
            statistics.sort(key=lambda x: x["video_count"], reverse=True)
        else:
            statistics.sort(key=lambda x: (x["actress_name"], -x["video_count"]))

        logger.debug(f"✅ 增強女優片商統計計算完成: {len(statistics)} 筆記錄")
        return statistics

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
        分析女優的主要片商

        根據女優的影片分布分析其主要片商,並提供分類建議。

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
        """
        try:
            self._acquire_read_lock()

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
                    }

                # 找出作品數最多的片商
                best_studio = max(
                    studio_stats.items(), key=lambda x: x[1]["total_count"]
                )[0]
                best_stats = studio_stats[best_studio]

                # 計算信心度
                confidence = (
                    (best_stats["total_count"] / total_videos) * 100
                    if total_videos > 0
                    else 0
                )

                # 決定推薦分類
                recommendation = "solo_artist"
                has_major_studio_work = False
                major_studio_work_count = 0
                minor_studio_work_count = 0
                best_major_studio = None
                best_major_confidence = 0

                if major_studios:
                    for studio, stats in studio_stats.items():
                        if studio in major_studios:
                            has_major_studio_work = True
                            major_studio_work_count += stats["total_count"]
                            if stats["total_count"] > best_major_confidence:
                                best_major_confidence = stats["total_count"]
                                best_major_studio = studio
                        else:
                            minor_studio_work_count += stats["total_count"]

                # 分類邏輯
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
                        confidence = max(major_studio_confidence, 60.0)

                return {
                    "actress_name": actress_name,
                    "primary_studio": best_studio or "UNKNOWN",
                    "confidence": round(confidence, 1),
                    "total_videos": total_videos,
                    "studio_distribution": studio_stats,
                    "recommendation": recommendation,
                }

            finally:
                self._release_locks()

        except LockError as e:
            logger.error(f"❌ 無法獲取讀鎖定: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 分析女優主要片商失敗: {e}")
            raise
