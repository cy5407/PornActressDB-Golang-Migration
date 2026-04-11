"""
補充 json_database.py 覆蓋率測試

目標行：132-134, 147-148, 164-166, 182, 195, 218, 229, 258, 263-283,
        309-312, 324-331, 346, 352, 356, 378-385, 394, 417, 442, 454,
        470-472, 501, 505-508, 511, 528-534, 553-557, 577-579, 608,
        610-612, 631, 633, 638, 646-652, 667-671, 675-676, 704, 706-708,
        780, 812-865, 882, 911-934, 945-977
"""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import orjson
import pytest

from src.models.json_database import JSONDBManager
from src.models.json_types import (
    CorruptedDataError,
    DataIntegrityError,
    JSONDatabaseError,
    ValidationError,
    get_empty_json_database,
    get_empty_video,
)
from src.services.go_cli import GoError, GoNotFoundError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(tmp_path: Path) -> JSONDBManager:
    db_dir = str(tmp_path / "json_db")
    return JSONDBManager(db_dir)


# ---------------------------------------------------------------------------
# _load_data：exception 路徑（lines 132-134）
# ---------------------------------------------------------------------------

class TestLoadDataErrors:
    def test_non_corrupted_exception_wrapped(self, tmp_path):
        """_load_data_internal 拋出非 CorruptedDataError 時應包裝（lines 132-134）"""
        mgr = _make_manager(tmp_path)
        with patch.object(mgr, "_load_data_internal", side_effect=OSError("disk error")):
            with pytest.raises(CorruptedDataError, match="載入失敗"):
                mgr._load_all_data()

    def test_corrupted_data_error_reraises(self, tmp_path):
        """CorruptedDataError 應直接重拋（line 130-131）"""
        mgr = _make_manager(tmp_path)
        with patch.object(
            mgr, "_load_data_internal", side_effect=CorruptedDataError("bad")
        ):
            with pytest.raises(CorruptedDataError, match="bad"):
                mgr._load_all_data()


# ---------------------------------------------------------------------------
# _load_data_internal：各種邊界情況
# ---------------------------------------------------------------------------

class TestLoadDataInternal:
    def test_missing_data_file_creates_empty(self, tmp_path):
        """data.json 不存在時應呼叫 _ensure_data_file_exists（lines 147-148）"""
        db_dir = str(tmp_path / "json_db")
        os.makedirs(db_dir, exist_ok=True)
        mgr = JSONDBManager(db_dir)
        # data.json 應已被建立
        assert (Path(db_dir) / "data.json").exists()

    def test_corrupted_json_raises_error(self, tmp_path):
        """JSON 損壞時應拋出 JSONDatabaseError（lines 164-166）"""
        db_dir = str(tmp_path / "json_db")
        os.makedirs(db_dir, exist_ok=True)
        (Path(db_dir) / "data.json").write_bytes(b"NOT JSON!!!")
        with pytest.raises((CorruptedDataError, JSONDatabaseError)):
            JSONDBManager(db_dir)

    def test_corrupted_error_reraises_from_inner(self, tmp_path):
        """內層 CorruptedDataError 應直接重拋（line 182）"""
        db_dir = str(tmp_path / "json_db")
        os.makedirs(db_dir, exist_ok=True)
        mgr = JSONDBManager(db_dir)
        with patch.object(
            mgr, "_validate_json_format", side_effect=CorruptedDataError("inner")
        ):
            with pytest.raises(CorruptedDataError, match="inner"):
                mgr._load_data_internal()


# ---------------------------------------------------------------------------
# _normalize_loaded_data：各種驗證錯誤
# ---------------------------------------------------------------------------

class TestNormalizeLoadedData:
    def test_non_dict_root_raises(self, tmp_path):
        """根層非 dict 時應拋出 ValidationError（line 195）"""
        mgr = _make_manager(tmp_path)
        with pytest.raises(ValidationError, match="根層必須是字典"):
            mgr._normalize_loaded_data([1, 2, 3])

    def test_statistics_not_dict_uses_default(self, tmp_path):
        """statistics 欄位非 dict 時應換成預設值（line 218）"""
        mgr = _make_manager(tmp_path)
        data = get_empty_json_database()
        data["statistics"] = "invalid"
        result = mgr._normalize_loaded_data(data)
        assert isinstance(result["statistics"], dict)

    def test_non_dict_video_raises(self, tmp_path):
        """影片資料非 dict 時應拋出 ValidationError（line 229）"""
        mgr = _make_manager(tmp_path)
        with pytest.raises(ValidationError):
            mgr._normalize_loaded_video("not-a-dict", "X-001")


# ---------------------------------------------------------------------------
# _validate_json_format：遺失鍵 / schema 版本
# ---------------------------------------------------------------------------

class TestValidateJsonFormat:
    def test_missing_required_keys(self, tmp_path):
        """遺失必要鍵時應拋出 ValidationError（line 258+352）"""
        mgr = _make_manager(tmp_path)
        with pytest.raises(ValidationError, match="遺失必需鍵"):
            mgr._validate_json_format({"schema_version": "1.0"})

    def test_wrong_schema_version(self, tmp_path):
        """schema 版本不符時應拋出 ValidationError（line 356）"""
        mgr = _make_manager(tmp_path)
        data = get_empty_json_database()
        data["schema_version"] = "99.99"
        with pytest.raises(ValidationError, match="Schema 版本不符"):
            mgr._validate_json_format(data)


# ---------------------------------------------------------------------------
# _validate_referential_integrity：連結驗證
# ---------------------------------------------------------------------------

class TestValidateReferentialIntegrity:
    def test_link_with_missing_video_code(self, tmp_path):
        """連結中 video_code 不存在時應拋出 DataIntegrityError（lines 378-383）"""
        mgr = _make_manager(tmp_path)
        data = get_empty_json_database()
        data["links"] = [{"video_code": "MISSING-001", "actress_id": ""}]
        with pytest.raises(DataIntegrityError, match="video_code"):
            mgr._validate_referential_integrity(data)

    def test_link_with_missing_actress_id(self, tmp_path):
        """連結中 actress_id 不存在時應拋出 DataIntegrityError（lines 384-385）"""
        mgr = _make_manager(tmp_path)
        data = get_empty_json_database()
        data["videos"]["V-001"] = get_empty_video()
        data["links"] = [{"video_code": "V-001", "actress_id": "NO_ACTRESS"}]
        data["actresses"]["SOME_ACTRESS"] = {"id": "SOME_ACTRESS", "name": "A"}
        with pytest.raises(DataIntegrityError, match="actress_id"):
            mgr._validate_referential_integrity(data)

    def test_actresses_not_list_raises(self, tmp_path):
        """影片 actresses 非 list 時應拋出 DataIntegrityError（line 394）"""
        mgr = _make_manager(tmp_path)
        data = get_empty_json_database()
        video = get_empty_video()
        video["actresses"] = "not-a-list"
        data["videos"]["X-001"] = video
        with pytest.raises(DataIntegrityError, match="actresses 必須是列表"):
            mgr._validate_referential_integrity(data)


# ---------------------------------------------------------------------------
# backup 方法：Go 回傳失敗的錯誤路徑
# ---------------------------------------------------------------------------

class TestBackupErrors:
    def test_create_backup_go_returns_empty_raises(self, tmp_path):
        """Go backup-create 回傳空值時應拋出（line 417）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_backup_create", return_value={}
        ):
            with pytest.raises(RuntimeError, match="Go backup-create 回傳空結果"):
                mgr.create_backup()

    def test_restore_from_backup_go_returns_false(self, tmp_path):
        """Go backup-restore 回傳 False 時應拋出（line 442）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_backup_restore", return_value=False
        ):
            with pytest.raises(RuntimeError, match="Go backup-restore 回傳失敗"):
                mgr.restore_from_backup("/some/backup.json")

    def test_get_backup_list_go_returns_none_raises(self, tmp_path):
        """Go backup-list 回傳 None 時應拋出（line 454）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_backup_list", return_value=None
        ):
            with pytest.raises(RuntimeError, match="Go backup-list 回傳空結果"):
                mgr.get_backup_list()

    def test_cleanup_old_backups_defaults(self, tmp_path):
        """cleanup_old_backups 使用預設值（lines 470-472）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_backup_cleanup", return_value=0
        ) as mock:
            result = mgr.cleanup_old_backups()
        assert result == 0
        # 應使用類別預設值
        call_kwargs = mock.call_args[1]
        assert call_kwargs["days"] == JSONDBManager.DEFAULT_BACKUP_DAYS
        assert call_kwargs["max_count"] == JSONDBManager.DEFAULT_BACKUP_MAX_COUNT


# ---------------------------------------------------------------------------
# add_or_update_video：各種驗證與錯誤路徑
# ---------------------------------------------------------------------------

class TestAddOrUpdateVideoErrors:
    def test_dict_with_extra_info_raises(self, tmp_path):
        """傳入 dict 同時又傳 info 時應拋出 ValidationError（line 501）"""
        mgr = _make_manager(tmp_path)
        with pytest.raises(ValidationError, match="不可同時提供 info"):
            mgr.add_or_update_video({"code": "X-001"}, info={"title": "t"})

    def test_info_not_dict_raises(self, tmp_path):
        """info 非 dict 時應拋出 ValidationError（lines 505-506）"""
        mgr = _make_manager(tmp_path)
        with pytest.raises(ValidationError, match="必須是字典"):
            mgr.add_or_update_video("X-001", info="invalid")

    def test_empty_code_raises(self, tmp_path):
        """番號為空時應拋出 ValidationError（line 511）"""
        mgr = _make_manager(tmp_path)
        with pytest.raises(ValidationError, match="番號必須存在"):
            mgr.add_or_update_video("", info={"title": "t"})

    def test_go_returns_false_raises_runtime(self, tmp_path):
        """Go CLI 回傳 False 時應拋出 RuntimeError（lines 528-534）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_update_video", return_value=False
        ):
            with pytest.raises(RuntimeError, match="Go db_update_video 回傳失敗"):
                mgr.add_or_update_video("X-001", info={"title": "t"})

    def test_unexpected_exception_wrapped(self, tmp_path):
        """非 ValidationError 例外應包裝成 RuntimeError（lines 533-534）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_update_video",
            side_effect=ConnectionError("network"),
        ):
            with pytest.raises(RuntimeError, match="Go 委派 add_or_update_video 失敗"):
                mgr.add_or_update_video("X-001", info={"title": "t"})


# ---------------------------------------------------------------------------
# get_video_info：GoError 路徑（lines 553-557）
# ---------------------------------------------------------------------------

class TestGetVideoInfoErrors:
    def test_not_found_error_returns_none(self, tmp_path):
        """GoNotFoundError 應回傳 None（lines 553-554）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_get_video",
            side_effect=GoNotFoundError("not found"),
        ):
            result = mgr.get_video_info("MISSING-001")
        assert result is None

    def test_go_error_raises_runtime(self, tmp_path):
        """GoError 應拋出 RuntimeError（lines 556-557）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_get_video",
            side_effect=GoError("go cli error"),
        ):
            with pytest.raises(RuntimeError):
                mgr.get_video_info("X-001")


# ---------------------------------------------------------------------------
# delete_video：warning 與 exception 路徑（lines 608, 610-612）
# ---------------------------------------------------------------------------

class TestDeleteVideoErrors:
    def test_go_returns_false_returns_false(self, tmp_path):
        """Go delete_video 回傳 False 時應回傳 False 並 log warning（line 608）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_delete_video", return_value=False
        ):
            result = mgr.delete_video("X-001")
        assert result is False

    def test_exception_raises_runtime(self, tmp_path):
        """例外應包裝成 RuntimeError（lines 610-612）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_delete_video",
            side_effect=IOError("io error"),
        ):
            with pytest.raises(RuntimeError, match="Go delete_video 失敗"):
                mgr.delete_video("X-001")


# ---------------------------------------------------------------------------
# add_or_update_actress：驗證錯誤（lines 631, 633, 638）
# ---------------------------------------------------------------------------

class TestAddOrUpdateActressErrors:
    def test_non_dict_raises(self, tmp_path):
        """非 dict 參數應拋出 ValidationError（line 631）"""
        mgr = _make_manager(tmp_path)
        with pytest.raises(ValidationError, match="必須是字典"):
            mgr.add_or_update_actress("not-a-dict")

    def test_missing_id_raises(self, tmp_path):
        """缺少 id 鍵時應拋出 ValidationError（line 633）"""
        mgr = _make_manager(tmp_path)
        with pytest.raises(ValidationError, match="ID 必須存在"):
            mgr.add_or_update_actress({"name": "女優A"})

    def test_empty_id_raises(self, tmp_path):
        """id 為空字串時應拋出 ValidationError（line 638）"""
        mgr = _make_manager(tmp_path)
        with pytest.raises(ValidationError, match="ID 不得為空"):
            mgr.add_or_update_actress({"id": ""})

    def test_go_exception_wrapped(self, tmp_path):
        """Go 例外應包裝成 RuntimeError（lines 646-650）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_update_actress",
            side_effect=RuntimeError("go error"),
        ):
            with pytest.raises(RuntimeError, match="Go add_or_update_actress 失敗"):
                mgr.add_or_update_actress({"id": "actress-1", "name": "A"})

    def test_go_returns_false_raises(self, tmp_path):
        """Go 回傳 False 時應拋出 RuntimeError（line 652）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_update_actress", return_value=False
        ):
            with pytest.raises(RuntimeError, match="Go db_update_actress 回傳失敗"):
                mgr.add_or_update_actress({"id": "actress-1", "name": "A"})


# ---------------------------------------------------------------------------
# get_actress_info：Go error 路徑（lines 667-671, 675-676）
# ---------------------------------------------------------------------------

class TestGetActressInfoErrors:
    def test_not_found_returns_none(self, tmp_path):
        """GoNotFoundError 應回傳 None（lines 667-670）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_get_actress",
            side_effect=GoNotFoundError("not found"),
        ):
            result = mgr.get_actress_info("no-actress")
        assert result is None

    def test_go_error_raises_runtime(self, tmp_path):
        """GoError 應拋出 RuntimeError（lines 675-676）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_get_actress",
            side_effect=GoError("go error"),
        ):
            with pytest.raises(RuntimeError):
                mgr.get_actress_info("actress-1")


# ---------------------------------------------------------------------------
# delete_actress：warning 與 exception 路徑（lines 704, 706-708）
# ---------------------------------------------------------------------------

class TestDeleteActressErrors:
    def test_go_returns_false_returns_false(self, tmp_path):
        """Go 回傳 False 時應回傳 False（line 704）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_delete_actress", return_value=False
        ):
            result = mgr.delete_actress("actress-1")
        assert result is False

    def test_exception_raises_runtime(self, tmp_path):
        """例外應包裝成 RuntimeError（lines 706-708）"""
        mgr = _make_manager(tmp_path)
        with patch(
            "src.models.json_database._go_db_delete_actress",
            side_effect=IOError("io error"),
        ):
            with pytest.raises(RuntimeError, match="Go delete_actress 失敗"):
                mgr.delete_actress("actress-1")


# ---------------------------------------------------------------------------
# analyze_actress_primary_studio：各種分類路徑
# ---------------------------------------------------------------------------

def _add_video(mgr: JSONDBManager, code: str, studio: str, actresses: list[str]):
    """直接寫入 in-memory data，不走 Go CLI"""
    video = get_empty_video()
    video["code"] = code
    video["studio"] = studio
    video["actresses"] = actresses
    mgr.data["videos"][code] = video


class TestAnalyzeActressPrimaryStudio:
    def test_no_data_returns_unknown(self, tmp_path):
        """女優無影片時應回傳 UNKNOWN（line 780）"""
        mgr = _make_manager(tmp_path)
        result = mgr.analyze_actress_primary_studio("無資料女優")
        assert result["primary_studio"] == "UNKNOWN"
        assert result["classification_type"] == "no_data"

    def test_exclusive_actress_single_studio(self, tmp_path):
        """單一片商 >= 3 部 → exclusive 分類"""
        mgr = _make_manager(tmp_path)
        for i in range(4):
            _add_video(mgr, f"SONE-{i:03d}", "S1 No.1 Style", ["女優B"])
        result = mgr.analyze_actress_primary_studio("女優B")
        assert result["classification_type"] == "exclusive"
        assert result["primary_studio"] == "S1 No.1 Style"

    def test_exclusive_actress_with_major_studio_flag(self, tmp_path):
        """單一大片商 → recommendation='studio_classification'"""
        mgr = _make_manager(tmp_path)
        for i in range(3):
            _add_video(mgr, f"IPX-{i:03d}", "Idea Pocket", ["女優C"])
        result = mgr.analyze_actress_primary_studio("女優C", major_studios={"Idea Pocket"})
        assert result["recommendation"] == "studio_classification"

    def test_multi_studio_actress(self, tmp_path):
        """5+ 片商 → multi_studio 分類（lines 812-839）"""
        mgr = _make_manager(tmp_path)
        studios = ["Studio1", "Studio2", "Studio3", "Studio4", "Studio5"]
        for i, s in enumerate(studios):
            _add_video(mgr, f"XX-{i:03d}", s, ["多片商女優"])
        result = mgr.analyze_actress_primary_studio("多片商女優")
        assert result["classification_type"] == "multi_studio"

    def test_high_loyalty_studio(self, tmp_path):
        """大片商佔 70%+ 且 >= 5 部 → high_loyalty（lines 882, 911-933）"""
        mgr = _make_manager(tmp_path)
        # 主要片商 7 部 + 另一片商 2 部 → 7/9 ≈ 78%
        for i in range(7):
            _add_video(mgr, f"STARS-{i:03d}", "SOD Create", ["忠誠女優"])
        for i in range(2):
            _add_video(mgr, f"OTHER-{i:03d}", "OtherStudio", ["忠誠女優"])
        result = mgr.analyze_actress_primary_studio("忠誠女優", major_studios={"SOD Create"})
        assert result["classification_type"] == "high_loyalty"
        assert result["primary_studio"] == "SOD Create"

    def test_standard_classification_with_major_studio(self, tmp_path):
        """兩個片商但有大片商主導 → studio_classification（lines 841-862, 945-977）"""
        mgr = _make_manager(tmp_path)
        # 大片商 4 部 + 小片商 1 部 → best_major_studio == best_studio
        for i in range(4):
            _add_video(mgr, f"BIG-{i:03d}", "BigStudio", ["標準女優"])
        _add_video(mgr, "SMALL-001", "SmallStudio", ["標準女優"])
        result = mgr.analyze_actress_primary_studio("標準女優", major_studios={"BigStudio"})
        assert result["primary_studio"] in {"BigStudio", "SmallStudio"}

    def test_determine_standard_no_major_studios(self, tmp_path):
        """無 major_studios 時 _determine_standard_classification 應直接回傳（line 953）"""
        mgr = _make_manager(tmp_path)
        for i in range(2):
            _add_video(mgr, f"A-{i:03d}", "StudioA", ["兩廠女優"])
        _add_video(mgr, "B-001", "StudioB", ["兩廠女優"])
        result = mgr.analyze_actress_primary_studio("兩廠女優", major_studios=None)
        assert result["primary_studio"] in {"StudioA", "StudioB"}
