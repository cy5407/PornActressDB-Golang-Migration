from src.models.incremental_json_database import IncrementalJSONDB
from src.models.json_database import JSONDBManager


def test_incremental_db_update_and_compact_persist_to_temp_db(
    temp_db_dir, seeded_db_manager
):
    db = IncrementalJSONDB(temp_db_dir)

    db.update_video("TEST-001", {"title": "更新後標題", "studio": "更新後片商"})

    updated = db.get_video_info("TEST-001")
    assert updated is not None
    assert updated["title"] == "更新後標題"
    assert updated["studio"] == "更新後片商"

    db.compact()

    reloaded = JSONDBManager(temp_db_dir)
    persisted = reloaded.get_video_info("TEST-001")
    assert persisted is not None
    assert persisted["title"] == "更新後標題"
    assert persisted["studio"] == "更新後片商"


def test_incremental_db_add_and_delete_video_use_temp_db(temp_db_dir, sample_video):
    db = IncrementalJSONDB(temp_db_dir)
    new_video = dict(sample_video)
    new_video["code"] = "TEST-DELETE"
    new_video["title"] = "待刪除影片"

    db.add_video(new_video)
    assert db.get_video_info("TEST-DELETE") is not None

    db.delete_video("TEST-DELETE")
    assert db.get_video_info("TEST-DELETE") is None


def test_incremental_db_missing_video_raises_json_error(temp_db_dir):
    db = IncrementalJSONDB(temp_db_dir)

    try:
        db.update_video("MISSING-001", {"title": "不存在"})
        raise AssertionError("預期 update_video 應拋出例外")
    except Exception as exc:
        assert "影片不存在" in str(exc)
