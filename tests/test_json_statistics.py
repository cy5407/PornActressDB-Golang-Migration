# -*- coding: utf-8 -*-
"""
測試 JSON 資料庫統計查詢方法 (T022, T023, T024)

此模組測試三個統計查詢方法的正確性和效能：
1. get_actress_statistics() - 女優統計查詢 (T022)
2. get_studio_statistics() - 片商統計查詢 (T023)
3. get_enhanced_actress_studio_statistics() - 交叉統計查詢 (T024)
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone

from src.models.json_database import JSONDBManager
from src.models.json_types import ISO_DATETIME_FORMAT


class TestActressStatistics:
    """測試女優統計查詢 (T022)"""
    
    @pytest.fixture
    def db_manager(self):
        """建立臨時測試資料庫"""
        temp_dir = tempfile.mkdtemp()
        db = JSONDBManager(data_dir=temp_dir)
        
        # 建立測試資料
        now = datetime.now(timezone.utc).strftime(ISO_DATETIME_FORMAT)
        
        # 新增女優
        db.add_or_update_actress({
            'id': 'actress_1',
            'name': '山田美優',
            'video_count': 0
        })
        db.add_or_update_actress({
            'id': 'actress_2',
            'name': '佐藤愛',
            'video_count': 0
        })
        db.add_or_update_actress({
            'id': 'actress_3',
            'name': '鈴木花',
            'video_count': 0
        })
        
        # 新增影片
        db.add_or_update_video({
            'id': 'video_1',
            'title': 'Test Video 1',
            'studio': 'S1',
            'studio_code': 'SNIS',
            'release_date': '2023-01-15',
            'actresses': ['actress_1']
        })
        db.add_or_update_video({
            'id': 'video_2',
            'title': 'Test Video 2',
            'studio': 'S1',
            'studio_code': 'SNIS',
            'release_date': '2023-02-20',
            'actresses': ['actress_1']
        })
        db.add_or_update_video({
            'id': 'video_3',
            'title': 'Test Video 3',
            'studio': 'PREMIUM',
            'studio_code': 'PGD',
            'release_date': '2023-03-10',
            'actresses': ['actress_1', 'actress_2']
        })
        db.add_or_update_video({
            'id': 'video_4',
            'title': 'Test Video 4',
            'studio': 'IDEA POCKET',
            'studio_code': 'IPX',
            'release_date': '2023-04-05',
            'actresses': ['actress_2']
        })
        
        # 新增關聯
        db.data['links'] = [
            {'video_id': 'video_1', 'actress_id': 'actress_1', 'role_type': '主演', 'timestamp': now},
            {'video_id': 'video_2', 'actress_id': 'actress_1', 'role_type': '主演', 'timestamp': now},
            {'video_id': 'video_3', 'actress_id': 'actress_1', 'role_type': '主演', 'timestamp': now},
            {'video_id': 'video_3', 'actress_id': 'actress_2', 'role_type': '配角', 'timestamp': now},
            {'video_id': 'video_4', 'actress_id': 'actress_2', 'role_type': '主演', 'timestamp': now},
        ]
        db._save_all_data(db.data)
        
        yield db
        
        # 清理
        shutil.rmtree(temp_dir)
    
    def test_basic_actress_statistics(self, db_manager):
        """測試基本女優統計查詢"""
        stats = db_manager.get_actress_statistics()
        
        # 驗證返回結果結構
        assert isinstance(stats, list)
        assert len(stats) == 3
        
        # 驗證結果包含必需欄位
        for stat in stats:
            assert 'actress_name' in stat
            assert 'video_count' in stat
            assert 'studios' in stat
            assert 'studio_codes' in stat
    
    def test_actress_statistics_sorting(self, db_manager):
        """測試女優統計結果按出演部數排序"""
        stats = db_manager.get_actress_statistics()
        
        # 山田美優應該排第一（3部）
        assert stats[0]['actress_name'] == '山田美優'
        assert stats[0]['video_count'] == 3
        
        # 佐藤愛應該排第二（2部）
        assert stats[1]['actress_name'] == '佐藤愛'
        assert stats[1]['video_count'] == 2
        
        # 鈴木花應該排第三（0部）
        assert stats[2]['actress_name'] == '鈴木花'
        assert stats[2]['video_count'] == 0
    
    def test_actress_statistics_studios(self, db_manager):
        """測試女優統計的片商資訊"""
        stats = db_manager.get_actress_statistics()
        
        # 山田美優的片商清單
        yamada_stats = next(s for s in stats if s['actress_name'] == '山田美優')
        assert set(yamada_stats['studios']) == {'S1', 'PREMIUM'}
        assert set(yamada_stats['studio_codes']) == {'SNIS', 'PGD'}
        
        # 佐藤愛的片商清單
        sato_stats = next(s for s in stats if s['actress_name'] == '佐藤愛')
        assert set(sato_stats['studios']) == {'PREMIUM', 'IDEA POCKET'}
        assert set(sato_stats['studio_codes']) == {'PGD', 'IPX'}


class TestStudioStatistics:
    """測試片商統計查詢 (T023)"""
    
    @pytest.fixture
    def db_manager(self):
        """建立臨時測試資料庫"""
        temp_dir = tempfile.mkdtemp()
        db = JSONDBManager(data_dir=temp_dir)
        
        now = datetime.now(timezone.utc).strftime(ISO_DATETIME_FORMAT)
        
        # 新增女優
        db.add_or_update_actress({'id': 'actress_1', 'name': '山田美優', 'video_count': 0})
        db.add_or_update_actress({'id': 'actress_2', 'name': '佐藤愛', 'video_count': 0})
        db.add_or_update_actress({'id': 'actress_3', 'name': '鈴木花', 'video_count': 0})
        
        # 新增影片
        db.add_or_update_video({
            'id': 'video_1',
            'title': 'S1 Video 1',
            'studio': 'S1',
            'studio_code': 'SNIS',
            'release_date': '2023-01-15',
            'actresses': ['actress_1']
        })
        db.add_or_update_video({
            'id': 'video_2',
            'title': 'S1 Video 2',
            'studio': 'S1',
            'studio_code': 'SNIS',
            'release_date': '2023-02-20',
            'actresses': ['actress_2']
        })
        db.add_or_update_video({
            'id': 'video_3',
            'title': 'S1 Video 3',
            'studio': 'S1',
            'studio_code': 'SSNI',
            'release_date': '2023-03-10',
            'actresses': ['actress_1', 'actress_2']
        })
        db.add_or_update_video({
            'id': 'video_4',
            'title': 'PREMIUM Video',
            'studio': 'PREMIUM',
            'studio_code': 'PGD',
            'release_date': '2023-04-05',
            'actresses': ['actress_3']
        })
        
        # 新增關聯
        db.data['links'] = [
            {'video_id': 'video_1', 'actress_id': 'actress_1', 'role_type': '主演', 'timestamp': now},
            {'video_id': 'video_2', 'actress_id': 'actress_2', 'role_type': '主演', 'timestamp': now},
            {'video_id': 'video_3', 'actress_id': 'actress_1', 'role_type': '主演', 'timestamp': now},
            {'video_id': 'video_3', 'actress_id': 'actress_2', 'role_type': '配角', 'timestamp': now},
            {'video_id': 'video_4', 'actress_id': 'actress_3', 'role_type': '主演', 'timestamp': now},
        ]
        db._save_all_data(db.data)
        
        yield db
        
        shutil.rmtree(temp_dir)
    
    def test_basic_studio_statistics(self, db_manager):
        """測試基本片商統計查詢"""
        stats = db_manager.get_studio_statistics()
        
        # 驗證返回結果結構
        assert isinstance(stats, list)
        assert len(stats) >= 2  # 至少有 S1 和 PREMIUM
        
        # 驗證結果包含必需欄位
        for stat in stats:
            assert 'studio' in stat
            assert 'studio_code' in stat
            assert 'video_count' in stat
            assert 'actress_count' in stat
    
    def test_studio_statistics_sorting(self, db_manager):
        """測試片商統計結果按影片數排序"""
        stats = db_manager.get_studio_statistics()
        
        # S1 應該排第一（2部或3部，視 studio_code 分組）
        # 驗證第一個片商是 S1
        assert stats[0]['studio'] == 'S1'
    
    def test_studio_statistics_counts(self, db_manager):
        """測試片商統計的計數正確性"""
        stats = db_manager.get_studio_statistics()
        
        # 找到 S1 片商（可能有多個 studio_code）
        s1_stats = [s for s in stats if s['studio'] == 'S1']
        total_s1_videos = sum(s['video_count'] for s in s1_stats)
        assert total_s1_videos == 3
        
        # 找到 PREMIUM 片商
        premium_stats = next((s for s in stats if s['studio'] == 'PREMIUM'), None)
        assert premium_stats is not None
        assert premium_stats['video_count'] == 1
        assert premium_stats['actress_count'] == 1


class TestEnhancedActressStudioStatistics:
    """測試增強版女優片商統計查詢 (T024)"""
    
    @pytest.fixture
    def db_manager(self):
        """建立臨時測試資料庫"""
        temp_dir = tempfile.mkdtemp()
        db = JSONDBManager(data_dir=temp_dir)
        
        now = datetime.now(timezone.utc).strftime(ISO_DATETIME_FORMAT)
        
        # 新增女優
        db.add_or_update_actress({'id': 'actress_1', 'name': '山田美優', 'video_count': 0})
        db.add_or_update_actress({'id': 'actress_2', 'name': '佐藤愛', 'video_count': 0})
        
        # 新增影片
        db.add_or_update_video({
            'id': 'video_1',
            'title': 'S1 Video 1',
            'studio': 'S1',
            'studio_code': 'SNIS',
            'release_date': '2023-01-15',
            'actresses': ['actress_1']
        })
        db.add_or_update_video({
            'id': 'video_2',
            'title': 'S1 Video 2',
            'studio': 'S1',
            'studio_code': 'SNIS',
            'release_date': '2023-02-20',
            'actresses': ['actress_1']
        })
        db.add_or_update_video({
            'id': 'video_3',
            'title': 'PREMIUM Video',
            'studio': 'PREMIUM',
            'studio_code': 'PGD',
            'release_date': '2023-03-10',
            'actresses': ['actress_1', 'actress_2']
        })
        
        # 新增關聯（包含不同角色類型）
        db.data['links'] = [
            {'video_id': 'video_1', 'actress_id': 'actress_1', 'role_type': '主演', 'timestamp': '2023-01-15T00:00:00Z'},
            {'video_id': 'video_2', 'actress_id': 'actress_1', 'role_type': '主演', 'timestamp': '2023-02-20T00:00:00Z'},
            {'video_id': 'video_3', 'actress_id': 'actress_1', 'role_type': '主演', 'timestamp': '2023-03-10T00:00:00Z'},
            {'video_id': 'video_3', 'actress_id': 'actress_2', 'role_type': '配角', 'timestamp': '2023-03-10T00:00:00Z'},
        ]
        db._save_all_data(db.data)
        
        yield db
        
        shutil.rmtree(temp_dir)
    
    def test_basic_enhanced_statistics(self, db_manager):
        """測試基本增強統計查詢"""
        stats = db_manager.get_enhanced_actress_studio_statistics()
        
        # 驗證返回結果結構
        assert isinstance(stats, list)
        assert len(stats) > 0
        
        # 驗證結果包含必需欄位
        for stat in stats:
            assert 'actress_name' in stat
            assert 'studio' in stat
            assert 'studio_code' in stat
            assert 'association_type' in stat
            assert 'video_count' in stat
            assert 'video_codes' in stat
            assert 'first_appearance' in stat
            assert 'latest_appearance' in stat
    
    def test_enhanced_statistics_with_filter(self, db_manager):
        """測試指定女優名稱的增強統計查詢"""
        stats = db_manager.get_enhanced_actress_studio_statistics(actress_name='山田美優')
        
        # 所有結果都應該是山田美優
        assert all(s['actress_name'] == '山田美優' for s in stats)
        
        # 山田美優應該有 S1 和 PREMIUM 的記錄
        studios = {s['studio'] for s in stats}
        assert 'S1' in studios
        assert 'PREMIUM' in studios
    
    def test_enhanced_statistics_role_types(self, db_manager):
        """測試增強統計中的角色類型分組"""
        stats = db_manager.get_enhanced_actress_studio_statistics()
        
        # 山田美優的 S1 主演應該有 2 部
        yamada_s1_main = next(
            (s for s in stats 
             if s['actress_name'] == '山田美優' 
             and s['studio'] == 'S1' 
             and s['association_type'] == '主演'),
            None
        )
        assert yamada_s1_main is not None
        assert yamada_s1_main['video_count'] == 2
        
        # 佐藤愛的 PREMIUM 配角應該有 1 部
        sato_premium_support = next(
            (s for s in stats 
             if s['actress_name'] == '佐藤愛' 
             and s['studio'] == 'PREMIUM' 
             and s['association_type'] == '配角'),
            None
        )
        assert sato_premium_support is not None
        assert sato_premium_support['video_count'] == 1
    
    def test_enhanced_statistics_video_codes(self, db_manager):
        """測試增強統計中的影片代碼清單"""
        stats = db_manager.get_enhanced_actress_studio_statistics(actress_name='山田美優')
        
        # 找到 S1 的記錄
        s1_record = next((s for s in stats if s['studio'] == 'S1'), None)
        assert s1_record is not None
        
        # 驗證影片代碼清單
        assert isinstance(s1_record['video_codes'], list)
        assert len(s1_record['video_codes']) == 2
        assert set(s1_record['video_codes']) == {'video_1', 'video_2'}
    
    def test_enhanced_statistics_date_range(self, db_manager):
        """測試增強統計中的日期範圍"""
        stats = db_manager.get_enhanced_actress_studio_statistics(actress_name='山田美優')
        
        # 找到 S1 的記錄
        s1_record = next((s for s in stats if s['studio'] == 'S1'), None)
        assert s1_record is not None
        
        # 驗證日期範圍
        assert s1_record['first_appearance'] == '2023-01-15T00:00:00Z'
        assert s1_record['latest_appearance'] == '2023-02-20T00:00:00Z'


class TestStatisticsPerformance:
    """測試統計查詢的效能"""
    
    @pytest.fixture
    def large_db_manager(self):
        """建立較大的測試資料庫"""
        temp_dir = tempfile.mkdtemp()
        db = JSONDBManager(data_dir=temp_dir)
        
        now = datetime.now(timezone.utc).strftime(ISO_DATETIME_FORMAT)
        
        # 建立 50 位女優
        for i in range(50):
            db.add_or_update_actress({
                'id': f'actress_{i}',
                'name': f'女優{i}',
                'video_count': 0
            })
        
        # 建立 200 部影片
        studios = ['S1', 'PREMIUM', 'IDEA POCKET', 'MOODYZ', 'E-BODY']
        for i in range(200):
            studio = studios[i % len(studios)]
            db.add_or_update_video({
                'id': f'video_{i}',
                'title': f'Video {i}',
                'studio': studio,
                'studio_code': f'{studio[:3]}{i:03d}',
                'release_date': '2023-01-01',
                'actresses': [f'actress_{i % 50}']
            })
        
        # 建立關聯
        links = []
        for i in range(200):
            links.append({
                'video_id': f'video_{i}',
                'actress_id': f'actress_{i % 50}',
                'role_type': '主演' if i % 3 == 0 else '配角',
                'timestamp': now
            })
        db.data['links'] = links
        db._save_all_data(db.data)
        
        yield db
        
        shutil.rmtree(temp_dir)
    
    def test_actress_statistics_performance(self, large_db_manager):
        """測試女優統計查詢效能"""
        import time
        
        start = time.time()
        stats = large_db_manager.get_actress_statistics()
        elapsed = time.time() - start
        
        # 驗證結果
        assert len(stats) == 50
        
        # 效能要求：應該在 1 秒內完成
        assert elapsed < 1.0, f"查詢時間過長: {elapsed:.3f}秒"
    
    def test_studio_statistics_performance(self, large_db_manager):
        """測試片商統計查詢效能"""
        import time
        
        start = time.time()
        stats = large_db_manager.get_studio_statistics()
        elapsed = time.time() - start
        
        # 驗證結果
        assert len(stats) >= 5
        
        # 效能要求：應該在 1 秒內完成
        assert elapsed < 1.0, f"查詢時間過長: {elapsed:.3f}秒"
    
    def test_enhanced_statistics_performance(self, large_db_manager):
        """測試增強統計查詢效能"""
        import time
        
        start = time.time()
        stats = large_db_manager.get_enhanced_actress_studio_statistics()
        elapsed = time.time() - start
        
        # 驗證結果
        assert len(stats) > 0
        
        # 效能要求：應該在 2 秒內完成
        assert elapsed < 2.0, f"查詢時間過長: {elapsed:.3f}秒"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
