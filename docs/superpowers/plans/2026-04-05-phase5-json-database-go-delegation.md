# Phase 5: JSONDBManager Go 完整委派 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delegate `JSONDBManager` video CRUD operations to Go CLI, reducing Python I/O from ~250ms per write to ~182μs by routing through `pkg/database`.

**Architecture:** Follow existing Phase 4 Adapter Pattern — add `_GO_DB_AVAILABLE` flag to `JSONDBManager`; each CRUD method first tries `go_api/db.py` functions (which call `classifier.exe db ...`), falls back to original Python logic on failure. Rename original Python implementations to `_*_python()` helpers.

**Tech Stack:** Go 1.24+, Python 3.11+, `pkg/database/jsondb.go`, `cmd/scanner/db_cmd.go`, `src/services/go_api/db.py`, `src/models/json_database.py`, `pytest`, `go test`

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `pkg/database/jsondb.go` | Modify | Add `GetAllVideos()` method returning `[]*VideoData` |
| `cmd/scanner/db_cmd.go` | Modify | Add `--full` flag to `db list` sub-command |
| `src/services/go_api/db.py` | Modify | Add `db_get_all_videos()` function |
| `src/models/json_database.py` | Modify | Add `_GO_DB_AVAILABLE` flag; delegate `get_video_info`, `add_or_update_video`, `delete_video`, `get_all_videos` |
| `tests/test_json_db_go_delegation.py` | Create | Unit + integration tests for all 4 delegated methods |

---

## Task 1: Add `GetAllVideos()` to Go `pkg/database` + `db list --full` CLI

**Files:**
- Modify: `pkg/database/jsondb.go`
- Modify: `cmd/scanner/db_cmd.go`

- [ ] **Step 1: Add `GetAllVideos()` to `pkg/database/jsondb.go`**

  Find the `ListVideos()` function. After it, add:

  ```go
  // GetAllVideos 返回所有影片的完整資料（含 journal 合併）
  func (db *JSONDatabase) GetAllVideos() ([]*VideoData, error) {
      db.mu.RLock()
      defer db.mu.RUnlock()
  
      if !db.loaded {
          return nil, ErrDatabaseNotLoaded
      }
  
      if err := db.mergeJournalLocked(); err != nil {
          return nil, fmt.Errorf("merge journal: %w", err)
      }
  
      videos := make([]*VideoData, 0, len(db.root.Videos))
      for _, v := range db.root.Videos {
          if v == nil {
              continue
          }
          copy := *v
          videos = append(videos, &copy)
      }
      return videos, nil
  }
  ```

  > **Note:** `mergeJournalLocked()` may not exist as-is. Check the existing method names in `jsondb.go` for merging journal before reading (e.g., `compactLocked`, `applyJournal`). Use the correct existing helper, or if journal is applied on `Load()`, skip the merge call and just iterate `db.root.Videos`.

- [ ] **Step 2: Run Go tests to ensure no regression**

  ```bash
  go test ./pkg/database/... -v
  ```

  Expected: all existing tests pass, no compile errors.

- [ ] **Step 3: Add `--full` flag to `db list` in `cmd/scanner/db_cmd.go`**

  Find the `case "list":` block. Replace it with:

  ```go
  case "list":
      fullFlag := fs.Bool("full", false, "返回完整影片物件陣列（預設只返回番號清單）")
      _ = fs.Parse(args[1:])
      if *fullFlag {
          videos, err := db.GetAllVideos()
          if err != nil {
              fmt.Fprintf(os.Stderr, "取得影片清單失敗: %v\n", err)
              os.Exit(1)
          }
          outputJSON(videos)
      } else {
          codes, err := db.ListVideos()
          if err != nil {
              fmt.Fprintf(os.Stderr, "列出影片番號失敗: %v\n", err)
              os.Exit(1)
          }
          outputJSON(codes)
      }
  ```

  > **Note:** The existing `case "list":` block may have a different structure. Adapt to match surrounding code style. Make sure `fs.Parse` is called before using `*fullFlag`.

- [ ] **Step 4: Rebuild `classifier.exe`**

  ```bash
  go build -o classifier.exe ./cmd/scanner
  ```

  Expected: exits 0 with no errors.

- [ ] **Step 5: Smoke-test the new CLI flag**

  ```bash
  ./classifier.exe db list -data-dir data/json_db
  ./classifier.exe db list --full -data-dir data/json_db
  ```

  First command: returns JSON array of code strings.
  Second command: returns JSON array of video objects (each has `"code"`, `"title"`, etc.).

- [ ] **Step 6: Commit**

  ```bash
  git add pkg/database/jsondb.go cmd/scanner/db_cmd.go classifier.exe
  git commit -m "feat(db): add GetAllVideos() to pkg/database and db list --full CLI flag"
  ```

---

## Task 2: Add `db_get_all_videos()` to `src/services/go_api/db.py`

**Files:**
- Modify: `src/services/go_api/db.py`

- [ ] **Step 1: Write the failing test first**

  Open `tests/test_json_db_go_delegation.py` (will be created). For now, add a placeholder test at the bottom of `tests/test_go_api_runner_injection.py` (or create a new file after Task 4).

  Actually, add the following standalone test to verify `db_get_all_videos` exists and calls the right command:

  ```python
  # tests/test_go_api_db_all_videos.py
  import pytest
  from unittest.mock import MagicMock
  import sys, os
  sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
  
  from services.go_api.db import db_get_all_videos
  from services.go_runner import GoCommandRunner, GoBridgeError
  
  def _make_runner(stdout: str) -> GoCommandRunner:
      r = MagicMock(spec=GoCommandRunner)
      result = MagicMock()
      result.stdout = stdout
      r.run.return_value = result
      r.parse_json.side_effect = lambda s: __import__('json').loads(s)
      return r
  
  def test_db_get_all_videos_returns_list():
      payload = '[{"code":"STARS-001","title":"Test"}]'
      runner = _make_runner(payload)
      result = db_get_all_videos(data_dir="data/json_db", runner=runner)
      assert isinstance(result, list)
      assert result[0]["code"] == "STARS-001"
      runner.run.assert_called_once_with(["db", "list", "--full", "-data-dir", "data/json_db"])
  
  def test_db_get_all_videos_default_data_dir():
      payload = '[]'
      runner = _make_runner(payload)
      db_get_all_videos(runner=runner)
      runner.run.assert_called_once_with(["db", "list", "--full"])
  
  def test_db_get_all_videos_returns_empty_on_error():
      runner = MagicMock(spec=GoCommandRunner)
      runner.run.side_effect = GoBridgeError("cli failed")
      result = db_get_all_videos(runner=runner)
      assert result == []
  ```

- [ ] **Step 2: Run test to verify it fails**

  ```bash
  python -m pytest tests/test_go_api_db_all_videos.py -v
  ```

  Expected: `ImportError` or `AttributeError: module has no attribute 'db_get_all_videos'`

- [ ] **Step 3: Add `db_get_all_videos()` to `src/services/go_api/db.py`**

  Append after the existing `db_compact_journal` function:

  ```python
  def db_get_all_videos(
      data_dir: str = "data/json_db",
      *,
      runner: GoCommandRunner | None = None,
  ) -> list[dict]:
      """取得所有影片的完整資訊列表。"""
      r = _get_runner(runner)
      try:
          cmd = ["db", "list", "--full"]
          if data_dir != "data/json_db":
              cmd.extend(["-data-dir", data_dir])
          result = r.run(cmd)
          data = r.parse_json(result.stdout)
          return data if isinstance(data, list) else []
      except GoBridgeError as e:
          logger.error(f"❌ Go CLI 執行失敗，取得所有影片失敗: {e}")
          return []
      except Exception as e:
          logger.error(f"❌ 取得所有影片失敗: {e}")
          return []
  ```

- [ ] **Step 4: Run tests to verify they pass**

  ```bash
  python -m pytest tests/test_go_api_db_all_videos.py -v
  ```

  Expected: 3 tests PASS.

- [ ] **Step 5: Run full test suite**

  ```bash
  python -m pytest tests/ -x --tb=short -q
  ```

  Expected: all pre-existing tests still pass (no regressions).

- [ ] **Step 6: Commit**

  ```bash
  git add src/services/go_api/db.py tests/test_go_api_db_all_videos.py
  git commit -m "feat(go_api): add db_get_all_videos() delegating to classifier.exe db list --full"
  ```

---

## Task 3: Delegate `get_video_info`, `add_or_update_video`, `delete_video` in `JSONDBManager`

**Files:**
- Modify: `src/models/json_database.py`

- [ ] **Step 1: Add module-level import guard near the top of `json_database.py`**

  Find the block of imports (after the `try: from utils.json_utils import load` block). Insert:

  ```python
  # Go API 委派 — 僅在 Go CLI 可用時啟用
  try:
      from services.go_api.db import (
          db_get_video,
          db_update_video,
          db_delete_video,
          db_get_all_videos,
      )
      _GO_DB_API_IMPORT_OK = True
  except ImportError:
      _GO_DB_API_IMPORT_OK = False
  ```

- [ ] **Step 2: Add `_check_go_db_available()` helper and `_GO_DB_AVAILABLE` instance flag**

  In `JSONDBManager.__init__`, after `self._ensure_data_file_exists()`, add:

  ```python
  self._GO_DB_AVAILABLE = self._check_go_db_available()
  ```

  After `__exit__` and before the CRUD section, add a new private method:

  ```python
  def _check_go_db_available(self) -> bool:
      """檢查 Go CLI 是否可用。"""
      if not _GO_DB_API_IMPORT_OK:
          return False
      try:
          from services.go_bridge import get_bridge
          return get_bridge().is_available
      except Exception:
          return False
  ```

- [ ] **Step 3: Rename Python implementations and add Go delegation for `get_video_info`**

  In `json_database.py`, rename `get_video_info` to `_get_video_info_python` and add a new public `get_video_info`:

  ```python
  def get_video_info(self, code: str) -> VideoDict | None:
      """查詢影片資訊（優先使用 Go，失敗時降級 Python）。"""
      if self._GO_DB_AVAILABLE:
          try:
              return db_get_video(code, data_dir=str(self.data_dir))
          except Exception as e:
              logger.warning(f"⚠️ Go DB get_video 失敗，降級 Python: {e}")
      return self._get_video_info_python(code)
  
  def _get_video_info_python(self, code: str) -> VideoDict | None:
      """[原始 Python 實作] 查詢影片資訊。"""
      try:
          self._acquire_read_lock()
          try:
              videos = self.data.get("videos", {})
              video = videos.get(code)
              if video:
                  logger.debug(f"✅ 查詢影片成功: {code}")
                  return video
              else:
                  logger.debug(f"⚠️ 影片不存在: {code}")
                  return None
          finally:
              self._release_locks()
      except LockError as e:
          logger.error(f"❌ 無法獲取讀鎖定: {e}")
          raise
      except Exception as e:
          logger.error(f"❌ 查詢影片失敗: {e}")
          raise
  ```

- [ ] **Step 4: Add Go delegation for `add_or_update_video`**

  Rename existing `add_or_update_video` to `_add_or_update_video_python`. Add new public method:

  ```python
  def add_or_update_video(
      self, code: str | VideoDict, info: dict[str, Any] | None = None
  ) -> str:
      """新增或更新影片（優先使用 Go，失敗時降級 Python）。"""
      # 解析 code 與 video_info（與原有邏輯相同）
      if isinstance(code, dict):
          if info is not None:
              raise ValidationError("傳入影片字典時不可同時提供 info")
          video_info = code.copy()
          video_code = video_info.get("code")
      else:
          if not isinstance(info, dict):
              raise ValidationError("影片資訊必須是字典")
          video_code = code
          video_info = info.copy()
  
      if not isinstance(video_code, str) or not video_code:
          raise ValidationError("影片番號必須存在")
  
      if self._GO_DB_AVAILABLE:
          try:
              video_dict = get_empty_video()
              video_dict["code"] = video_code
              video_dict.update(video_info)
              video_dict["updated_at"] = datetime.now(UTC).strftime(ISO_DATETIME_FORMAT)
              if db_update_video(video_code, video_dict, data_dir=str(self.data_dir)):
                  # 重新同步記憶體快取
                  self.data.setdefault("videos", {})[video_code] = video_dict
                  logger.info(f"✅ 影片已新增/更新（Go）: {video_code}")
                  return video_code
          except Exception as e:
              logger.warning(f"⚠️ Go DB add_or_update 失敗，降級 Python: {e}")
  
      return self._add_or_update_video_python(code, info)
  
  def _add_or_update_video_python(
      self, code: str | VideoDict, info: dict[str, Any] | None = None
  ) -> str:
      """[原始 Python 實作] 新增或更新影片。"""
      # ... [此處貼上原有 add_or_update_video 的完整實作，不做任何修改]
  ```

  > **IMPORTANT:** The `_add_or_update_video_python` body must be the **exact copy** of the original `add_or_update_video` body (lines ~792-845 of the original file). Do not summarize or omit any code.

- [ ] **Step 5: Add Go delegation for `delete_video`**

  Rename existing `delete_video` to `_delete_video_python`. Add new public method:

  ```python
  def delete_video(self, code: str) -> bool:
      """刪除影片（優先使用 Go，失敗時降級 Python）。"""
      if self._GO_DB_AVAILABLE:
          try:
              result = db_delete_video(code, data_dir=str(self.data_dir))
              if result:
                  # 同步記憶體快取並清理 links（Python 側邏輯）
                  videos = self.data.get("videos", {})
                  videos.pop(code, None)
                  links = self.data.get("links", [])
                  self.data["links"] = [
                      lnk for lnk in links if lnk.get("video_code") != code
                  ]
                  logger.info(f"✅ 影片已刪除（Go）: {code}")
                  return True
          except Exception as e:
              logger.warning(f"⚠️ Go DB delete 失敗，降級 Python: {e}")
  
      return self._delete_video_python(code)
  
  def _delete_video_python(self, code: str) -> bool:
      """[原始 Python 實作] 刪除影片。"""
      # ... [此處貼上原有 delete_video 的完整實作，不做任何修改]
  ```

  > **IMPORTANT:** The `_delete_video_python` body must be the **exact copy** of the original `delete_video` body (lines ~936-996). Do not summarize or omit any code.

- [ ] **Step 6: Run all Python tests**

  ```bash
  python -m pytest tests/ -x --tb=short -q
  ```

  Expected: all tests pass (same count as before this task).

- [ ] **Step 7: Commit**

  ```bash
  git add src/models/json_database.py
  git commit -m "refactor(json_db): delegate get_video_info/add_or_update_video/delete_video to Go with Python fallback"
  ```

---

## Task 4: Delegate `get_all_videos()` in `JSONDBManager` + comprehensive tests

**Files:**
- Modify: `src/models/json_database.py`
- Create: `tests/test_json_db_go_delegation.py`

- [ ] **Step 1: Write the failing tests first**

  Create `tests/test_json_db_go_delegation.py`:

  ```python
  """Tests for JSONDBManager Go delegation (Phase 5)."""
  import sys
  import os
  from unittest.mock import MagicMock, patch
  
  import pytest
  
  sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
  
  
  def _make_mock_runner(stdout: str):
      import json
      from services.go_runner import GoCommandRunner
      r = MagicMock(spec=GoCommandRunner)
      result = MagicMock()
      result.stdout = stdout
      r.run.return_value = result
      r.parse_json.side_effect = lambda s: json.loads(s)
      return r
  
  
  class TestGetVideoInfoDelegation:
      """get_video_info() Go 委派測試"""
  
      def test_delegates_to_go_when_available(self, tmp_path):
          from models.json_database import JSONDBManager
          db = JSONDBManager(str(tmp_path))
          db._GO_DB_AVAILABLE = True
          with patch('models.json_database.db_get_video', return_value={"code": "STARS-001"}) as mock:
              result = db.get_video_info("STARS-001")
          mock.assert_called_once_with("STARS-001", data_dir=str(tmp_path))
          assert result == {"code": "STARS-001"}
  
      def test_falls_back_to_python_when_go_unavailable(self, tmp_path):
          from models.json_database import JSONDBManager
          db = JSONDBManager(str(tmp_path))
          db._GO_DB_AVAILABLE = False
          db.data["videos"]["STARS-001"] = {"code": "STARS-001", "title": "Test"}
          result = db.get_video_info("STARS-001")
          assert result["code"] == "STARS-001"
  
      def test_falls_back_to_python_on_go_failure(self, tmp_path):
          from models.json_database import JSONDBManager
          from services.go_runner import GoBridgeError
          db = JSONDBManager(str(tmp_path))
          db._GO_DB_AVAILABLE = True
          db.data["videos"]["STARS-001"] = {"code": "STARS-001"}
          with patch('models.json_database.db_get_video', side_effect=GoBridgeError("fail")):
              result = db.get_video_info("STARS-001")
          assert result is not None
  
      def test_returns_none_for_missing_video(self, tmp_path):
          from models.json_database import JSONDBManager
          db = JSONDBManager(str(tmp_path))
          db._GO_DB_AVAILABLE = True
          with patch('models.json_database.db_get_video', return_value=None):
              result = db.get_video_info("NONEXISTENT")
          assert result is None
  
  
  class TestAddOrUpdateVideoDelegation:
      """add_or_update_video() Go 委派測試"""
  
      def test_delegates_to_go_when_available(self, tmp_path):
          from models.json_database import JSONDBManager
          db = JSONDBManager(str(tmp_path))
          db._GO_DB_AVAILABLE = True
          with patch('models.json_database.db_update_video', return_value=True) as mock:
              code = db.add_or_update_video("STARS-001", {"title": "Test"})
          assert code == "STARS-001"
          assert mock.called
  
      def test_updates_memory_cache_after_go_write(self, tmp_path):
          from models.json_database import JSONDBManager
          db = JSONDBManager(str(tmp_path))
          db._GO_DB_AVAILABLE = True
          with patch('models.json_database.db_update_video', return_value=True):
              db.add_or_update_video("STARS-001", {"title": "Test"})
          assert "STARS-001" in db.data["videos"]
  
      def test_falls_back_to_python_when_go_unavailable(self, tmp_path):
          from models.json_database import JSONDBManager
          db = JSONDBManager(str(tmp_path))
          db._GO_DB_AVAILABLE = False
          code = db.add_or_update_video("STARS-001", {"title": "Test"})
          assert code == "STARS-001"
          assert "STARS-001" in db.data.get("videos", {})
  
      def test_accepts_video_dict_as_first_arg(self, tmp_path):
          from models.json_database import JSONDBManager
          db = JSONDBManager(str(tmp_path))
          db._GO_DB_AVAILABLE = True
          with patch('models.json_database.db_update_video', return_value=True):
              code = db.add_or_update_video({"code": "STARS-002", "title": "Test 2"})
          assert code == "STARS-002"
  
  
  class TestDeleteVideoDelegation:
      """delete_video() Go 委派測試"""
  
      def test_delegates_to_go_when_available(self, tmp_path):
          from models.json_database import JSONDBManager
          db = JSONDBManager(str(tmp_path))
          db._GO_DB_AVAILABLE = True
          db.data["videos"]["STARS-001"] = {"code": "STARS-001"}
          with patch('models.json_database.db_delete_video', return_value=True) as mock:
              result = db.delete_video("STARS-001")
          assert result is True
          assert "STARS-001" not in db.data["videos"]
          mock.assert_called_once_with("STARS-001", data_dir=str(tmp_path))
  
      def test_cleans_up_links_after_go_delete(self, tmp_path):
          from models.json_database import JSONDBManager
          db = JSONDBManager(str(tmp_path))
          db._GO_DB_AVAILABLE = True
          db.data["videos"]["STARS-001"] = {"code": "STARS-001"}
          db.data["links"] = [
              {"video_code": "STARS-001", "actress_id": "A1"},
              {"video_code": "STARS-002", "actress_id": "A2"},
          ]
          with patch('models.json_database.db_delete_video', return_value=True):
              db.delete_video("STARS-001")
          remaining_links = db.data.get("links", [])
          assert all(lnk["video_code"] != "STARS-001" for lnk in remaining_links)
          assert len(remaining_links) == 1
  
      def test_falls_back_to_python_when_go_unavailable(self, tmp_path):
          from models.json_database import JSONDBManager
          db = JSONDBManager(str(tmp_path))
          db._GO_DB_AVAILABLE = False
          db._add_or_update_video_python("STARS-001", {"code": "STARS-001", "title": "T"})
          result = db.delete_video("STARS-001")
          assert result is True
  
  
  class TestGetAllVideosDelegation:
      """get_all_videos() Go 委派測試"""
  
      def test_delegates_to_go_when_available(self, tmp_path):
          from models.json_database import JSONDBManager
          db = JSONDBManager(str(tmp_path))
          db._GO_DB_AVAILABLE = True
          mock_videos = [{"code": "STARS-001"}, {"code": "STARS-002"}]
          with patch('models.json_database.db_get_all_videos', return_value=mock_videos) as mock:
              result = db.get_all_videos()
          mock.assert_called_once_with(data_dir=str(tmp_path))
          assert len(result) == 2
  
      def test_applies_filter_after_go_fetch(self, tmp_path):
          from models.json_database import JSONDBManager
          db = JSONDBManager(str(tmp_path))
          db._GO_DB_AVAILABLE = True
          mock_videos = [
              {"code": "STARS-001", "studio": "ABC"},
              {"code": "STARS-002", "studio": "XYZ"},
          ]
          with patch('models.json_database.db_get_all_videos', return_value=mock_videos):
              result = db.get_all_videos(filter_dict={"studio": "ABC"})
          assert len(result) == 1
          assert result[0]["code"] == "STARS-001"
  
      def test_falls_back_to_python_when_go_unavailable(self, tmp_path):
          from models.json_database import JSONDBManager
          db = JSONDBManager(str(tmp_path))
          db._GO_DB_AVAILABLE = False
          db.data["videos"]["STARS-001"] = {"code": "STARS-001"}
          result = db.get_all_videos()
          assert len(result) == 1
  
      def test_falls_back_to_python_on_go_failure(self, tmp_path):
          from models.json_database import JSONDBManager
          from services.go_runner import GoBridgeError
          db = JSONDBManager(str(tmp_path))
          db._GO_DB_AVAILABLE = True
          db.data["videos"]["STARS-001"] = {"code": "STARS-001"}
          with patch('models.json_database.db_get_all_videos', side_effect=Exception("fail")):
              result = db.get_all_videos()
          assert len(result) == 1
  ```

- [ ] **Step 2: Run tests to verify they fail**

  ```bash
  python -m pytest tests/test_json_db_go_delegation.py -v
  ```

  Expected: most fail with `AttributeError` (missing methods) or assertion errors.

- [ ] **Step 3: Add Go delegation for `get_all_videos()` in `json_database.py`**

  Rename existing `get_all_videos` to `_get_all_videos_python`. Add new public method:

  ```python
  def get_all_videos(
      self, filter_dict: dict[str, Any] | None = None
  ) -> list[VideoDict]:
      """取得所有影片清單（優先使用 Go，失敗時降級 Python）。"""
      if self._GO_DB_AVAILABLE:
          try:
              videos = db_get_all_videos(data_dir=str(self.data_dir))
              # 確保每個影片有 code 欄位（與 Python 實作一致）
              for v in videos:
                  if "code" not in v and "id" in v:
                      v["code"] = v["id"]
              if filter_dict:
                  videos = self._apply_video_filters(videos, filter_dict)
              logger.debug(f"✅ 取得 {len(videos)} 個影片（Go）")
              return videos
          except Exception as e:
              logger.warning(f"⚠️ Go DB get_all_videos 失敗，降級 Python: {e}")
      return self._get_all_videos_python(filter_dict)
  
  def _get_all_videos_python(
      self, filter_dict: dict[str, Any] | None = None
  ) -> list[VideoDict]:
      """[原始 Python 實作] 取得所有影片清單。"""
      # ... [此處貼上原有 get_all_videos 的完整實作，不做任何修改]
  ```

  > **IMPORTANT:** The `_get_all_videos_python` body must be the **exact copy** of the original `get_all_videos` body (lines ~885-934 of the original file).

- [ ] **Step 4: Run delegation tests**

  ```bash
  python -m pytest tests/test_json_db_go_delegation.py -v
  ```

  Expected: all 15 tests PASS.

- [ ] **Step 5: Run full test suite**

  ```bash
  python -m pytest tests/ -x --tb=short -q
  ```

  Expected: all pre-existing tests pass. Note total test count increase.

- [ ] **Step 6: Commit**

  ```bash
  git add src/models/json_database.py tests/test_json_db_go_delegation.py
  git commit -m "refactor(json_db): delegate get_all_videos to Go; add 15 delegation tests"
  ```

---

## Completion Checklist

After all tasks are done, verify:

- [ ] `go test ./pkg/database/... -v` — all pass
- [ ] `go build -o classifier.exe ./cmd/scanner` — exits 0
- [ ] `./classifier.exe db list --full -data-dir data/json_db` — returns JSON array of objects
- [ ] `python -m pytest tests/ -q` — all pass (count ≥ previous + 18)
- [ ] `python -m pytest tests/test_json_db_go_delegation.py -v` — 15 tests pass
- [ ] `python -m pytest tests/test_go_api_db_all_videos.py -v` — 3 tests pass

## Update MIGRATION_STATUS.md

After all tasks complete, update `MIGRATION_STATUS.md`:

```markdown
### Phase 5 — JSONDBManager Go 完整委派
- [x] Task 5-1: `pkg/database/jsondb.go` + `cmd/scanner/db_cmd.go` — `GetAllVideos()` + `db list --full`
- [x] Task 5-2: `src/services/go_api/db.py` — `db_get_all_videos()` added
- [x] Task 5-3: `src/models/json_database.py` — delegate `get_video_info`/`add_or_update_video`/`delete_video`
- [x] Task 5-4: `src/models/json_database.py` + `tests/test_json_db_go_delegation.py` — `get_all_videos` delegated + 15 tests
```
