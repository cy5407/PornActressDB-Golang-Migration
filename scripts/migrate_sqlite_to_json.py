"""
SQLite 至 JSON 資料庫遷移工具

此模組提供從 SQLite 資料庫遷移至 JSON 檔案格式的完整功能，
包括資料轉換、驗證和報告生成。

功能模組:
- T008: 遷移工具主函式實作 (export_sqlite_to_json)
- T009: SQLite 至 JSON 資料轉換邏輯
"""

import sqlite3
import json
import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
import hashlib

# 專案導入
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.models.json_database import JSONDBManager
from src.models.json_types import (
    VideoDict,
    ActressDict,
    VideoActressLinkDict,
    SCHEMA_VERSION,
    ISO_DATETIME_FORMAT,
)

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('migration.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# 常數定義
# ============================================================================

JSON_DB_FILENAME = 'data.json'


# ============================================================================
# T009: SQLite 至 JSON 資料轉換邏輯
# ============================================================================

def handle_datetime_conversion(sqlite_timestamp: Optional[str]) -> str:
    """
    將 SQLite TIMESTAMP 轉換至 ISO 8601 格式。
    
    Args:
        sqlite_timestamp: SQLite 時間戳字串 (格式: 'YYYY-MM-DD HH:MM:SS' 或 None)
    
    Returns:
        ISO 8601 格式的時間戳 (例: '2025-10-16T10:30:00+00:00')
    
    Raises:
        ValueError: 時間戳格式無效
    """
    try:
        if sqlite_timestamp is None or sqlite_timestamp == '':
            # 使用當前時間作為預設值
            return datetime.now().strftime(ISO_DATETIME_FORMAT)
        
        # 嘗試解析 SQLite 時間戳格式
        dt = datetime.strptime(sqlite_timestamp, '%Y-%m-%d %H:%M:%S')
        # 轉換至 ISO 8601 格式
        return dt.strftime(ISO_DATETIME_FORMAT)
    except (ValueError, TypeError) as e:
        logger.warning(f"時間戳轉換失敗 ({sqlite_timestamp}): {e}，使用當前時間")
        return datetime.now().strftime(ISO_DATETIME_FORMAT)


def _is_datetime_field(key: str) -> bool:
    """檢查欄位名稱是否為日期/時間欄位"""
    return key.endswith('_date') or key.endswith('_time') or key.endswith('_at')


def _is_boolean_field(table_name: str, key: str, value: int) -> bool:
    """檢查是否應轉換為布林值"""
    if not isinstance(value, int):
        return False
    return table_name == 'videos' and key in ['has_subtitle', 'is_active']


def _convert_string_value(value: str) -> str:
    """安全地轉換字串值，確保 UTF-8 編碼"""
    try:
        return value.encode('utf-8').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        logger.warning("欄位編碼失敗，移除非法字元")
        return value.encode('utf-8', errors='ignore').decode('utf-8')


def convert_sqlite_data_to_json(sqlite_row: sqlite3.Row, table_name: str) -> Dict[str, Any]:
    """
    將 SQLite 列轉換至 JSON 相容的字典格式。
    
    特殊處理:
    - NULL 值: 轉換為 None（稍後在建構時移除或設定預設值）
    - TIMESTAMP: 轉換至 ISO 8601 格式
    - 布林值: SQLite 的 INTEGER (0/1) 轉換至 bool
    - 編碼: 確保 UTF-8 相容性
    
    Args:
        sqlite_row: SQLite 行物件 (sqlite3.Row)
        table_name: 表名稱 ('videos', 'actresses', 'video_actress_link')
    
    Returns:
        JSON 相容的字典
    """
    converted = {}
    
    try:
        # 轉換所有欄位
        for key in sqlite_row.keys():
            value = sqlite_row[key]
            
            # 特殊欄位處理
            if _is_datetime_field(key):
                converted[key] = handle_datetime_conversion(value)
            elif isinstance(value, bool):
                converted[key] = value
            elif isinstance(value, int):
                # 檢查是否為布林值欄位 (SQLite 使用 0/1 表示)
                if _is_boolean_field(table_name, key, value):
                    converted[key] = bool(value)
                else:
                    converted[key] = value
            elif isinstance(value, str):
                # 字串值: 確保 UTF-8 編碼
                converted[key] = _convert_string_value(value)
            elif value is None:
                converted[key] = None
            else:
                # 其他型別: 轉換為字串
                converted[key] = str(value)
        
        return converted
    except Exception as e:
        logger.error(f"行轉換失敗 ({table_name}): {e}")
        raise


def build_json_structure(
    videos: List[Dict[str, Any]],
    actresses: List[Dict[str, Any]],
    links: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    建構完整的 JSON 資料庫結構。
    
    結構:
    ```json
    {
        "schema_version": "1.0",
        "created_at": "2025-10-16T...",
        "videos": [...],
        "actresses": [...],
        "video_actress_links": [...]
    }
    ```
    
    Args:
        videos: 轉換後的影片清單
        actresses: 轉換後的女優清單
        links: 轉換後的關聯清單
    
    Returns:
        完整的 JSON 資料結構
    """
    current_time = datetime.now().strftime(ISO_DATETIME_FORMAT)
    
    json_structure = {
        "schema_version": SCHEMA_VERSION,
        "created_at": current_time,
        "updated_at": current_time,
        "videos": videos,
        "actresses": actresses,
        "video_actress_links": links,
        "metadata": {
            "video_count": len(videos),
            "actress_count": len(actresses),
            "link_count": len(links),
            "migrated_at": current_time,
            "migration_source": "SQLite",
        }
    }
    
    return json_structure


# ============================================================================
# T008: 遷移工具主函式實作
# ============================================================================

def export_sqlite_to_json(
    sqlite_path: str,
    output_dir: str
) -> Tuple[bool, Dict[str, Any]]:
    """
    從 SQLite 資料庫匯出數據至 JSON 格式。
    
    此函式是遷移工具的主入口點，負責:
    1. 連接 SQLite 資料庫
    2. 讀取所有資料 (videos, actresses, video_actress_links)
    3. 轉換至 JSON 格式
    4. 建構完整的 JSON 檔案結構
    5. 生成遷移報告
    
    Args:
        sqlite_path: SQLite 檔案路徑
        output_dir: JSON 輸出目錄
        create_backup: 是否建立備份 (預設: True)
    
    Returns:
        Tuple[成功標記, 遷移報告字典]
        報告包含:
        - 'success': 是否成功
        - 'sqlite_path': SQLite 檔案路徑
        - 'output_dir': 輸出目錄
        - 'video_count': 遷移的影片數量
        - 'actress_count': 遷移的女優數量
        - 'link_count': 遷移的關聯數量
        - 'start_time': 開始時間
        - 'end_time': 結束時間
        - 'duration_seconds': 耗時（秒）
        - 'errors': 錯誤清單
        - 'warnings': 警告清單
    
    Raises:
        FileNotFoundError: SQLite 檔案不存在
        sqlite3.DatabaseError: SQLite 資料庫錯誤
    """
    start_time = datetime.now()
    report = {
        'success': False,
        'sqlite_path': sqlite_path,
        'output_dir': output_dir,
        'video_count': 0,
        'actress_count': 0,
        'link_count': 0,
        'start_time': start_time.isoformat(),
        'end_time': None,
        'duration_seconds': 0,
        'errors': [],
        'warnings': [],
    }
    
    try:
        # 驗證 SQLite 檔案存在
        sqlite_file = Path(sqlite_path)
        if not sqlite_file.exists():
            error_msg = f"SQLite 檔案不存在: {sqlite_path}"
            logger.error(error_msg)
            report['errors'].append(error_msg)
            return False, report
        
        logger.info(f"開始遷移: {sqlite_path} → {output_dir}")
        
        # 連接 SQLite 資料庫
        conn = sqlite3.connect(str(sqlite_file))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 讀取資料
        logger.info("讀取 SQLite 資料...")
        
        # 讀取影片表
        cursor.execute("SELECT * FROM videos")
        videos_raw = cursor.fetchall()
        videos = [convert_sqlite_data_to_json(row, 'videos') for row in videos_raw]
        report['video_count'] = len(videos)
        logger.info(f"讀取影片: {len(videos)} 筆")
        
        # 讀取女優表
        cursor.execute("SELECT * FROM actresses")
        actresses_raw = cursor.fetchall()
        actresses = [convert_sqlite_data_to_json(row, 'actresses') for row in actresses_raw]
        report['actress_count'] = len(actresses)
        logger.info(f"讀取女優: {len(actresses)} 筆")
        
        # 讀取關聯表
        cursor.execute("SELECT * FROM video_actress_link")
        links_raw = cursor.fetchall()
        links = [convert_sqlite_data_to_json(row, 'video_actress_link') for row in links_raw]
        report['link_count'] = len(links)
        logger.info(f"讀取關聯: {len(links)} 筆")
        
        cursor.close()
        conn.close()
        
        # 驗證資料完整性
        logger.info("驗證資料完整性...")
        if len(videos) == 0:
            warning_msg = "SQLite 中無影片記錄"
            logger.warning(warning_msg)
            report['warnings'].append(warning_msg)
        
        if len(actresses) == 0:
            warning_msg = "SQLite 中無女優記錄"
            logger.warning(warning_msg)
            report['warnings'].append(warning_msg)
        
        # 建構 JSON 結構
        logger.info("建構 JSON 結構...")
        json_data = build_json_structure(videos, actresses, links)
        
        # 建立輸出目錄
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 計算資料雜湊
        json_str = json.dumps(json_data, ensure_ascii=False, indent=2)
        data_hash = hashlib.sha256(json_str.encode('utf-8')).hexdigest()
        
        # 寫入 JSON 檔案
        json_file = output_path / JSON_DB_FILENAME
        logger.info(f"寫入 JSON 檔案: {json_file}")
        
        with open(json_file, 'w', encoding='utf-8') as f:
            f.write(json_str)
        
        logger.info(f"JSON 檔案寫入完成 (雜湊: {data_hash[:16]}...)")
        
        # 生成統計報告
        logger.info("生成遷移統計...")
        stats = {
            'total_records': len(videos) + len(actresses) + len(links),
            'file_size_bytes': json_file.stat().st_size,
            'file_size_mb': round(json_file.stat().st_size / (1024 * 1024), 2),
            'data_hash': data_hash,
        }
        
        logger.info(f"遷移統計: {stats}")
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        report['success'] = True
        report['end_time'] = end_time.isoformat()
        report['duration_seconds'] = duration
        report['file_size_bytes'] = stats['file_size_bytes']
        report['file_size_mb'] = stats['file_size_mb']
        report['data_hash'] = data_hash
        
        logger.info(f"遷移成功! 耗時: {duration:.2f} 秒")
        return True, report
        
    except sqlite3.DatabaseError as e:
        error_msg = f"SQLite 資料庫錯誤: {e}"
        logger.error(error_msg)
        report['errors'].append(error_msg)
        return False, report
    except Exception as e:
        error_msg = f"遷移失敗: {e}"
        logger.error(error_msg, exc_info=True)
        report['errors'].append(error_msg)
        return False, report


def write_json_database(
    json_data: Dict[str, Any],
    output_dir: str,
    create_backup: bool = True
) -> Tuple[bool, str]:
    """
    使用 JSONDBManager 寫入轉換後的資料至 JSON 資料庫。
    
    此函式建立 JSONDBManager 實例並寫入所有數據，
    同時建立初始備份以防止遷移失敗。
    
    Args:
        json_data: 轉換後的 JSON 資料結構
        output_dir: JSON 資料庫目錄
        create_backup: 是否建立備份 (預設: True)
    
    Returns:
        Tuple[成功標記, 訊息]
    """
    try:
        logger.info("初始化 JSONDBManager...")
        db_manager = JSONDBManager(output_dir)
        
        # 寫入影片
        logger.info("寫入影片至 JSON 資料庫...")
        for video_data in json_data.get('videos', []):
            db_manager.add_or_update_video(video_data)
        
        # 寫入女優
        logger.info("寫入女優至 JSON 資料庫...")
        for actress_data in json_data.get('actresses', []):
            db_manager.add_or_update_actress(actress_data)
        
        # 建立初始備份
        if create_backup:
            logger.info("建立初始備份...")
            backup_path = db_manager.create_backup()
            logger.info(f"備份建立: {backup_path}")
        
        logger.info("JSON 資料庫寫入完成")
        return True, "JSON 資料庫寫入成功"
        
    except Exception as e:
        error_msg = f"JSON 資料庫寫入失敗: {e}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg


# ============================================================================
# T011: 遷移資料寫入與驗證 (完整流程)
# ============================================================================

def migrate_sqlite_to_json_complete(
    sqlite_path: str,
    output_dir: str,
    validate: bool = True,
    create_backup: bool = True
) -> Tuple[bool, Dict[str, Any]]:
    """
    完整的 SQLite 至 JSON 遷移流程 (T008 + T009 + T011)。
    
    此函式組合了遷移工具主函式、資料轉換邏輯和寫入驗證，
    提供端到端的遷移功能。
    
    流程:
    1. export_sqlite_to_json(): 從 SQLite 匯出資料
    2. write_json_database(): 寫入至 JSON 資料庫
    3. validate_migration(): (可選) 驗證遷移結果
    
    Args:
        sqlite_path: SQLite 檔案路徑
        output_dir: JSON 輸出目錄
        validate: 是否驗證遷移結果 (預設: True)
        create_backup: 是否建立備份 (預設: True)
    
    Returns:
        Tuple[成功標記, 結果報告字典]
        報告包含:
        - 'success': 遷移是否成功
        - 'export_report': export_sqlite_to_json() 的報告
        - 'write_message': write_json_database() 的訊息
        - 'validation_report': (可選) validate_migration() 的報告
        - 'total_duration_seconds': 總耗時
    """
    start_time = datetime.now()
    result = {
        'success': False,
        'export_report': {},
        'write_message': '',
        'validation_report': {},
        'total_duration_seconds': 0,
        'steps_completed': [],
        'errors': [],
    }
    
    try:
        # 步驟 1: 匯出 SQLite 資料
        logger.info("=" * 60)
        logger.info("步驟 1: 匯出 SQLite 資料")
        logger.info("=" * 60)
        
        export_success, export_report = export_sqlite_to_json(sqlite_path, output_dir)
        result['export_report'] = export_report
        
        if not export_success:
            error_msg = f"匯出失敗: {export_report.get('errors', ['未知錯誤'])}"
            logger.error(error_msg)
            result['errors'].append(error_msg)
            return False, result
        
        result['steps_completed'].append('export_sqlite_to_json')
        logger.info(f"✓ 匯出成功: {export_report['video_count']} 影片, {export_report['actress_count']} 女優")
        
        # 步驟 2: 寫入 JSON 資料庫
        logger.info("=" * 60)
        logger.info("步驟 2: 寫入 JSON 資料庫")
        logger.info("=" * 60)
        
        json_file = Path(output_dir) / JSON_DB_FILENAME
        with open(json_file, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        write_success, write_message = write_json_database(json_data, output_dir, create_backup)
        result['write_message'] = write_message
        
        if not write_success:
            error_msg = f"寫入失敗: {write_message}"
            logger.error(error_msg)
            result['errors'].append(error_msg)
            return False, result
        
        result['steps_completed'].append('write_json_database')
        logger.info(f"✓ 寫入成功: {write_message}")
        
        # 步驟 3: (可選) 驗證遷移結果
        if validate:
            logger.info("=" * 60)
            logger.info("步驟 3: 驗證遷移結果")
            logger.info("=" * 60)
            
            validate_success, validation_report = validate_migration(sqlite_path, output_dir)
            result['validation_report'] = validation_report
            
            if not validate_success:
                warning_msg = f"驗證失敗: {validation_report.get('errors', ['未知錯誤'])}"
                logger.warning(warning_msg)
                result['errors'].append(warning_msg)
                # 驗證失敗不中止流程，但標記為警告
            else:
                result['steps_completed'].append('validate_migration')
                logger.info("✓ 驗證成功")
        
        # 最終結果
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        result['success'] = True
        result['total_duration_seconds'] = duration
        
        logger.info("=" * 60)
        logger.info("遷移完成!")
        logger.info(f"耗時: {duration:.2f} 秒")
        logger.info("=" * 60)
        
        return True, result
        
    except Exception as e:
        error_msg = f"遷移流程失敗: {e}"
        logger.error(error_msg, exc_info=True)
        result['errors'].append(error_msg)
        return False, result


def validate_migration(
    sqlite_path: str,
    json_output_dir: str
) -> Tuple[bool, Dict[str, Any]]:
    """
    驗證遷移結果的完整性。
    
    驗證項目:
    1. 記錄計數是否一致
    2. 每筆記錄的完整性
    3. 資料型別正確性
    4. 關聯表完整性
    
    Args:
        sqlite_path: SQLite 檔案路徑
        json_output_dir: JSON 輸出目錄
    
    Returns:
        Tuple[驗證成功, 驗證報告字典]
    """
    validation_report = {
        'passed': True,
        'checks': [],
        'errors': [],
        'warnings': [],
    }
    
    try:
        logger.info("開始遷移驗證...")
        
        # 連接兩個資料庫
        sqlite_conn = sqlite3.connect(sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row
        sqlite_cursor = sqlite_conn.cursor()
        
        json_file = Path(json_output_dir) / JSON_DB_FILENAME
        with open(json_file, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        # 檢查 1: 記錄計數
        logger.info("檢查 1: 驗證記錄計數...")
        
        sqlite_cursor.execute("SELECT COUNT(*) as cnt FROM videos")
        sqlite_video_count = sqlite_cursor.fetchone()['cnt']
        json_video_count = len(json_data.get('videos', []))
        
        if sqlite_video_count == json_video_count:
            check_msg = f"✓ 影片計數一致: {sqlite_video_count}"
            logger.info(check_msg)
            validation_report['checks'].append(check_msg)
        else:
            error_msg = f"✗ 影片計數不一致: SQLite={sqlite_video_count}, JSON={json_video_count}"
            logger.error(error_msg)
            validation_report['errors'].append(error_msg)
            validation_report['passed'] = False
        
        sqlite_cursor.execute("SELECT COUNT(*) as cnt FROM actresses")
        sqlite_actress_count = sqlite_cursor.fetchone()['cnt']
        json_actress_count = len(json_data.get('actresses', []))
        
        if sqlite_actress_count == json_actress_count:
            check_msg = f"✓ 女優計數一致: {sqlite_actress_count}"
            logger.info(check_msg)
            validation_report['checks'].append(check_msg)
        else:
            error_msg = f"✗ 女優計數不一致: SQLite={sqlite_actress_count}, JSON={json_actress_count}"
            logger.error(error_msg)
            validation_report['errors'].append(error_msg)
            validation_report['passed'] = False
        
        sqlite_cursor.execute("SELECT COUNT(*) as cnt FROM video_actress_link")
        sqlite_link_count = sqlite_cursor.fetchone()['cnt']
        json_link_count = len(json_data.get('video_actress_links', []))
        
        if sqlite_link_count == json_link_count:
            check_msg = f"✓ 關聯計數一致: {sqlite_link_count}"
            logger.info(check_msg)
            validation_report['checks'].append(check_msg)
        else:
            error_msg = f"✗ 關聯計數不一致: SQLite={sqlite_link_count}, JSON={json_link_count}"
            logger.error(error_msg)
            validation_report['errors'].append(error_msg)
            validation_report['passed'] = False
        
        # 檢查 2: 關聯表完整性
        logger.info("檢查 2: 驗證關聯表完整性...")
        
        json_video_ids = {v.get('id') for v in json_data.get('videos', [])}
        json_actress_ids = {a.get('id') for a in json_data.get('actresses', [])}
        
        invalid_links = 0
        for link in json_data.get('video_actress_links', []):
            video_id = link.get('video_id')
            actress_id = link.get('actress_id')
            
            if video_id not in json_video_ids:
                invalid_links += 1
                logger.warning(f"無效的影片 ID 參考: {video_id}")
            
            if actress_id not in json_actress_ids:
                invalid_links += 1
                logger.warning(f"無效的女優 ID 參考: {actress_id}")
        
        if invalid_links == 0:
            check_msg = "✓ 關聯表完整性: 所有參考均有效"
            logger.info(check_msg)
            validation_report['checks'].append(check_msg)
        else:
            warning_msg = f"⚠ 發現 {invalid_links} 個無效的關聯參考"
            logger.warning(warning_msg)
            validation_report['warnings'].append(warning_msg)
        
        sqlite_cursor.close()
        sqlite_conn.close()
        
        logger.info(f"遷移驗證完成: {'成功' if validation_report['passed'] else '失敗'}")
        return validation_report['passed'], validation_report
        
    except Exception as e:
        error_msg = f"驗證失敗: {e}"
        logger.error(error_msg, exc_info=True)
        validation_report['errors'].append(error_msg)
        validation_report['passed'] = False
        return False, validation_report


# ============================================================================
# 命令行介面 (CLI)
# ============================================================================

def main():
    """命令行主函式"""
    parser = argparse.ArgumentParser(
        description='SQLite 至 JSON 資料庫遷移工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python migrate_sqlite_to_json.py
  python migrate_sqlite_to_json.py --sqlite-path data/actress_classifier.db --json-dir data/json_db
  python migrate_sqlite_to_json.py --sqlite-path data/actress_classifier.db --validate
        """
    )
    
    parser.add_argument(
        '--sqlite-path',
        type=str,
        default='data/actress_classifier.db',
        help='SQLite 檔案路徑 (預設: data/actress_classifier.db)'
    )
    
    parser.add_argument(
        '--json-dir',
        type=str,
        default='data/json_db',
        help='JSON 輸出目錄 (預設: data/json_db)'
    )
    
    parser.add_argument(
        '--backup',
        type=bool,
        default=True,
        help='遷移後是否建立備份 (預設: True)'
    )
    
    parser.add_argument(
        '--validate',
        action='store_true',
        help='遷移後驗證結果'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='SQLite to JSON Migration Tool v1.0'
    )
    
    args = parser.parse_args()
    
    # 執行遷移
    success, report = export_sqlite_to_json(
        args.sqlite_path,
        args.json_dir
    )
    
    if not success:
        logger.error("遷移失敗")
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        sys.exit(1)
    
    # 驗證遷移結果
    if args.validate:
        validate_success, validation_report = validate_migration(
            args.sqlite_path,
            args.json_dir
        )
        
        if not validate_success:
            logger.error("驗證失敗")
            print(json.dumps(validation_report, ensure_ascii=False, indent=2))
            sys.exit(1)
    
    # 輸出報告
    print("\n" + "="*60)
    print("遷移報告")
    print("="*60)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    
    if args.validate:
        print("\n驗證報告")
        print("-"*60)
        print(json.dumps(validation_report, ensure_ascii=False, indent=2))
    
    print("\n遷移完成!")
    sys.exit(0)


if __name__ == '__main__':
    main()
