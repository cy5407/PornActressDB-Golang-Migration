# -*- coding: utf-8 -*-
"""
智慧快取管理模組
提供高效的多層級快取機制
"""

import asyncio
import sqlite3
import json
import hashlib
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, List, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
import pickle
import gzip

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """快取配置類"""
    cache_dir: str = "cache"                    # 快取目錄
    db_file: str = "cache_index.db"             # SQLite索引檔案
    default_ttl_hours: int = 24                 # 預設TTL(小時)
    max_memory_entries: int = 1000              # 記憶體快取最大條目數
    enable_compression: bool = True             # 啟用壓縮
    enable_memory_cache: bool = True            # 啟用記憶體快取
    enable_disk_cache: bool = True              # 啟用磁碟快取
    cleanup_interval_hours: int = 6             # 清理間隔(小時)
    max_file_size_mb: int = 10                  # 單檔最大大小(MB)


@dataclass
class CacheEntry:
    """快取條目"""
    key: str
    value: Any
    created_at: float
    ttl_seconds: int
    access_count: int = 0
    last_accessed: float = 0.0
    compressed: bool = False
    size_bytes: int = 0


class CacheManager:
    """多層級智慧快取管理器"""
    
    def __init__(self, config: CacheConfig = None):
        self.config = config or CacheConfig()
        self.cache_dir = Path(self.config.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 記憶體快取
        self.memory_cache: Dict[str, CacheEntry] = {}
        self.memory_lock = threading.RLock()
        
        # 資料庫連線
        self.db_path = self.cache_dir / self.config.db_file
        self._init_database()
        
        # 統計資訊
        self.stats = {
            'memory_hits': 0,
            'disk_hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'cleanups': 0,
            'total_size_mb': 0.0
        }
        
        # 啟動背景清理任務
        self._start_cleanup_task()
        
        logger.info(f"💾 快取管理器已初始化 - 目錄: {self.cache_dir}")
    
    def _init_database(self):
        """初始化SQLite索引資料庫"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS cache_index (
                        key TEXT PRIMARY KEY,
                        file_path TEXT,
                        created_at REAL,
                        ttl_seconds INTEGER,
                        access_count INTEGER DEFAULT 0,
                        last_accessed REAL,
                        compressed BOOLEAN DEFAULT 0,
                        size_bytes INTEGER DEFAULT 0
                    )
                ''')
                
                # 創建索引
                conn.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON cache_index(created_at)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_last_accessed ON cache_index(last_accessed)')
                
                conn.commit()
                logger.debug("📊 快取索引資料庫已初始化")
                
        except Exception as e:
            logger.error(f"初始化快取資料庫失敗: {e}")
    
    def _generate_cache_key(self, key: str) -> str:
        """生成快取鍵值"""
        return hashlib.sha256(key.encode('utf-8')).hexdigest()
    
    def _get_file_path(self, cache_key: str) -> Path:
        """獲取快取檔案路徑"""
        # 使用兩層目錄結構避免單目錄檔案過多
        dir1 = cache_key[:2]
        dir2 = cache_key[2:4]
        cache_file_dir = self.cache_dir / dir1 / dir2
        cache_file_dir.mkdir(parents=True, exist_ok=True)
        return cache_file_dir / f"{cache_key}.cache"
    
    def _serialize_value(self, value: Any) -> Tuple[bytes, bool]:
        """序列化值並選擇性壓縮"""
        try:
            # 序列化
            serialized = pickle.dumps(value)
            
            # 決定是否壓縮
            should_compress = (
                self.config.enable_compression and 
                len(serialized) > 1024  # 超過1KB才壓縮
            )
            
            if should_compress:
                compressed_data = gzip.compress(serialized)
                # 只有在壓縮有效果時才使用
                if len(compressed_data) < len(serialized) * 0.9:
                    return compressed_data, True
            
            return serialized, False
            
        except Exception as e:
            logger.error(f"序列化值失敗: {e}")
            return b'', False
    
    def _deserialize_value(self, data: bytes, compressed: bool) -> Any:
        """反序列化值"""
        try:
            if compressed:
                data = gzip.decompress(data)
            return pickle.loads(data)
        except Exception as e:
            logger.error(f"反序列化值失敗: {e}")
            return None
    
    def _is_expired(self, created_at: float, ttl_seconds: int) -> bool:
        """檢查是否過期"""
        return time.time() - created_at > ttl_seconds
    
    def set(self, key: str, value: Any, ttl_hours: Optional[int] = None) -> bool:
        """設置快取值"""
        ttl_seconds = (ttl_hours or self.config.default_ttl_hours) * 3600
        cache_key = self._generate_cache_key(key)
        current_time = time.time()
        
        try:
            # 序列化和壓縮
            serialized_data, compressed = self._serialize_value(value)
            size_bytes = len(serialized_data)
            
            # 檢查檔案大小限制
            max_size_bytes = self.config.max_file_size_mb * 1024 * 1024
            if size_bytes > max_size_bytes:
                logger.warning(f"快取值過大 ({size_bytes/1024/1024:.1f}MB)，跳過快取")
                return False
            
            # 建立快取條目
            entry = CacheEntry(
                key=cache_key,
                value=value,
                created_at=current_time,
                ttl_seconds=ttl_seconds,
                last_accessed=current_time,
                compressed=compressed,
                size_bytes=size_bytes
            )
            
            # 設置記憶體快取
            if self.config.enable_memory_cache:
                with self.memory_lock:
                    self.memory_cache[cache_key] = entry
                    self._cleanup_memory_cache()
            
            # 設置磁碟快取
            if self.config.enable_disk_cache:
                file_path = self._get_file_path(cache_key)
                
                # 寫入檔案
                with open(file_path, 'wb') as f:
                    f.write(serialized_data)
                
                # 更新索引
                with sqlite3.connect(str(self.db_path)) as conn:
                    conn.execute('''
                        INSERT OR REPLACE INTO cache_index 
                        (key, file_path, created_at, ttl_seconds, last_accessed, compressed, size_bytes)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        cache_key, str(file_path), current_time, ttl_seconds,
                        current_time, compressed, size_bytes
                    ))
                    conn.commit()
            
            self.stats['sets'] += 1
            logger.debug(f"💾 已快取: {key} ({size_bytes} bytes)")
            return True
            
        except Exception as e:
            logger.error(f"設置快取失敗: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """獲取快取值"""
        cache_key = self._generate_cache_key(key)
        current_time = time.time()
        
        # 嘗試記憶體快取
        if self.config.enable_memory_cache:
            with self.memory_lock:
                if cache_key in self.memory_cache:
                    entry = self.memory_cache[cache_key]
                    
                    # 檢查是否過期
                    if not self._is_expired(entry.created_at, entry.ttl_seconds):
                        entry.access_count += 1
                        entry.last_accessed = current_time
                        self.stats['memory_hits'] += 1
                        logger.debug(f"📋 記憶體快取命中: {key}")
                        return entry.value
                    else:
                        # 過期，從記憶體移除
                        del self.memory_cache[cache_key]
        
        # 嘗試磁碟快取
        if self.config.enable_disk_cache:
            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.execute('''
                        SELECT file_path, created_at, ttl_seconds, compressed, access_count
                        FROM cache_index WHERE key = ?
                    ''', (cache_key,))
                    
                    result = cursor.fetchone()
                    if result:
                        file_path, created_at, ttl_seconds, compressed, access_count = result
                        
                        # 檢查是否過期
                        if not self._is_expired(created_at, ttl_seconds):
                            file_path_obj = Path(file_path)
                            
                            if file_path_obj.exists():
                                # 讀取檔案
                                with open(file_path_obj, 'rb') as f:
                                    data = f.read()
                                
                                # 反序列化
                                value = self._deserialize_value(data, compressed)
                                
                                if value is not None:
                                    # 更新訪問統計
                                    conn.execute('''
                                        UPDATE cache_index 
                                        SET access_count = access_count + 1, last_accessed = ?
                                        WHERE key = ?
                                    ''', (current_time, cache_key))
                                    conn.commit()
                                    
                                    # 載入到記憶體快取
                                    if self.config.enable_memory_cache:
                                        with self.memory_lock:
                                            entry = CacheEntry(
                                                key=cache_key,
                                                value=value,
                                                created_at=created_at,
                                                ttl_seconds=ttl_seconds,
                                                access_count=access_count + 1,
                                                last_accessed=current_time,
                                                compressed=compressed,
                                                size_bytes=len(data)
                                            )
                                            self.memory_cache[cache_key] = entry
                                    
                                    self.stats['disk_hits'] += 1
                                    logger.debug(f"💿 磁碟快取命中: {key}")
                                    return value
                        else:
                            # 過期，清理
                            self._delete_cache_entry(cache_key, file_path)
                            
            except Exception as e:
                logger.error(f"讀取磁碟快取失敗: {e}")
        
        self.stats['misses'] += 1
        logger.debug(f"❌ 快取未命中: {key}")
        return None
    
    def delete(self, key: str) -> bool:
        """刪除快取條目"""
        cache_key = self._generate_cache_key(key)
        
        try:
            # 從記憶體移除
            if self.config.enable_memory_cache:
                with self.memory_lock:
                    self.memory_cache.pop(cache_key, None)
            
            # 從磁碟移除
            if self.config.enable_disk_cache:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.execute('SELECT file_path FROM cache_index WHERE key = ?', (cache_key,))
                    result = cursor.fetchone()
                    
                    if result:
                        file_path = result[0]
                        self._delete_cache_entry(cache_key, file_path)
            
            self.stats['deletes'] += 1
            logger.debug(f"🗑️ 已刪除快取: {key}")
            return True
            
        except Exception as e:
            logger.error(f"刪除快取失敗: {e}")
            return False
    
    def _delete_cache_entry(self, cache_key: str, file_path: str):
        """刪除快取條目（檔案和索引）"""
        try:
            # 刪除檔案
            file_path_obj = Path(file_path)
            if file_path_obj.exists():
                file_path_obj.unlink()
            
            # 從索引移除
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute('DELETE FROM cache_index WHERE key = ?', (cache_key,))
                conn.commit()
                
        except Exception as e:
            logger.error(f"刪除快取條目失敗: {e}")
    
    def _cleanup_memory_cache(self):
        """清理記憶體快取（LRU策略）"""
        if len(self.memory_cache) <= self.config.max_memory_entries:
            return
        
        # 按最後訪問時間排序，移除最舊的條目
        sorted_entries = sorted(
            self.memory_cache.items(),
            key=lambda x: x[1].last_accessed
        )
        
        # 移除超出限制的條目
        remove_count = len(self.memory_cache) - self.config.max_memory_entries
        for i in range(remove_count):
            cache_key, _ = sorted_entries[i]
            del self.memory_cache[cache_key]
        
        logger.debug(f"🧹 記憶體快取清理: 移除 {remove_count} 個條目")
    
    def _cleanup_expired_cache(self):
        """清理過期快取"""
        try:
            current_time = time.time()
            
            # 清理記憶體快取
            if self.config.enable_memory_cache:
                with self.memory_lock:
                    expired_keys = [
                        key for key, entry in self.memory_cache.items()
                        if self._is_expired(entry.created_at, entry.ttl_seconds)
                    ]
                    
                    for key in expired_keys:
                        del self.memory_cache[key]
                    
                    if expired_keys:
                        logger.info(f"🧹 記憶體快取清理: {len(expired_keys)} 個過期條目")
            
            # 清理磁碟快取
            if self.config.enable_disk_cache:
                with sqlite3.connect(str(self.db_path)) as conn:
                    # 查找過期條目
                    cursor = conn.execute('''
                        SELECT key, file_path FROM cache_index 
                        WHERE ? - created_at > ttl_seconds
                    ''', (current_time,))
                    
                    expired_entries = cursor.fetchall()
                    
                    # 刪除過期條目
                    for cache_key, file_path in expired_entries:
                        self._delete_cache_entry(cache_key, file_path)
                    
                    if expired_entries:
                        logger.info(f"🧹 磁碟快取清理: {len(expired_entries)} 個過期條目")
            
            self.stats['cleanups'] += 1
            
        except Exception as e:
            logger.error(f"清理過期快取失敗: {e}")
    
    def _start_cleanup_task(self):
        """啟動背景清理任務"""
        def cleanup_worker():
            while True:
                try:
                    time.sleep(self.config.cleanup_interval_hours * 3600)
                    self._cleanup_expired_cache()
                except Exception as e:
                    logger.error(f"背景清理任務失敗: {e}")
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        logger.info(f"🧹 背景清理任務已啟動 (間隔: {self.config.cleanup_interval_hours}小時)")
    
    def clear_cache(self):
        """清空所有快取"""
        try:
            # 清空記憶體快取
            if self.config.enable_memory_cache:
                with self.memory_lock:
                    self.memory_cache.clear()
            
            # 清空磁碟快取
            if self.config.enable_disk_cache:
                # 刪除所有快取檔案
                for cache_file in self.cache_dir.rglob("*.cache"):
                    try:
                        cache_file.unlink()
                    except:
                        pass
                
                # 清空索引
                with sqlite3.connect(str(self.db_path)) as conn:
                    conn.execute('DELETE FROM cache_index')
                    conn.commit()
            
            logger.info("🧹 已清空所有快取")
            
        except Exception as e:
            logger.error(f"清空快取失敗: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """獲取快取統計資訊"""
        try:
            # 計算總大小
            total_size_bytes = 0
            if self.config.enable_disk_cache:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.execute('SELECT SUM(size_bytes) FROM cache_index')
                    result = cursor.fetchone()
                    if result and result[0]:
                        total_size_bytes = result[0]
            
            # 記憶體快取大小
            memory_size_bytes = sum(entry.size_bytes for entry in self.memory_cache.values())
            
            total_requests = self.stats['memory_hits'] + self.stats['disk_hits'] + self.stats['misses']
            hit_rate = (
                (self.stats['memory_hits'] + self.stats['disk_hits']) / total_requests * 100
                if total_requests > 0 else 0
            )
            
            return {
                **self.stats,
                'total_size_mb': total_size_bytes / (1024 * 1024),
                'memory_cache_entries': len(self.memory_cache),
                'memory_cache_size_mb': memory_size_bytes / (1024 * 1024),
                'hit_rate': f"{hit_rate:.1f}%",
                'memory_hit_rate': f"{(self.stats['memory_hits'] / total_requests * 100):.1f}%" if total_requests > 0 else "0%",
                'disk_hit_rate': f"{(self.stats['disk_hits'] / total_requests * 100):.1f}%" if total_requests > 0 else "0%",
                'config': asdict(self.config)
            }
            
        except Exception as e:
            logger.error(f"獲取快取統計失敗: {e}")
            return self.stats
    
    # 非同步介面
    async def set_async(self, key: str, value: Any, ttl_hours: Optional[int] = None) -> bool:
        """非同步設置快取值"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.set, key, value, ttl_hours)
    
    async def get_async(self, key: str) -> Optional[Any]:
        """非同步獲取快取值"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get, key)
    
    async def delete_async(self, key: str) -> bool:
        """非同步刪除快取值"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.delete, key)