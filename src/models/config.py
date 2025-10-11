# -*- coding: utf-8 -*-
"""
配置管理模組
包含系統配置和使用者偏好設定管理
"""
import json
import logging
import configparser
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ConfigManager:
    """設定檔管理器"""
    def __init__(self, config_file: str = "config.ini"):
        self.config_file = Path(config_file)
        self.config = configparser.ConfigParser()
        self.load_config()

    def load_config(self):
        if self.config_file.exists():
            self.config.read(self.config_file, encoding='utf-8')
        db_path = Path.home() / "Documents" / "ActressClassifier" / "actress_database.db"
        defaults = {
            'database': {'database_path': str(db_path)},
            'paths': {'default_input_dir': '.'},
            'search': {'batch_size': '10', 'thread_count': '5', 'batch_delay': '2.0', 'request_timeout': '20'},
            'classification': {'mode': 'interactive', 'auto_apply_preferences': 'true'}
        }
        needs_saving = not self.config_file.exists()
        for section, options in defaults.items():
            if not self.config.has_section(section):
                self.config.add_section(section); needs_saving = True
            for option, value in options.items():
                if not self.config.has_option(section, option):
                    self.config.set(section, option, value); needs_saving = True
        if needs_saving: self.save_config()

    def save_config(self):
        try:
            with self.config_file.open('w', encoding='utf-8') as f: self.config.write(f)
        except IOError as e: logger.error(f"儲存設定檔失敗: {e}")

    def get(self, section: str, key: str, fallback=None): return self.config.get(section, key, fallback=fallback)
    def getint(self, section: str, key: str, fallback=0): return self.config.getint(section, key, fallback=fallback)
    def getfloat(self, section: str, key: str, fallback=0.0): return self.config.getfloat(section, key, fallback=fallback)
    def getboolean(self, section: str, key: str, fallback=False): return self.config.getboolean(section, key, fallback=fallback)


class PreferenceManager:
    """使用者偏好管理器 - 包含片商分類設定"""
    def __init__(self, preference_file: str = "user_preferences.json"):
        self.preference_file = Path(preference_file)
        self.preferences = self.load_preferences()

    def load_preferences(self) -> Dict:
        """載入使用者偏好設定 - 包含片商分類設定"""
        try:
            if self.preference_file.exists():
                with self.preference_file.open('r', encoding='utf-8') as f:
                    prefs = json.load(f)
                    
                # 確保新設定項目存在（向後相容）
                if 'solo_folder_name' not in prefs:
                    prefs['solo_folder_name'] = '單體企劃女優'
                if 'studio_classification' not in prefs:
                    prefs['studio_classification'] = {
                        'confidence_threshold': 60.0,
                        'auto_create_studio_folders': True,
                        'backup_before_move': True
                    }
                
                return prefs
                
        except Exception as e:
            logger.warning(f"載入偏好設定失敗: {e}")
        
        # 預設設定
        return {
            'favorite_actresses': [],
            'priority_actresses': [],
            'collaboration_preferences': {},
            'classification_strategy': 'interactive',
            'auto_tag_filenames': True,
            'skip_single_actress': False,
            
            # 片商分類設定
            'solo_folder_name': '單體企劃女優',
            'studio_classification': {
                'confidence_threshold': 60.0,
                'auto_create_studio_folders': True,
                'backup_before_move': True
            }
        }

    def save_preferences(self):
        """儲存偏好設定"""
        try:
            with self.preference_file.open('w', encoding='utf-8') as f:
                json.dump(self.preferences, f, ensure_ascii=False, indent=2)
            logger.info("偏好設定已儲存")
        except Exception as e:
            logger.error(f"儲存偏好設定失敗: {e}")

    def get_preferred_actress(self, actresses: List[str]) -> Optional[str]:
        """根據偏好選擇分類女優"""
        if not actresses:
            return None
        
        # 檢查是否有記住的共演偏好
        actresses_key = "+".join(sorted(actresses))
        if actresses_key in self.preferences['collaboration_preferences']:
            return self.preferences['collaboration_preferences'][actresses_key]
        
        # 優先級1：最愛女優
        for actress in actresses:
            if actress in self.preferences['favorite_actresses']:
                return actress
        
        # 優先級2：優先女優
        for actress in actresses:
            if actress in self.preferences['priority_actresses']:
                return actress
        
        return None

    def save_collaboration_preference(self, actresses: List[str], chosen: str):
        """儲存共演組合的偏好設定"""
        actresses_key = "+".join(sorted(actresses))
        self.preferences['collaboration_preferences'][actresses_key] = chosen
        self.save_preferences()
        logger.info(f"已記住組合偏好: {actresses_key} -> {chosen}")

    # 片商分類相關方法
    def get_solo_folder_name(self) -> str:
        """取得單體企劃女優資料夾名稱"""
        return self.preferences.get('solo_folder_name', '單體企劃女優')

    def set_solo_folder_name(self, folder_name: str):
        """設定單體企劃女優資料夾名稱"""
        self.preferences['solo_folder_name'] = folder_name
        self.save_preferences()

    def get_confidence_threshold(self) -> float:
        """取得片商信心度門檻"""
        return self.preferences.get('studio_classification', {}).get('confidence_threshold', 60.0)

    def set_confidence_threshold(self, threshold: float):
        """設定片商信心度門檻"""
        if 'studio_classification' not in self.preferences:
            self.preferences['studio_classification'] = {}
        self.preferences['studio_classification']['confidence_threshold'] = threshold
        self.save_preferences()

    def should_backup_before_move(self) -> bool:
        """是否在移動前備份"""
        return self.preferences.get('studio_classification', {}).get('backup_before_move', True)

    def should_auto_create_studio_folders(self) -> bool:
        """是否自動建立片商資料夾"""
        return self.preferences.get('studio_classification', {}).get('auto_create_studio_folders', True)
