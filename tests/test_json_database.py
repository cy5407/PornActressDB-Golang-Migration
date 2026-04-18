"""
測試 JSON 資料庫核心模組（基礎功能）
"""

import json
from pathlib import Path

import pytest

import src.models.json_database as json_database
from src.models.json_database import JSONDBManager
from src.models.json_types import (
    JSONDatabaseError,
    VideoDict,
    get_empty_json_database,
    get_empty_video,
)


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

    def test_get_empty_video_includes_source_specific_search_fields(self):
        """新 schema 應預留來源別女優搜尋欄位"""
        video = get_empty_video()

        assert video["avwiki_actress_status"] == ""
        assert video["avwiki_last_search_date"] == ""
        assert video["javdb_actress_status"] == ""
        assert video["javdb_last_search_date"] == ""

    def test_load_normalizes_missing_source_specific_search_fields(self, temp_db_dir):
        """載入舊資料時應補齊來源別女優搜尋欄位"""
        payload = get_empty_json_database()
        payload["videos"]["TEST-LEGACY"] = {
            "code": "TEST-LEGACY",
            "title": "舊資料",
            "studio": "",
            "release_date": "",
            "url": "",
            "actresses": [],
            "search_status": "success",
            "search_method": "AV-WIKI",
            "last_search_date": "2024-01-01",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "metadata": {"source": "test", "confidence": 1.0},
        }
        data_file = Path(temp_db_dir) / "data.json"
        data_file.parent.mkdir(parents=True, exist_ok=True)
        data_file.write_text(json.dumps(payload), encoding="utf-8")

        manager = JSONDBManager(temp_db_dir)

        loaded = manager.data["videos"]["TEST-LEGACY"]
        assert loaded["search_status"] == "success"
        assert loaded["search_method"] == "AV-WIKI"
        assert loaded["avwiki_actress_status"] == ""
        assert loaded["avwiki_last_search_date"] == ""
        assert loaded["javdb_actress_status"] == ""
        assert loaded["javdb_last_search_date"] == ""

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

    def test_create_backup_raises_runtime_on_go_error(self, db_manager, monkeypatch):
        monkeypatch.setattr(
            "src.models.json_database._go_db_backup_create",
            lambda **_kwargs: (_ for _ in ()).throw(json_database._GoBridgeError("backup failed")),
        )

        with pytest.raises(RuntimeError, match="Go backup-create 失敗"):
            db_manager.create_backup()

    def test_get_backup_list_raises_runtime_on_go_error(self, db_manager, monkeypatch):
        monkeypatch.setattr(
            "src.models.json_database._go_db_backup_list",
            lambda **_kwargs: (_ for _ in ()).throw(json_database._GoBridgeError("list failed")),
        )

        with pytest.raises(RuntimeError, match="Go backup-list 失敗"):
            db_manager.get_backup_list()

    def test_cleanup_old_backups_raises_runtime_on_go_error(self, db_manager, monkeypatch):
        monkeypatch.setattr(
            "src.models.json_database._go_db_backup_cleanup",
            lambda **_kwargs: (_ for _ in ()).throw(json_database._GoBridgeError("cleanup failed")),
        )

        with pytest.raises(RuntimeError, match="Go backup-cleanup 失敗"):
            db_manager.cleanup_old_backups(days=5, max_count=8)

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

    def test_add_or_update_actress_updates_memory_cache(self, db_manager, monkeypatch):
        captured = {}
        actress = {"id": "actress-001", "name": "測試女優", "aliases": ["別名"]}

        def fake_update_actress(actress_id, actress_info, data_dir):
            captured["actress_id"] = actress_id
            captured["actress_info"] = actress_info
            captured["data_dir"] = data_dir
            return True

        monkeypatch.setattr(
            "src.models.json_database._go_db_update_actress",
            fake_update_actress,
        )

        result = db_manager.add_or_update_actress(actress)

        assert result == "actress-001"
        assert captured["actress_id"] == "actress-001"
        assert captured["actress_info"] == actress
        assert Path(captured["data_dir"]) == Path(db_manager.data_dir)
        assert db_manager.data["actresses"]["actress-001"] == actress

    def test_get_actress_info_returns_none_for_not_found(self, db_manager, monkeypatch):
        monkeypatch.setattr(
            "src.models.json_database._go_db_get_actress",
            lambda actress_id, data_dir: (_ for _ in ()).throw(
                json_database._GoBridgeNotFoundError("not found")
            ),
        )

        assert db_manager.get_actress_info("missing-actress") is None

    def test_delete_actress_removes_cache_and_links(self, db_manager, monkeypatch):
        db_manager.data["actresses"]["actress-001"] = {"id": "actress-001", "name": "測試女優"}
        db_manager.data["links"] = [
            {"video_code": "TEST-001", "actress_id": "actress-001"},
            {"video_code": "TEST-002", "actress_id": "actress-999"},
        ]
        monkeypatch.setattr(
            "src.models.json_database._go_db_delete_actress",
            lambda actress_id, data_dir: True,
        )

        result = db_manager.delete_actress("actress-001")

        assert result is True
        assert "actress-001" not in db_manager.data["actresses"]
        assert db_manager.data["links"] == [
            {"video_code": "TEST-002", "actress_id": "actress-999"}
        ]

    def test_apply_video_filters_supports_studio_and_date_bounds(self):
        videos = [
            {"code": "A", "studio": "S1", "release_date": "2024-01-01"},
            {"code": "B", "studio": "S1", "release_date": "2024-03-01"},
            {"code": "C", "studio": "S2", "release_date": "2024-02-01"},
        ]

        filtered = JSONDBManager._apply_video_filters(
            videos,
            {
                "studio": "S1",
                "release_date_after": "2024-02-01",
                "release_date_before": "2024-03-31",
            },
        )

        assert filtered == [{"code": "B", "studio": "S1", "release_date": "2024-03-01"}]

    def test_empty_data_file_initializes_empty_database(self, temp_db_dir):
        data_file = Path(temp_db_dir) / "data.json"
        data_file.parent.mkdir(parents=True, exist_ok=True)
        data_file.write_text("", encoding="utf-8")

        manager = JSONDBManager(temp_db_dir)

        assert manager.data["videos"] == {}
        assert manager.data["actresses"] == {}
        assert manager.data["links"] == []
