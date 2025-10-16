# -*- coding: utf-8 -*-
"""
資料庫管理模組
"""
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 修正 sqlite3 DeprecationWarning
sqlite3.register_adapter(datetime, lambda val: val.isoformat())
sqlite3.register_converter("timestamp", lambda val: datetime.fromisoformat(val.decode()))


class SQLiteDBManager:
    """SQLite 資料庫管理器"""
    
    def __init__(self, db_path: str):
        if not db_path: 
            raise ValueError("資料庫路徑不能為空。請檢查您的 config.ini 檔案。")
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_schema()
    
    def _get_connection(self):
        return sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    
    def _create_schema(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 建立主要影片資料表（基本結構）
            cursor.execute('''CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY, 
                code TEXT NOT NULL UNIQUE, 
                original_filename TEXT, 
                file_path TEXT, 
                studio TEXT, 
                search_method TEXT, 
                last_updated TIMESTAMP
            )''')
            
            # 建立女優資料表
            cursor.execute('CREATE TABLE IF NOT EXISTS actresses (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)')
            
            # 建立影片與女優關聯表（增強版 - 包含檔案關聯類型）
            cursor.execute('''CREATE TABLE IF NOT EXISTS video_actress_link (
                video_id INTEGER, 
                actress_id INTEGER, 
                file_association_type TEXT DEFAULT 'primary',  -- 檔案關聯類型: primary, secondary, collaboration
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (video_id, actress_id), 
                FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE, 
                FOREIGN KEY (actress_id) REFERENCES actresses(id) ON DELETE CASCADE
            )''')
            
            # 檢查是否需要新增欄位（支援既有資料庫升級）
            cursor.execute("PRAGMA table_info(videos)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'studio_code' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN studio_code TEXT')
                logger.info("已新增 studio_code 欄位至資料庫")
                
            if 'release_date' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN release_date TEXT')
                logger.info("已新增 release_date 欄位至資料庫")
            
            if 'search_status' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN search_status TEXT DEFAULT "not_searched"')
                logger.info("已新增 search_status 欄位至資料庫 (値: not_searched, searched_found, searched_not_found, failed)")
            
            if 'last_search_date' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN last_search_date TIMESTAMP')
                logger.info("已新增 last_search_date 欄位至資料庫")
            
            # 建立索引以提升查詢效能（在欄位確保存在之後）
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_code ON videos(code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_studio ON videos(studio)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_actress_name ON actresses(name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_status ON videos(search_status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_last_search_date ON videos(last_search_date)')
            
            # 檢查新欄位索引（只有在欄位存在時才建立）
            cursor.execute("PRAGMA table_info(videos)")
            current_columns = [column[1] for column in cursor.fetchall()]
            
            if 'studio_code' in current_columns:
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_studio_code ON videos(studio_code)')
            
            # 檢查並升級 video_actress_link 表結構
            cursor.execute("PRAGMA table_info(video_actress_link)")
            link_columns = [column[1] for column in cursor.fetchall()]
            
            if 'file_association_type' not in link_columns:
                logger.info("升級 video_actress_link 表，添加 file_association_type 欄位...")
                cursor.execute('ALTER TABLE video_actress_link ADD COLUMN file_association_type TEXT DEFAULT "primary"')
                
            if 'created_date' not in link_columns:
                logger.info("升級 video_actress_link 表，添加 created_date 欄位...")
                # SQLite 不支援 ALTER TABLE 時使用 CURRENT_TIMESTAMP 預設值
                # 先添加欄位為 NULL，然後更新現有記錄
                cursor.execute('ALTER TABLE video_actress_link ADD COLUMN created_date TIMESTAMP')
                # 為現有記錄設定預設時間戳
                cursor.execute('UPDATE video_actress_link SET created_date = CURRENT_TIMESTAMP WHERE created_date IS NULL')
            
            # 建立新的索引以提升查詢效能
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_link_association_type ON video_actress_link(file_association_type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_link_created_date ON video_actress_link(created_date)')
            
            conn.commit()
    
    def add_or_update_video(self, code: str, info: Dict):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM videos WHERE code = ?", (code,))
            video_row = cursor.fetchone()
            
            # 準備片商相關資訊
            studio = info.get('studio')
            studio_code = info.get('studio_code')
            release_date = info.get('release_date')
            search_status = info.get('search_status', 'not_searched')
            last_search_date = info.get('last_search_date')
            
            if video_row:
                video_id = video_row[0]
                cursor.execute("""UPDATE videos SET 
                    original_filename=?, file_path=?, studio=?, studio_code=?, 
                    release_date=?, search_method=?, last_updated=?, 
                    search_status=?, last_search_date=? 
                    WHERE id=?""", 
                    (info.get('original_filename'), str(info.get('file_path')), 
                     studio, studio_code, release_date, info.get('search_method'), 
                     datetime.now(), search_status, last_search_date, video_id))
            else:
                cursor.execute("""INSERT INTO videos 
                    (code, original_filename, file_path, studio, studio_code, 
                     release_date, search_method, last_updated, search_status, last_search_date) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                    (code, info.get('original_filename'), str(info.get('file_path')), 
                     studio, studio_code, release_date, info.get('search_method'), 
                     datetime.now(), search_status, last_search_date))
                video_id = cursor.lastrowid
                
            actress_names = info.get('actresses', [])
            if not actress_names: 
                conn.commit()
                return
                
            actress_ids = []
            for name in actress_names:
                cursor.execute("INSERT OR IGNORE INTO actresses (name) VALUES (?)", (name,))
                cursor.execute("SELECT id FROM actresses WHERE name = ?", (name,))
                actress_id_row = cursor.fetchone()
                if actress_id_row: 
                    actress_ids.append(actress_id_row[0])
                    
            cursor.execute("DELETE FROM video_actress_link WHERE video_id = ?", (video_id,))
            if actress_ids:
                # 決定檔案關聯類型
                for i, actress_id in enumerate(actress_ids):
                    if len(actress_ids) == 1:
                        association_type = 'primary'  # 單人作品
                    elif i == 0:
                        association_type = 'primary'  # 主要女優（第一位）
                    else:
                        association_type = 'collaboration'  # 共演女優
                    
                    cursor.execute("""INSERT OR IGNORE INTO video_actress_link 
                                    (video_id, actress_id, file_association_type, created_date) 
                                    VALUES (?, ?, ?, ?)""", 
                                 (video_id, actress_id, association_type, datetime.now()))
            
            conn.commit()
            
            # 記錄片商資訊寫入結果
            if studio or studio_code:
                logger.info(f"已更新番號 {code} 的片商資訊: {studio} ({studio_code})")
            else:
                logger.debug(f"番號 {code} 未找到片商資訊")
    
    def get_video_info(self, code: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE code = ?", (code,))
            video_row = cursor.fetchone()
            if not video_row: 
                return None
            video_id, code_val, *video_data = video_row
            cursor.execute("SELECT a.name FROM actresses a JOIN video_actress_link va ON a.id = va.actress_id WHERE va.video_id = ?", (video_id,))
            actresses = [row[0] for row in cursor.fetchall()]
            return {
                'code': code_val, 
                'original_filename': video_data[0], 
                'file_path': video_data[1], 
                'studio': video_data[2], 
                'studio_code': video_data[3],
                'release_date': video_data[4],
                'search_method': video_data[5], 
                'last_updated': video_data[6], 
                'actresses': actresses
            }
    
    def get_all_videos(self) -> List[Dict]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM videos")
            return [dict(row) for row in cursor.fetchall()]

    def get_actress_statistics(self) -> List[Dict]:
        """取得女優統計資訊，包含片商分佈"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    a.name as actress_name,
                    COUNT(v.id) as video_count,
                    GROUP_CONCAT(DISTINCT v.studio) as studios,
                    GROUP_CONCAT(DISTINCT v.studio_code) as studio_codes
                FROM actresses a
                LEFT JOIN video_actress_link va ON a.id = va.actress_id
                LEFT JOIN videos v ON va.video_id = v.id
                GROUP BY a.name
                ORDER BY video_count DESC
            """)
            return [
                {
                    'actress_name': row[0],
                    'video_count': row[1],
                    'studios': row[2].split(',') if row[2] else [],
                    'studio_codes': row[3].split(',') if row[3] else []
                }
                for row in cursor.fetchall()
            ]

    def get_studio_statistics(self) -> List[Dict]:
        """取得片商統計資訊"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    studio,
                    studio_code,
                    COUNT(*) as video_count,
                    COUNT(DISTINCT va.actress_id) as actress_count
                FROM videos v
                LEFT JOIN video_actress_link va ON v.id = va.video_id
                WHERE studio IS NOT NULL
                GROUP BY studio, studio_code
                ORDER BY video_count DESC
            """)
            return [
                {
                    'studio': row[0],
                    'studio_code': row[1],
                    'video_count': row[2],
                    'actress_count': row[3]
                }
                for row in cursor.fetchall()
            ]

    def get_enhanced_actress_studio_statistics(self, actress_name: str = None) -> List[Dict]:
        """取得增強版女優片商統計資訊（包含檔案關聯類型分析）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            base_query = """
                SELECT 
                    a.name as actress_name,
                    v.studio,
                    v.studio_code,
                    va.file_association_type,
                    COUNT(*) as video_count,
                    GROUP_CONCAT(v.code) as video_codes,
                    MIN(va.created_date) as first_appearance,
                    MAX(va.created_date) as latest_appearance
                FROM actresses a
                JOIN video_actress_link va ON a.id = va.actress_id
                JOIN videos v ON va.video_id = v.id
                WHERE v.studio IS NOT NULL AND v.studio != 'UNKNOWN'
            """
            
            if actress_name:
                base_query += " AND a.name = ?"
                cursor.execute(base_query + " GROUP BY a.name, v.studio, v.studio_code, va.file_association_type ORDER BY video_count DESC", (actress_name,))
            else:
                cursor.execute(base_query + " GROUP BY a.name, v.studio, v.studio_code, va.file_association_type ORDER BY a.name, video_count DESC")
            
            return [
                {
                    'actress_name': row[0],
                    'studio': row[1],
                    'studio_code': row[2],
                    'association_type': row[3],
                    'video_count': row[4],
                    'video_codes': row[5].split(',') if row[5] else [],
                    'first_appearance': row[6],
                    'latest_appearance': row[7]
                }
                for row in cursor.fetchall()
            ]

    def analyze_actress_primary_studio(self, actress_name: str, major_studios: set = None) -> Dict:
        """
        分析女優的主要片商（基於檔案關聯類型和番號統計）。
        若影片數<=3且屬於大片商，推薦分類為片商。
        major_studios: 傳入大片商集合以支援例外邏輯。
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 獲取該女優的詳細片商統計
            cursor.execute("""
                SELECT 
                    v.studio,
                    v.studio_code,
                    va.file_association_type,
                    COUNT(*) as video_count,
                    GROUP_CONCAT(v.code) as codes
                FROM actresses a
                JOIN video_actress_link va ON a.id = va.actress_id
                JOIN videos v ON va.video_id = v.id
                WHERE a.name = ? AND v.studio IS NOT NULL AND v.studio != 'UNKNOWN'
                GROUP BY v.studio, v.studio_code, va.file_association_type
                ORDER BY video_count DESC
            """, (actress_name,))
            
            studio_stats = {}
            total_videos = 0
            
            for row in cursor.fetchall():
                studio, studio_code, association_type, count, codes = row
                total_videos += count
                
                if studio not in studio_stats:
                    studio_stats[studio] = {
                        'studio_code': studio_code,
                        'primary_count': 0,
                        'collaboration_count': 0,
                        'total_count': 0,
                        'codes': []
                    }
                
                studio_stats[studio]['total_count'] += count
                studio_stats[studio]['codes'].extend(codes.split(',') if codes else [])
                
                if association_type == 'primary':
                    studio_stats[studio]['primary_count'] += count
                elif association_type == 'collaboration':
                    studio_stats[studio]['collaboration_count'] += count
            
            # 計算主要片商
            if not studio_stats:
                return {
                    'actress_name': actress_name,
                    'primary_studio': 'UNKNOWN',
                    'confidence': 0.0,
                    'total_videos': 0,
                    'studio_distribution': {},
                    'recommendation': 'solo_artist'
                }
            
            # 優先考慮 primary 作品較多的片商
            best_studio = None
            best_score = 0
            
            for studio, stats in studio_stats.items():
                # 計算綜合評分：primary作品權重更高
                primary_weight = 3.0  # primary 作品權重
                collaboration_weight = 1.0  # collaboration 作品權重
                
                weighted_score = (stats['primary_count'] * primary_weight + 
                                stats['collaboration_count'] * collaboration_weight)
                
                if weighted_score > best_score:
                    best_score = weighted_score
                    best_studio = studio
            
            # 計算信心度
            if best_studio and total_videos > 0:
                best_stats = studio_stats[best_studio]
                confidence = (best_stats['total_count'] / total_videos) * 100
                
                # 如果主要作品比例很高，提升信心度
                if total_videos > 0:
                    primary_ratio = best_stats['primary_count'] / total_videos
                    if primary_ratio > 0.7:  # 70%以上是主要作品
                        confidence = min(confidence * 1.2, 100)  # 提升20%信心度
            else:
                confidence = 0            # 決定推薦分類 - 改進的大片商優先邏輯
            recommendation = 'solo_artist'  # 預設值
            
            # 檢查是否有大片商作品
            has_major_studio_work = False
            major_studio_work_count = 0
            minor_studio_work_count = 0
            best_major_studio = None
            best_major_confidence = 0
            
            if major_studios:
                for studio, stats in studio_stats.items():
                    if studio in major_studios:
                        has_major_studio_work = True
                        major_studio_work_count += stats['total_count']
                        # 找出作品數最多的大片商
                        if stats['total_count'] > best_major_confidence:
                            best_major_confidence = stats['total_count']
                            best_major_studio = studio
                    else:
                        minor_studio_work_count += stats['total_count']
            
            # 新的分類邏輯
            if has_major_studio_work:
                # 有大片商作品的女優
                if best_major_studio and best_major_studio == best_studio:
                    # 最佳片商就是大片商
                    if best_stats['total_count'] >= 3 and confidence >= 70:
                        # 標準條件：≥3部作品且信心度≥70%
                        recommendation = 'studio_classification'
                    elif best_stats['total_count'] >= 1 and minor_studio_work_count < 10:
                        # 新增條件：有大片商作品且小片商作品<10部
                        recommendation = 'studio_classification'
                        confidence = max(confidence, 60.0)  # 提升信心度
                    else:
                        # 小片商作品過多（≥10部），分類為單體企劃
                        recommendation = 'solo_artist'
                elif best_major_studio:
                    # 最佳片商不是大片商，但有大片商作品
                    if major_studio_work_count >= 1 and minor_studio_work_count < 10:
                        # 有大片商作品且小片商作品不多，優先考慮大片商
                        recommendation = 'studio_classification'
                        best_studio = best_major_studio  # 改用大片商作為分類依據
                        # 重新計算該大片商的信心度
                        major_studio_confidence = (studio_stats[best_major_studio]['total_count'] / total_videos) * 100
                        confidence = max(major_studio_confidence, 60.0)
                    else:
                        recommendation = 'solo_artist'
                else:
                    recommendation = 'solo_artist'
            else:
                # 沒有大片商作品，一律歸類為單體企劃
                recommendation = 'solo_artist'
            
            return {
                'actress_name': actress_name,
                'primary_studio': best_studio or 'UNKNOWN',
                'confidence': round(confidence, 1),
                'total_videos': total_videos,
                'studio_distribution': studio_stats,
                'recommendation': recommendation
            }
