"""
配置管理模組
包含系統配置和使用者偏好設定管理
"""

import configparser
import logging
from pathlib import Path
from typing import Any

try:
    from utils.json_utils import dump as json_dump
    from utils.json_utils import load as json_load
except ImportError:  # pragma: no cover
    from src.utils.json_utils import dump as json_dump
    from src.utils.json_utils import load as json_load

logger = logging.getLogger(__name__)


def normalize_path(path_str: str) -> str:
    """
    標準化路徑格式，統一使用 POSIX 風格 (/)

    Args:
        path_str: 原始路徑字串

    Returns:
        標準化後的路徑字串
    """
    if not path_str:
        return path_str
    # 使用 pathlib 處理，然後轉換為 POSIX 風格
    return Path(path_str).as_posix()


class ConfigManager:
    """設定檔管理器 - 增強版，支援路徑標準化和配置驗證"""

    # 配置驗證規則
    VALIDATION_RULES = {
        "search": {
            "batch_size": {"type": int, "min": 1, "max": 100, "default": 10},
            "thread_count": {"type": int, "min": 1, "max": 20, "default": 5},
            "batch_delay": {"type": float, "min": 0.1, "max": 30.0, "default": 2.0},
            "request_timeout": {"type": int, "min": 5, "max": 120, "default": 20},
            "avwiki_max_concurrent": {"type": int, "min": 1, "max": 50, "default": 15},
        },
        "cache": {
            "ttl_days": {"type": int, "min": 1, "max": 365, "default": 7},
            "max_size_mb": {"type": int, "min": 10, "max": 5000, "default": 500},
        },
    }

    def __init__(self, config_file: str = "config.ini"):
        self.config_file = Path(config_file)
        self.config = configparser.ConfigParser()
        self.load_config()
        self._normalize_path_settings()
        self._validate_config()

    def load_config(self):
        if self.config_file.exists():
            self.config.read(self.config_file, encoding="utf-8")
        db_path = (
            Path.home() / "Documents" / "ActressClassifier" / "actress_database.db"
        )
        defaults = {
            "database": {
                "database_path": str(db_path),
                "json_data_dir": "data/json_db",
            },
            "paths": {"default_input_dir": "."},
            "search": {
                "batch_size": "10",
                "thread_count": "5",
                "batch_delay": "2.0",
                "request_timeout": "20",
                "avwiki_concurrent_enabled": "true",
                "avwiki_max_concurrent": "15",
            },
            "classification": {"mode": "interactive", "auto_apply_preferences": "true"},
            "cache": {
                "ttl_days": "7",
                "max_size_mb": "500",
                "auto_cleanup_on_exit": "true",
            },
            "go_integration": {
                "enabled": "true",
                "exe_path": "",
                "scan_workers": "10",
                "move_conflict_strategy": "skip",
                "enable_operation_log": "true",
                "log_dir": "logs",
            },
        }
        needs_saving = not self.config_file.exists()
        for section, options in defaults.items():
            if not self.config.has_section(section):
                self.config.add_section(section)
                needs_saving = True
            for option, value in options.items():
                if not self.config.has_option(section, option):
                    self.config.set(section, option, value)
                    needs_saving = True
        if needs_saving:
            self.save_config()

    def _normalize_path_settings(self):
        """標準化所有路徑設定，統一使用 POSIX 風格"""
        path_settings = [
            ("database", "database_path"),
            ("database", "json_data_dir"),
            ("paths", "default_input_dir"),
        ]

        needs_saving = False
        for section, key in path_settings:
            if self.config.has_option(section, key):
                original = self.config.get(section, key)
                normalized = normalize_path(original)
                if original != normalized:
                    self.config.set(section, key, normalized)
                    logger.debug(
                        f"路徑標準化: [{section}]{key} = {original} -> {normalized}"
                    )
                    needs_saving = True

        if needs_saving:
            self.save_config()

    def _validate_config(self):
        """驗證配置項目的有效性"""
        needs_saving = False

        for section, rules in self.VALIDATION_RULES.items():
            if not self.config.has_section(section):
                continue

            for key, rule in rules.items():
                if not self.config.has_option(section, key):
                    continue

                try:
                    value_str = self.config.get(section, key)
                    value = rule["type"](value_str)

                    # 檢查範圍
                    if "min" in rule and value < rule["min"]:
                        logger.warning(
                            f"配置 [{section}]{key}={value} 低於最小值 {rule['min']}，已重設為預設值 {rule['default']}"
                        )
                        self.config.set(section, key, str(rule["default"]))
                        needs_saving = True
                    elif "max" in rule and value > rule["max"]:
                        logger.warning(
                            f"配置 [{section}]{key}={value} 超過最大值 {rule['max']}，已重設為預設值 {rule['default']}"
                        )
                        self.config.set(section, key, str(rule["default"]))
                        needs_saving = True

                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"配置 [{section}]{key} 格式錯誤: {e}，已重設為預設值 {rule['default']}"
                    )
                    self.config.set(section, key, str(rule["default"]))
                    needs_saving = True

        if needs_saving:
            self.save_config()

    def save_config(self):
        try:
            with self.config_file.open("w", encoding="utf-8") as f:
                self.config.write(f)
        except OSError as e:
            logger.error(f"儲存設定檔失敗: {e}")

    def get(self, section: str, key: str, fallback=None):
        return self.config.get(section, key, fallback=fallback)

    def getint(self, section: str, key: str, fallback=0):
        return self.config.getint(section, key, fallback=fallback)

    def getfloat(self, section: str, key: str, fallback=0.0):
        return self.config.getfloat(section, key, fallback=fallback)

    def getboolean(self, section: str, key: str, fallback=False):
        return self.config.getboolean(section, key, fallback=fallback)

    def getpath(self, section: str, key: str, fallback=None) -> Path | None:
        """取得路徑設定，自動轉換為 Path 物件"""
        value = self.config.get(section, key, fallback=fallback)
        if value:
            return Path(value)
        return None

    def set(self, section: str, key: str, value: Any):
        """設定配置值"""
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, str(value))
        self.save_config()

    def get_all_settings(self) -> dict[str, dict[str, str]]:
        """取得所有設定（用於除錯）"""
        result = {}
        for section in self.config.sections():
            result[section] = dict(self.config.items(section))
        return result


class PreferenceManager:
    """使用者偏好管理器 - 包含片商分類設定"""

    def __init__(self, preference_file: str = "user_preferences.json"):
        self.preference_file = Path(preference_file)
        self.preferences = self.load_preferences()

    def load_preferences(self) -> dict:
        """載入使用者偏好設定 - 包含片商分類設定"""
        try:
            if self.preference_file.exists():
                with self.preference_file.open("r", encoding="utf-8") as f:
                    prefs = json_load(f)

                # 確保新設定項目存在（向後相容）
                if "solo_folder_name" not in prefs:
                    prefs["solo_folder_name"] = "單體企劃女優"
                if "studio_classification" not in prefs:
                    prefs["studio_classification"] = {
                        "confidence_threshold": 60.0,
                        "auto_create_studio_folders": True,
                        "backup_before_move": True,
                    }

                return prefs

        except Exception as e:
            logger.warning(f"載入偏好設定失敗: {e}")

        # 預設設定
        return {
            "favorite_actresses": [],
            "priority_actresses": [],
            "collaboration_preferences": {},
            "classification_strategy": "interactive",
            "auto_tag_filenames": True,
            "skip_single_actress": False,
            # 片商分類設定
            "solo_folder_name": "單體企劃女優",
            "studio_classification": {
                "confidence_threshold": 60.0,
                "auto_create_studio_folders": True,
                "backup_before_move": True,
            },
        }

    def save_preferences(self):
        """儲存偏好設定"""
        try:
            with self.preference_file.open("w", encoding="utf-8") as f:
                json_dump(self.preferences, f, ensure_ascii=False, indent=2)
            logger.info("偏好設定已儲存")
        except Exception as e:
            logger.error(f"儲存偏好設定失敗: {e}")

    def get_preferred_actress(self, actresses: list[str]) -> str | None:
        """根據偏好選擇分類女優"""
        if not actresses:
            return None

        # 檢查是否有記住的共演偏好
        actresses_key = "+".join(sorted(actresses))
        if actresses_key in self.preferences["collaboration_preferences"]:
            return self.preferences["collaboration_preferences"][actresses_key]

        # 優先級1：最愛女優
        for actress in actresses:
            if actress in self.preferences["favorite_actresses"]:
                return actress

        # 優先級2：優先女優
        for actress in actresses:
            if actress in self.preferences["priority_actresses"]:
                return actress

        return None

    def save_collaboration_preference(self, actresses: list[str], chosen: str):
        """儲存共演組合的偏好設定"""
        actresses_key = "+".join(sorted(actresses))
        self.preferences["collaboration_preferences"][actresses_key] = chosen
        self.save_preferences()
        logger.info(f"已記住組合偏好: {actresses_key} -> {chosen}")

    # 片商分類相關方法
    def get_solo_folder_name(self) -> str:
        """取得單體企劃女優資料夾名稱"""
        return self.preferences.get("solo_folder_name", "單體企劃女優")

    def set_solo_folder_name(self, folder_name: str):
        """設定單體企劃女優資料夾名稱"""
        self.preferences["solo_folder_name"] = folder_name
        self.save_preferences()

    def get_confidence_threshold(self) -> float:
        """取得片商信心度門檻"""
        return self.preferences.get("studio_classification", {}).get(
            "confidence_threshold", 60.0
        )

    def set_confidence_threshold(self, threshold: float):
        """設定片商信心度門檻"""
        if "studio_classification" not in self.preferences:
            self.preferences["studio_classification"] = {}
        self.preferences["studio_classification"]["confidence_threshold"] = threshold
        self.save_preferences()

    def should_backup_before_move(self) -> bool:
        """是否在移動前備份"""
        return self.preferences.get("studio_classification", {}).get(
            "backup_before_move", True
        )

    def should_auto_create_studio_folders(self) -> bool:
        """是否自動建立片商資料夾"""
        return self.preferences.get("studio_classification", {}).get(
            "auto_create_studio_folders", True
        )
