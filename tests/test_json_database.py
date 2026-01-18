"""
測試 JSON 資料庫核心模組（基礎功能）
"""

import tempfile
from pathlib import Path

import pytest

from src.models.json_database import JSONDBManager
from src.models.json_types import VideoDict


class TestJSONDatabase:
    """測試 JSON 資料庫管理器"""

    @pytest.fixture
    def temp_db_dir(self):
        """建立臨時資料庫目錄"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def db_manager(self, temp_db_dir):
        """建立資料庫管理器實例"""
        return JSONDBManager(temp_db_dir)

    def test_create_database(self, db_manager):
        """測試建立資料庫"""
        assert db_manager is not None
        assert db_manager.db_dir is not None

    def test_add_video(self, db_manager):
        """測試新增影片"""
        video_data: VideoDict = {
            "code": "TEST-001",
            "title": "測試影片",
            "studio": "測試片商",
            "release_date": "2024-01-01",
            "url": "https://example.com",
            "actresses": ["女優A", "女優B"],
            "search_status": "success",
            "last_search_date": "2024-01-01",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "metadata": {"source": "test", "confidence": 1.0},
        }

        db_manager.add_or_update_video(video_data)
        result = db_manager.get_video_info("TEST-001")

        assert result is not None
        assert result["code"] == "TEST-001"
        assert result["title"] == "測試影片"
        assert len(result["actresses"]) == 2

    def test_get_nonexistent_video(self, db_manager):
        """測試取得不存在的影片"""
        result = db_manager.get_video_info("NONEXISTENT-999")
        assert result is None

    def test_get_all_videos(self, db_manager):
        """測試取得所有影片"""
        # 新增幾部測試影片
        for i in range(3):
            video_data: VideoDict = {
                "code": f"TEST-{i:03d}",
                "title": f"測試影片 {i}",
                "studio": "測試片商",
                "release_date": "2024-01-01",
                "url": "",
                "actresses": [],
                "search_status": "success",
                "last_search_date": "2024-01-01",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "metadata": {"source": "test", "confidence": 1.0},
            }
            db_manager.add_or_update_video(video_data)

        all_videos = db_manager.get_all_videos()
        assert len(all_videos) >= 3

    def test_update_existing_video(self, db_manager):
        """測試更新現有影片"""
        # 先新增
        video_data: VideoDict = {
            "code": "TEST-UPDATE",
            "title": "原始標題",
            "studio": "測試片商",
            "release_date": "2024-01-01",
            "url": "",
            "actresses": [],
            "search_status": "success",
            "last_search_date": "2024-01-01",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "metadata": {"source": "test", "confidence": 1.0},
        }
        db_manager.add_or_update_video(video_data)

        # 更新
        updated_data: VideoDict = video_data.copy()
        updated_data["title"] = "更新後的標題"
        db_manager.add_or_update_video(updated_data)

        result = db_manager.get_video_info("TEST-UPDATE")
        assert result["title"] == "更新後的標題"

    def test_delete_video(self, db_manager):
        """測試刪除影片"""
        # 先新增
        video_data: VideoDict = {
            "code": "TEST-DELETE",
            "title": "要刪除的影片",
            "studio": "測試片商",
            "release_date": "2024-01-01",
            "url": "",
            "actresses": [],
            "search_status": "success",
            "last_search_date": "2024-01-01",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "metadata": {"source": "test", "confidence": 1.0},
        }
        db_manager.add_or_update_video(video_data)

        # 確認存在
        assert db_manager.get_video_info("TEST-DELETE") is not None

        # 刪除
        db_manager.delete_video("TEST-DELETE")

        # 確認已刪除
        assert db_manager.get_video_info("TEST-DELETE") is None

    def test_batch_add_videos(self, db_manager):
        """測試批次新增影片"""
        videos = []
        for i in range(5):
            video_data: VideoDict = {
                "code": f"BATCH-{i:03d}",
                "title": f"批次影片 {i}",
                "studio": "測試片商",
                "release_date": "2024-01-01",
                "url": "",
                "actresses": [],
                "search_status": "success",
                "last_search_date": "2024-01-01",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "metadata": {"source": "test", "confidence": 1.0},
            }
            videos.append(video_data)
            db_manager.add_or_update_video(video_data)

        # 驗證全部新增成功
        for i in range(5):
            assert db_manager.get_video_info(f"BATCH-{i:03d}") is not None
