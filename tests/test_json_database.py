"""
測試 JSON 資料庫核心模組（基礎功能）
"""

import json
from pathlib import Path

import pytest

from src.models.json_database import JSONDBManager
from src.models.json_types import JSONDatabaseError, VideoDict, get_empty_json_database


class TestJSONDatabase:
    """測試 JSON 資料庫管理器"""

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

    def test_restore_from_backup_uses_backup_file_keyword(self, db_manager, monkeypatch):
        """還原備份應傳遞 backup_file 參數給 Go CLI 包裝層"""
        captured = {}

        def fake_restore(*, backup_file, data_dir):
            captured["backup_file"] = backup_file
            captured["data_dir"] = data_dir
            return {"success": True}

        monkeypatch.setattr(
            "src.models.json_database._go_db_backup_restore",
            fake_restore,
        )

        assert db_manager.restore_from_backup("demo-backup.json") is True
        assert captured["backup_file"] == "demo-backup.json"
        assert Path(captured["data_dir"]) == Path(db_manager.data_dir)

    def test_create_backup_returns_backup_path(self, db_manager, monkeypatch):
        monkeypatch.setattr(
            "src.models.json_database._go_db_backup_create",
            lambda **_kwargs: {"success": True, "path": "backup/demo.json"},
        )

        assert db_manager.create_backup() == "backup/demo.json"

    def test_get_backup_list_returns_backups_array(self, db_manager, monkeypatch):
        monkeypatch.setattr(
            "src.models.json_database._go_db_backup_list",
            lambda **_kwargs: ["backup/a.json", "backup/b.json"],
        )

        assert db_manager.get_backup_list() == ["backup/a.json", "backup/b.json"]

    def test_cleanup_old_backups_returns_deleted_count(self, db_manager, monkeypatch):
        monkeypatch.setattr(
            "src.models.json_database._go_db_backup_cleanup",
            lambda **_kwargs: 4,
        )

        assert db_manager.cleanup_old_backups(days=5, max_count=8) == 4

    def test_legacy_video_actress_links_is_rejected(self, temp_db_dir):
        payload = get_empty_json_database()
        payload["video_actress_links"] = {"TEST-001": ["actress-1"]}
        data_file = Path(temp_db_dir) / "data.json"
        data_file.parent.mkdir(parents=True, exist_ok=True)
        data_file.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(JSONDatabaseError, match="video_actress_links"):
            JSONDBManager(temp_db_dir)

    def test_dict_links_is_rejected(self, temp_db_dir):
        payload = get_empty_json_database()
        payload["links"] = {"TEST-001": ["actress-1"]}
        data_file = Path(temp_db_dir) / "data.json"
        data_file.parent.mkdir(parents=True, exist_ok=True)
        data_file.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(JSONDatabaseError, match="'links' 必須是清單"):
            JSONDBManager(temp_db_dir)

    def test_analyze_primary_studio_counts_all_json_db_entries_as_primary(
        self, db_manager
    ):
        actress_name = "測試女優"
        for index in range(3):
            db_manager.add_or_update_video(
                {
                    "code": f"SAME-{index:03d}",
                    "title": f"測試影片 {index}",
                    "studio": "S1",
                    "studio_code": "S1",
                    "release_date": "2024-01-01",
                    "url": "",
                    "actresses": [actress_name],
                    "search_status": "success",
                    "last_search_date": "2024-01-01",
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "metadata": {"source": "test", "confidence": 1.0},
                }
            )

        analysis = db_manager.analyze_actress_primary_studio(actress_name)

        assert analysis["classification_type"] == "exclusive"
        assert analysis["total_videos"] == 3
        assert analysis["studio_distribution"]["S1"]["total_count"] == 3
        assert analysis["studio_distribution"]["S1"]["primary_count"] == 3
        assert analysis["studio_distribution"]["S1"]["collaboration_count"] == 0
