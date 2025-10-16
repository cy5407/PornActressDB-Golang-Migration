# -*- coding: utf-8 -*-
"""
JSON 資料庫管理器 (JSONDBManager)

此模組提供 JSON 檔案型資料庫的核心管理功能，包括：
- 檔案鎖定機制（讀寫並行控制）
- 資料的載入和保存
- 基本 CRUD 操作
- 資料驗證和完整性檢查
"""

import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from filelock import FileLock

from src.models.json_types import (
    JSONDatabaseDict,
    VideoDict,
    ActressDict,
    VideoActressLinkDict,
    ValidationError,
    LockError,
    DataIntegrityError,
    CorruptedDataError,
    JSONDatabaseError,
    BackupError,
    SCHEMA_VERSION,
    JSON_DB_FILE,
    BACKUP_DIR,
    READ_LOCK_TIMEOUT,
    WRITE_LOCK_TIMEOUT,
    ISO_DATETIME_FORMAT,
    get_empty_json_database,
    get_empty_video,
    get_empty_actress,
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
            raise JSONDatabaseError(f"初始化失敗: {e}")
    
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
                if not self.data_file.exists():
                    self._ensure_data_file_exists()
                    return
                
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                
                # 試圖解析 JSON
                try:
                    loaded_data = json.loads(file_content)
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON 解析失敗: {e}")
                    raise CorruptedDataError(f"JSON 格式錯誤: {e}")
                
                # 驗證資料結構
                self._validate_json_format(loaded_data)
                
                # 驗證完整性
                self._validate_referential_integrity(loaded_data)
                
                self.data = loaded_data
                logger.info(f"✅ 資料載入成功: {len(loaded_data.get('videos', {}))} 部影片")
                
        except LockError as e:
            logger.error(f"❌ 讀鎖定失敗: {e}")
            raise
        except CorruptedDataError:
            raise
        except Exception as e:
            logger.error(f"❌ 資料載入失敗: {e}")
            raise CorruptedDataError(f"載入失敗: {e}")
    
    def _save_all_data(self, data: JSONDatabaseDict) -> None:
        """
        原子寫入資料到磁碟
        
        包含資料雜湊計算和備份。
        
        Args:
            data: 要儲存的資料字典
            
        Raises:
            LockError: 若無法獲得寫鎖定
            DataIntegrityError: 若寫入驗證失敗
        """
        try:
            # 驗證資料
            self._validate_json_format(data)
            self._validate_referential_integrity(data)
            
            # 計算資料雜湊
            data_copy = data.copy()
            data_copy['data_hash'] = ''  # 暫時清空以計算雜湊
            data_str = json.dumps(data_copy, ensure_ascii=False, sort_keys=True)
            data_hash = hashlib.sha256(data_str.encode('utf-8')).hexdigest()
            data['data_hash'] = data_hash
            
            # 更新時間戳
            data['updated_at'] = datetime.now(timezone.utc).strftime(ISO_DATETIME_FORMAT)
            
            with self.write_lock:
                # 原子寫入
                temp_file = self.data_file.parent / f"{self.data_file.name}.tmp"
                
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                # 替換原檔案
                temp_file.replace(self.data_file)
                
                logger.info(f"✅ 資料儲存成功: {self.data_file}")
                
        except LockError as e:
            logger.error(f"❌ 寫鎖定失敗: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 資料儲存失敗: {e}")
            raise DataIntegrityError(f"儲存失敗: {e}")
    
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
        
        required_keys = {'schema_version', 'videos', 'actresses', 'links', 'statistics'}
        missing_keys = required_keys - set(data.keys())
        
        if missing_keys:
            raise ValidationError(f"遺失必需鍵: {missing_keys}")
        
        # 驗證 schema 版本
        if data.get('schema_version') != SCHEMA_VERSION:
            raise ValidationError(
                f"Schema 版本不符: 預期 {SCHEMA_VERSION}, 實際 {data.get('schema_version')}"
            )
        
        logger.debug("✅ JSON 格式驗證通過")
    
    def _validate_referential_integrity(self, data: Dict[str, Any]) -> None:
        """
        驗證參照完整性（外鍵約束）
        
        Args:
            data: 要驗證的資料
            
        Raises:
            DataIntegrityError: 若完整性檢查失敗
        """
        videos = data.get('videos', {})
        actresses = data.get('actresses', {})
        links = data.get('links', [])
        
        # 檢查連結中的 video_id 和 actress_id 是否存在
        for link in links:
            video_id = link.get('video_id')
            actress_id = link.get('actress_id')
            
            if video_id and video_id not in videos:
                raise DataIntegrityError(
                    f"連結中的 video_id '{video_id}' 不存在"
                )
            
            if actress_id and actress_id not in actresses:
                raise DataIntegrityError(
                    f"連結中的 actress_id '{actress_id}' 不存在"
                )
        
        # 檢查影片中的 actresses 清單是否有效
        for video_id, video in videos.items():
            actresses_list = video.get('actresses', [])
            for actress_id in actresses_list:
                if actress_id not in actresses:
                    raise DataIntegrityError(
                        f"影片 '{video_id}' 中的女優 ID '{actress_id}' 不存在"
                    )
        
        logger.debug("✅ 參照完整性驗證通過")
    
    def _validate_structure(self, data: Dict[str, Any]) -> None:
        """
        驗證資料結構和欄位類型（第二層驗證）
        
        Args:
            data: 要驗證的資料
            
        Raises:
            ValidationError: 若結構或欄位類型不正確
        """
        # 驗證 videos 結構
        videos = data.get('videos', {})
        if not isinstance(videos, dict):
            raise ValidationError("'videos' 必須是字典")
        
        for video_id, video in videos.items():
            if not isinstance(video, dict):
                raise ValidationError(f"影片 '{video_id}' 必須是字典")
            
            # 必需欄位
            required_video_fields = {'id', 'title', 'studio', 'release_date'}
            missing = required_video_fields - set(video.keys())
            if missing:
                raise ValidationError(f"影片 '{video_id}' 缺少欄位: {missing}")
            
            # 欄位類型檢查
            if not isinstance(video.get('id'), str):
                raise ValidationError(f"影片 '{video_id}' 的 'id' 必須是字串")
            if not isinstance(video.get('actresses'), list):
                raise ValidationError(f"影片 '{video_id}' 的 'actresses' 必須是清單")
        
        # 驗證 actresses 結構
        actresses = data.get('actresses', {})
        if not isinstance(actresses, dict):
            raise ValidationError("'actresses' 必須是字典")
        
        for actress_id, actress in actresses.items():
            if not isinstance(actress, dict):
                raise ValidationError(f"女優 '{actress_id}' 必須是字典")
            
            required_actress_fields = {'id', 'name'}
            missing = required_actress_fields - set(actress.keys())
            if missing:
                raise ValidationError(f"女優 '{actress_id}' 缺少欄位: {missing}")
        
        # 驗證 links 結構
        links = data.get('links', [])
        if not isinstance(links, list):
            raise ValidationError("'links' 必須是清單")
        
        for idx, link in enumerate(links):
            if not isinstance(link, dict):
                raise ValidationError(f"連結 {idx} 必須是字典")
            
            required_link_fields = {'video_id', 'actress_id'}
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
            actresses = data.get('actresses', {})
            links = data.get('links', [])
            
            # 計算實際的女優出演部數
            actual_actress_counts = {}
            for link in links:
                actress_id = link.get('actress_id')
                if actress_id:
                    actual_actress_counts[actress_id] = actual_actress_counts.get(actress_id, 0) + 1
            
            # 驗證 actresses 的 video_count 是否一致
            for actress_id, actress in actresses.items():
                expected_count = actual_actress_counts.get(actress_id, 0)
                actual_count = actress.get('video_count', 0)
                
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
    
    def validate_data(self) -> Dict[str, Any]:
        """
        執行全面的資料驗證
        
        Returns:
            驗證結果字典，包含:
            - 'valid' (bool): 是否有效
            - 'errors' (List[str]): 錯誤訊息清單
        """
        result = {
            'valid': True,
            'errors': [],
        }
        
        try:
            self._validate_json_format(self.data)
        except ValidationError as e:
            result['valid'] = False
            result['errors'].append(f"格式驗證失敗: {e}")
        
        try:
            self._validate_referential_integrity(self.data)
        except DataIntegrityError as e:
            result['valid'] = False
            result['errors'].append(f"完整性驗證失敗: {e}")
        
        if not self._validate_consistency():
            result['valid'] = False
            result['errors'].append("一致性驗證失敗")
        
        return result
    
    # ========================================================================
    # 基本 CRUD 方法 (將在 T010 實現)
    # ========================================================================
    
    def add_or_update_video(self, video_info: VideoDict) -> str:
        """新增或更新影片 (待實現)"""
        pass
    
    def get_video_info(self, video_id: str) -> Optional[VideoDict]:
        """查詢影片 (待實現)"""
        pass
    
    def get_all_videos(self, filter_dict: Optional[Dict] = None) -> List[VideoDict]:
        """取得影片清單 (待實現)"""
        pass
    
    def delete_video(self, video_id: str) -> bool:
        """刪除影片 (待實現)"""
        pass
    
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
            from datetime import datetime, timezone
            
            timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S')
            backup_filename = f"backup_{timestamp}.json"
            backup_path = self.backup_dir / backup_filename
            
            # 複製資料
            with open(self.data_file, 'r', encoding='utf-8') as src:
                content = src.read()
            
            with open(backup_path, 'w', encoding='utf-8') as dst:
                dst.write(content)
            
            logger.info(f"✅ 備份建立成功: {backup_path}")
            return str(backup_path)
            
        except Exception as e:
            logger.error(f"❌ 備份失敗: {e}")
            raise BackupError(f"備份失敗: {e}")
    
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
            with open(backup_file, 'r', encoding='utf-8') as f:
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
            raise BackupError(f"備份檔案損壞: {e}")
        except Exception as e:
            logger.error(f"❌ 還原失敗: {e}")
            raise BackupError(f"還原失敗: {e}")
    
    def get_backup_list(self) -> List[str]:
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
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            
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
            file_date = datetime.strptime(date_part, "%Y-%m-%d").replace(tzinfo=timezone.utc)
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
            raise LockError(f"無法獲得讀鎖定: {e}")
    
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
            raise LockError(f"無法獲得寫鎖定: {e}")
    
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
