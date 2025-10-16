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
        
        logger.debug("✅ 參照完整性驗證通過")
    
    def _validate_consistency(self) -> bool:
        """
        驗證統計快取一致性
        
        Returns:
            bool: 一致則 True
        """
        try:
            # 這個方法將在 Phase 5 實現
            # 目前先返回 True
            logger.debug("統計快取一致性檢查 (待實現)")
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
        """建立備份 (待實現)"""
        pass
    
    def restore_from_backup(self, backup_path: str) -> bool:
        """還原備份 (待實現)"""
        pass
    
    # ========================================================================
    # 並行鎖定 (已在 __init__ 實現)
    # ========================================================================
    
    def _acquire_read_lock(self, timeout: int = READ_LOCK_TIMEOUT) -> None:
        """取得讀鎖定"""
        try:
            self.read_lock.acquire(timeout=timeout)
        except Exception as e:
            raise LockError(f"無法獲得讀鎖定: {e}")
    
    def _acquire_write_lock(self, timeout: int = WRITE_LOCK_TIMEOUT) -> None:
        """取得寫鎖定"""
        try:
            self.write_lock.acquire(timeout=timeout)
        except Exception as e:
            raise LockError(f"無法獲得寫鎖定: {e}")
    
    def _release_locks(self) -> None:
        """釋放所有鎖定"""
        try:
            self.read_lock.release()
        except:
            pass
        try:
            self.write_lock.release()
        except:
            pass
    
    def __enter__(self):
        """上下文管理器進入"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self._release_locks()
        return False
