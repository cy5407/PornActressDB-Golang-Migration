# Phase 4 — CacheManager & IncrementalJSONDB Go Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `src/scrapers/cache_manager.py` and `src/models/incremental_json_database.py` to Go core, reducing both Python files to thin adapter layers that delegate all logic to existing Go packages.

**Architecture:** `pkg/cache/cache.go` is extended with `Get`/`Set`/`Delete` core operations and exposed via `classifier.exe cache` CLI. `pkg/database/jsondb.go` is already complete; `incremental_json_database.py` is refactored to delegate all read/write to `go_api/db.py`. Both Python files retain their public interface for backward compatibility but contain no business logic.

**Tech Stack:** Go 1.25+, Python 3.11+, `pkg/cache`, `pkg/database`, `src/services/go_api/db.py`, `classifier.exe` CLI, `pytest`, `go test`

---

## File Structure

### Phase A — CacheManager

| File | Action | Purpose |
|------|--------|---------|
| `pkg/cache/cache.go` | Modify | Add `Get`, `Set`, `Delete`, `Exists` methods |
| `pkg/cache/types.go` | Modify | Add `CachePayload` struct for read/write |
| `pkg/cache/cache_test.go` | Modify | Add tests for new Get/Set/Delete |
| `cmd/scanner/cache_cmd.go` | Modify | Add `get`, `set`, `delete` sub-commands |
| `src/services/go_api/cache.py` | Create | New thin wrapper: `cache_get()`, `cache_set()`, `cache_delete()` |
| `src/scrapers/cache_manager.py` | Modify | Replace `get()`/`set()`/`delete()` body with `go_api/cache.py` delegation |
| `tests/test_go_api_cache.py` | Create | Tests for new `go_api/cache.py` |

### Phase B — IncrementalJSONDB

| File | Action | Purpose |
|------|--------|---------|
| `src/models/incremental_json_database.py` | Modify | Delegate `update_video`, `get_video`, `get_all_videos`, `compact` to `go_api/db.py` |
| `tests/test_incremental_db_go_delegation.py` | Create | Tests verifying delegation + Python fallback |

---

## Phase A — CacheManager Go Core

### Task 1: Add `CachePayload` type and `Get`/`Set`/`Delete` to `pkg/cache`

**Files:**
- Modify: `pkg/cache/types.go`
- Modify: `pkg/cache/cache.go`

- [ ] **Step 1: Write the failing Go test**

  File: `pkg/cache/cache_test.go` — add inside `TestCacheManager`:

  ```go
  func TestCacheGetSetDelete(t *testing.T) {
      dir := t.TempDir()
      cm := NewCacheManager(dir)

      // Set
      err := cm.Set("test-key", []byte(`{"actress":"蒼井空"}`), 24)
      if err != nil {
          t.Fatalf("Set failed: %v", err)
      }

      // Get
      data, found, err := cm.Get("test-key")
      if err != nil || !found {
          t.Fatalf("Get failed: found=%v err=%v", found, err)
      }
      if string(data) != `{"actress":"蒼井空"}` {
          t.Fatalf("unexpected value: %s", data)
      }

      // Delete
      err = cm.Delete("test-key")
      if err != nil {
          t.Fatalf("Delete failed: %v", err)
      }
      _, found, _ = cm.Get("test-key")
      if found {
          t.Fatal("key should be gone after Delete")
      }
  }

  func TestCacheExpiry(t *testing.T) {
      dir := t.TempDir()
      cm := NewCacheManager(dir)
      _ = cm.Set("expiring", []byte(`"value"`), 0) // 0 hours = already expired
      _, found, _ := cm.Get("expiring")
      if found {
          t.Fatal("expired entry should not be found")
      }
  }
  ```

- [ ] **Step 2: Run test to verify it fails**

  ```bash
  go test ./pkg/cache -run "TestCacheGetSetDelete|TestCacheExpiry" -v
  ```

  Expected: `FAIL — cm.Set undefined`

- [ ] **Step 3: Add `CachePayload` to `pkg/cache/types.go`**

  Append to end of `pkg/cache/types.go`:

  ```go
  // CachePayload 快取讀寫載荷格式（與 Python cache_manager.py 磁碟格式相容）
  type CachePayload struct {
      Version    int     `json:"version"`
      CreatedAt  float64 `json:"created_at"`
      TTLSeconds int     `json:"ttl_seconds"`
      Compressed bool    `json:"compressed"`
      Data       []byte  `json:"data"` // raw JSON bytes
  }
  ```

- [ ] **Step 4: Add `Set`, `Get`, `Delete`, `Exists` to `pkg/cache/cache.go`**

  Append to end of `pkg/cache/cache.go`:

  ```go
  // generateKey 產生 SHA256 快取 key（與 Python _generate_cache_key 相容）
  func (cm *CacheManager) generateKey(key string) string {
      h := fmt.Sprintf("%x", sha256sum(key))
      return h
  }

  func sha256sum(s string) []byte {
      // import crypto/sha256
      h := sha256.Sum256([]byte(s))
      return h[:]
  }

  // cacheFilePath 回傳快取檔案路徑
  func (cm *CacheManager) cacheFilePath(cacheKey string) string {
      subDir := cacheKey[:2]
      return filepath.Join(cm.cacheDir, subDir, cacheKey+".json")
  }

  // Set 寫入快取值（ttlHours=0 視為立即過期）
  func (cm *CacheManager) Set(key string, value []byte, ttlHours int) error {
      cacheKey := cm.generateKey(key)
      filePath := cm.cacheFilePath(cacheKey)

      if err := os.MkdirAll(filepath.Dir(filePath), 0750); err != nil {
          return fmt.Errorf("建立快取子目錄失敗: %w", err)
      }

      payload := CachePayload{
          Version:    1,
          CreatedAt:  float64(time.Now().Unix()),
          TTLSeconds: ttlHours * 3600,
          Compressed: false,
          Data:       value,
      }
      data, err := json.Marshal(payload)
      if err != nil {
          return fmt.Errorf("序列化快取載荷失敗: %w", err)
      }
      if err := safefile.WriteFile(filePath, data, 0600); err != nil {
          return fmt.Errorf("寫入快取檔案失敗: %w", err)
      }

      // 更新索引
      index, _ := cm.loadIndex()
      if index == nil {
          index = &CacheIndex{Entries: make(map[string]IndexEntry)}
      }
      index.Entries[cacheKey] = IndexEntry{
          FilePath:     filePath,
          CreatedAt:    payload.CreatedAt,
          TTLSeconds:   payload.TTLSeconds,
          LastAccessed: payload.CreatedAt,
          AccessCount:  0,
          Compressed:   false,
          SizeBytes:    len(data),
      }
      return cm.saveIndex(index)
  }

  // Get 讀取快取值；found=false 表示不存在或已過期
  func (cm *CacheManager) Get(key string) (value []byte, found bool, err error) {
      cacheKey := cm.generateKey(key)
      filePath := cm.cacheFilePath(cacheKey)

      data, readErr := safefile.ReadFile(filePath)
      if readErr != nil {
          return nil, false, nil // 不存在
      }

      var payload CachePayload
      if err := json.Unmarshal(data, &payload); err != nil {
          return nil, false, nil
      }

      // 檢查過期
      if payload.TTLSeconds > 0 {
          age := float64(time.Now().Unix()) - payload.CreatedAt
          if age > float64(payload.TTLSeconds) {
              return nil, false, nil // 已過期
          }
      } else if payload.TTLSeconds == 0 {
          return nil, false, nil // ttl=0 = 立即過期
      }

      // 更新存取統計（best-effort，忽略錯誤）
      index, _ := cm.loadIndex()
      if index != nil {
          if entry, ok := index.Entries[cacheKey]; ok {
              entry.LastAccessed = float64(time.Now().Unix())
              entry.AccessCount++
              index.Entries[cacheKey] = entry
              _ = cm.saveIndex(index)
          }
      }

      return payload.Data, true, nil
  }

  // Delete 刪除快取條目
  func (cm *CacheManager) Delete(key string) error {
      cacheKey := cm.generateKey(key)
      filePath := cm.cacheFilePath(cacheKey)

      if !cm.validateCachePath(filePath) {
          return fmt.Errorf("路徑安全驗證失敗: %s", filePath)
      }
      _ = os.Remove(filePath)

      index, _ := cm.loadIndex()
      if index != nil {
          delete(index.Entries, cacheKey)
          return cm.saveIndex(index)
      }
      return nil
  }

  // Exists 檢查快取 key 是否存在且未過期
  func (cm *CacheManager) Exists(key string) bool {
      _, found, _ := cm.Get(key)
      return found
  }
  ```

  Add import `"crypto/sha256"` to `cache.go` imports block.

- [ ] **Step 5: Run tests to verify they pass**

  ```bash
  go test ./pkg/cache -v
  ```

  Expected: All PASS including `TestCacheGetSetDelete`, `TestCacheExpiry`

- [ ] **Step 6: Commit**

  ```bash
  git add pkg/cache/cache.go pkg/cache/types.go pkg/cache/cache_test.go
  git commit -m "feat(cache): add Get/Set/Delete/Exists core operations to pkg/cache"
  ```

---

### Task 2: Expose `cache get|set|delete` via `classifier.exe`

**Files:**
- Modify: `cmd/scanner/cache_cmd.go`

- [ ] **Step 1: Locate the existing `cache` command handler**

  ```bash
  grep -n "cache" cmd/scanner/cache_cmd.go | head -20
  ```

  Find the `handleCache` function and the sub-command dispatch.

- [ ] **Step 2: Add `get`, `set`, `delete` sub-commands to `handleCacheCmd` in `cmd/scanner/cache_cmd.go`**

  In the sub-command switch, add:

  ```go
  case "get":
      // Usage: classifier.exe cache get --dir <dir> --key <key>
      fs := flag.NewFlagSet("cache get", flag.ContinueOnError)
      dir := fs.String("dir", "cache", "快取目錄")
      key := fs.String("key", "", "快取 key")
      if err := fs.Parse(args[1:]); err != nil || *key == "" {
          fmt.Fprintln(os.Stderr, "Usage: cache get --dir <dir> --key <key>")
          os.Exit(1)
      }
      cm := cache.NewCacheManager(*dir)
      value, found, err := cm.Get(*key)
      if err != nil {
          fmt.Fprintf(os.Stderr, `{"error":%q}`+"\n", err.Error())
          os.Exit(1)
      }
      if !found {
          fmt.Println(`{"found":false,"value":null}`)
          return
      }
      fmt.Printf(`{"found":true,"value":%s}`+"\n", value)

  case "set":
      // Usage: classifier.exe cache set --dir <dir> --key <key> --value <json> --ttl <hours>
      fs := flag.NewFlagSet("cache set", flag.ContinueOnError)
      dir := fs.String("dir", "cache", "快取目錄")
      key := fs.String("key", "", "快取 key")
      value := fs.String("value", "", "JSON 值")
      ttl := fs.Int("ttl", 24, "TTL 小時數")
      if err := fs.Parse(args[1:]); err != nil || *key == "" {
          fmt.Fprintln(os.Stderr, "Usage: cache set --dir <dir> --key <key> --value <json> --ttl <hours>")
          os.Exit(1)
      }
      cm := cache.NewCacheManager(*dir)
      if err := cm.Set(*key, []byte(*value), *ttl); err != nil {
          fmt.Fprintf(os.Stderr, `{"error":%q}`+"\n", err.Error())
          os.Exit(1)
      }
      fmt.Println(`{"success":true}`)

  case "delete":
      // Usage: classifier.exe cache delete --dir <dir> --key <key>
      fs := flag.NewFlagSet("cache delete", flag.ContinueOnError)
      dir := fs.String("dir", "cache", "快取目錄")
      key := fs.String("key", "", "快取 key")
      if err := fs.Parse(args[1:]); err != nil || *key == "" {
          fmt.Fprintln(os.Stderr, "Usage: cache delete --dir <dir> --key <key>")
          os.Exit(1)
      }
      cm := cache.NewCacheManager(*dir)
      if err := cm.Delete(*key); err != nil {
          fmt.Fprintf(os.Stderr, `{"error":%q}`+"\n", err.Error())
          os.Exit(1)
      }
      fmt.Println(`{"success":true}`)
  ```

- [ ] **Step 3: Build and smoke test**

  ```bash
  go build -o classifier.exe ./cmd/scanner
  ./classifier.exe cache set --key "test-001" --value '{"actress":"蒼井空"}' --ttl 1
  ./classifier.exe cache get --key "test-001"
  ./classifier.exe cache delete --key "test-001"
  ./classifier.exe cache get --key "test-001"
  ```

  Expected output:
  ```
  {"success":true}
  {"found":true,"value":{"actress":"蒼井空"}}
  {"success":true}
  {"found":false,"value":null}
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add cmd/scanner/cache_cmd.go classifier.exe
  git commit -m "feat(cli): expose cache get/set/delete sub-commands"
  ```

---

### Task 3: Create `src/services/go_api/cache.py`

**Files:**
- Create: `src/services/go_api/cache.py`
- Create: `tests/test_go_api_cache.py`

- [ ] **Step 1: Write the failing test**

  File: `tests/test_go_api_cache.py`

  ```python
  import pytest
  from unittest.mock import MagicMock

  def make_runner(stdout: str, returncode: int = 0):
      r = MagicMock()
      r.run.return_value = MagicMock(stdout=stdout, returncode=returncode)
      return r

  def test_cache_set_success():
      from src.services.go_api.cache import cache_set
      runner = make_runner('{"success":true}')
      result = cache_set("test-key", {"actress": "蒼井空"}, ttl_hours=24, runner=runner)
      assert result["success"] is True
      runner.run.assert_called_once()

  def test_cache_get_found():
      from src.services.go_api.cache import cache_get
      runner = make_runner('{"found":true,"value":{"actress":"蒼井空"}}')
      result = cache_get("test-key", runner=runner)
      assert result["found"] is True
      assert result["value"]["actress"] == "蒼井空"

  def test_cache_get_not_found():
      from src.services.go_api.cache import cache_get
      runner = make_runner('{"found":false,"value":null}')
      result = cache_get("test-key", runner=runner)
      assert result["found"] is False
      assert result["value"] is None

  def test_cache_delete_success():
      from src.services.go_api.cache import cache_delete
      runner = make_runner('{"success":true}')
      result = cache_delete("test-key", runner=runner)
      assert result["success"] is True

  def test_cache_set_go_unavailable():
      from src.services.go_api.cache import cache_set
      runner = make_runner("", returncode=1)
      result = cache_set("test-key", {"x": 1}, runner=runner)
      assert result["success"] is False
      assert "error" in result
  ```

- [ ] **Step 2: Run test to verify it fails**

  ```bash
  python -m pytest tests/test_go_api_cache.py -v
  ```

  Expected: `FAIL — cannot import name 'cache_set'`

- [ ] **Step 3: Create `src/services/go_api/cache.py`**

  ```python
  """
  Go CLI 快取操作 API
  對應 classifier.exe cache get|set|delete
  """
  import json
  import logging
  from typing import Any

  logger = logging.getLogger(__name__)

  _DEFAULT_CACHE_DIR = "cache"


  def _get_runner(runner=None):
      if runner is not None:
          return runner
      try:
          try:
              from services.go_runner import GoCommandRunner
          except ImportError:
              from src.services.go_runner import GoCommandRunner
          return GoCommandRunner()
      except Exception:
          return None


  def cache_set(
      key: str,
      value: Any,
      ttl_hours: int = 24,
      cache_dir: str = _DEFAULT_CACHE_DIR,
      runner=None,
  ) -> dict:
      """寫入快取；回傳 {"success": bool, "error": str | None}"""
      r = _get_runner(runner)
      if r is None:
          return {"success": False, "error": "Go runner 不可用"}
      try:
          value_json = json.dumps(value, ensure_ascii=False)
          result = r.run(
              ["cache", "set", "--dir", cache_dir, "--key", key,
               "--value", value_json, "--ttl", str(ttl_hours)]
          )
          if result.returncode != 0:
              return {"success": False, "error": f"exit {result.returncode}"}
          return json.loads(result.stdout)
      except Exception as e:
          logger.debug(f"cache_set 失敗: {e}")
          return {"success": False, "error": str(e)}


  def cache_get(
      key: str,
      cache_dir: str = _DEFAULT_CACHE_DIR,
      runner=None,
  ) -> dict:
      """讀取快取；回傳 {"found": bool, "value": Any}"""
      r = _get_runner(runner)
      if r is None:
          return {"found": False, "value": None}
      try:
          result = r.run(["cache", "get", "--dir", cache_dir, "--key", key])
          if result.returncode != 0:
              return {"found": False, "value": None}
          return json.loads(result.stdout)
      except Exception as e:
          logger.debug(f"cache_get 失敗: {e}")
          return {"found": False, "value": None}


  def cache_delete(
      key: str,
      cache_dir: str = _DEFAULT_CACHE_DIR,
      runner=None,
  ) -> dict:
      """刪除快取；回傳 {"success": bool}"""
      r = _get_runner(runner)
      if r is None:
          return {"success": False, "error": "Go runner 不可用"}
      try:
          result = r.run(["cache", "delete", "--dir", cache_dir, "--key", key])
          if result.returncode != 0:
              return {"success": False, "error": f"exit {result.returncode}"}
          return json.loads(result.stdout)
      except Exception as e:
          logger.debug(f"cache_delete 失敗: {e}")
          return {"success": False, "error": str(e)}
  ```

- [ ] **Step 4: Run tests to verify they pass**

  ```bash
  python -m pytest tests/test_go_api_cache.py -v
  ```

  Expected: 5 passed

- [ ] **Step 5: Commit**

  ```bash
  git add src/services/go_api/cache.py tests/test_go_api_cache.py
  git commit -m "feat(go_api): add cache.py wrapper for Go cache get/set/delete"
  ```

---

### Task 4: Delegate `CacheManager.get()` / `set()` / `delete()` to Go

**Files:**
- Modify: `src/scrapers/cache_manager.py` (methods `set`, `get`, `delete`, `_delete_cache_entry`)

- [ ] **Step 1: Write the failing test for delegation**

  Add to `tests/test_go_api_cache.py`:

  ```python
  def test_cache_manager_set_delegates_to_go(monkeypatch):
      from src.scrapers.cache_manager import CacheManager
      from unittest.mock import patch, MagicMock

      mock_set = MagicMock(return_value={"success": True})
      with patch("src.scrapers.cache_manager.cache_set", mock_set):
          cm = CacheManager()
          result = cm.set("SSIS-100", {"actress": "蒼井空"})
          assert result is True
          mock_set.assert_called_once()

  def test_cache_manager_get_delegates_to_go(monkeypatch):
      from src.scrapers.cache_manager import CacheManager
      from unittest.mock import patch

      mock_get = lambda key, **kw: {"found": True, "value": {"actress": "蒼井空"}}
      with patch("src.scrapers.cache_manager.cache_get", mock_get):
          cm = CacheManager()
          result = cm.get("SSIS-100")
          assert result == {"actress": "蒼井空"}

  def test_cache_manager_get_fallback_on_go_miss(monkeypatch):
      """Go 回傳 not found 時，應直接回傳 None（不再做磁碟讀取）"""
      from src.scrapers.cache_manager import CacheManager
      from unittest.mock import patch

      mock_get = lambda key, **kw: {"found": False, "value": None}
      with patch("src.scrapers.cache_manager.cache_get", mock_get):
          cm = CacheManager()
          result = cm.get("MISSING-KEY")
          assert result is None
  ```

- [ ] **Step 2: Run test to verify it fails**

  ```bash
  python -m pytest tests/test_go_api_cache.py::test_cache_manager_set_delegates_to_go -v
  ```

  Expected: FAIL — `cache_set` not imported in `cache_manager.py`

- [ ] **Step 3: Modify `src/scrapers/cache_manager.py` — add import + delegate `set`**

  At top of `cache_manager.py`, add after existing imports:

  ```python
  try:
      from services.go_api.cache import cache_delete as _go_cache_delete
      from services.go_api.cache import cache_get as _go_cache_get
      from services.go_api.cache import cache_set as _go_cache_set
      _GO_CACHE_AVAILABLE = True
  except ImportError:
      try:
          from src.services.go_api.cache import cache_delete as _go_cache_delete
          from src.services.go_api.cache import cache_get as _go_cache_get
          from src.services.go_api.cache import cache_set as _go_cache_set
          _GO_CACHE_AVAILABLE = True
      except ImportError:
          _GO_CACHE_AVAILABLE = False
  ```

  Replace `CacheManager.set()` method body with:

  ```python
  def set(self, key: str, value: Any, ttl_hours: int | None = None) -> bool:
      """寫入快取，優先委派 Go CLI；Go 不可用時降級到 Python 磁碟快取。"""
      ttl = ttl_hours if ttl_hours is not None else self.config.default_ttl_hours
      if _GO_CACHE_AVAILABLE:
          try:
              result = _go_cache_set(key, value, ttl_hours=ttl,
                                     cache_dir=str(self.cache_dir))
              if result.get("success"):
                  return True
          except Exception as e:
              logger.debug(f"Go cache set 失敗，降級 Python: {e}")
      # Python fallback（原有磁碟寫入邏輯保留不變）
      return self._set_python(key, value, ttl)
  ```

  Rename existing `set()` method body to `_set_python()`.

  Replace `CacheManager.get()` method body with:

  ```python
  def get(self, key: str) -> Any | None:
      """讀取快取，優先委派 Go CLI；Go 不可用時降級 Python。"""
      if _GO_CACHE_AVAILABLE:
          try:
              result = _go_cache_get(key, cache_dir=str(self.cache_dir))
              if result.get("found"):
                  return result["value"]
              return None  # Go 明確回傳 not found，不再嘗試 Python
          except Exception as e:
              logger.debug(f"Go cache get 失敗，降級 Python: {e}")
      return self._get_python(key)
  ```

  Rename existing `get()` method body to `_get_python()`.

  Replace `CacheManager.delete()` method body with:

  ```python
  def delete(self, key: str) -> bool:
      """刪除快取，優先委派 Go CLI；Go 不可用時降級 Python。"""
      if _GO_CACHE_AVAILABLE:
          try:
              result = _go_cache_delete(key, cache_dir=str(self.cache_dir))
              return result.get("success", False)
          except Exception as e:
              logger.debug(f"Go cache delete 失敗，降級 Python: {e}")
      return self._delete_python(key)
  ```

  Rename existing `delete()` method body to `_delete_python()`.

- [ ] **Step 4: Run all cache tests**

  ```bash
  python -m pytest tests/test_go_api_cache.py -v
  ```

  Expected: All 8 passed

- [ ] **Step 5: Run full test suite to verify no regression**

  ```bash
  python -m pytest tests/ -v --tb=short -q
  ```

  Expected: All passed (same count as before)

- [ ] **Step 6: Commit**

  ```bash
  git add src/scrapers/cache_manager.py tests/test_go_api_cache.py
  git commit -m "refactor(cache): delegate set/get/delete to Go CLI; Python as fallback"
  ```

---

## Phase B — IncrementalJSONDB Go Delegation

### Task 5: Delegate `update_video` / `get_video` to `go_api/db.py`

**Files:**
- Modify: `src/models/incremental_json_database.py`
- Create: `tests/test_incremental_db_go_delegation.py`

- [ ] **Step 1: Verify `go_api/db.py` has the needed functions**

  ```bash
  grep -n "^def " src/services/go_api/db.py
  ```

  Expected: `db_get_video`, `db_update_video`, `db_list_videos`, `db_compact` (all with `runner=` param)

- [ ] **Step 2: Write the failing test**

  File: `tests/test_incremental_db_go_delegation.py`

  ```python
  import pytest
  from unittest.mock import patch, MagicMock


  def make_db_runner(result_dict: dict):
      runner = MagicMock()
      import json
      runner.run.return_value = MagicMock(
          stdout=json.dumps(result_dict), returncode=0
      )
      return runner


  def test_update_video_delegates_to_go():
      from src.models.incremental_json_database import IncrementalJSONDB

      mock_update = MagicMock(return_value={"success": True})
      with patch("src.models.incremental_json_database.db_update_video", mock_update):
          db = IncrementalJSONDB("data/json_db")
          db.update_video("SSIS-100", {"title": "test"})
          mock_update.assert_called_once()
          call_args = mock_update.call_args
          assert call_args[0][0] == "SSIS-100"


  def test_get_video_delegates_to_go():
      from src.models.incremental_json_database import IncrementalJSONDB

      mock_data = {"code": "SSIS-100", "title": "test", "actress": ["蒼井空"]}
      mock_get = MagicMock(return_value={"success": True, "video": mock_data})
      with patch("src.models.incremental_json_database.db_get_video", mock_get):
          db = IncrementalJSONDB("data/json_db")
          result = db.get_video("SSIS-100")
          assert result == mock_data
          mock_get.assert_called_once_with("SSIS-100", db_dir="data/json_db")


  def test_get_video_returns_none_on_miss():
      from src.models.incremental_json_database import IncrementalJSONDB

      mock_get = MagicMock(return_value={"success": False, "video": None})
      with patch("src.models.incremental_json_database.db_get_video", mock_get):
          db = IncrementalJSONDB("data/json_db")
          result = db.get_video("NOTEXIST-999")
          assert result is None


  def test_python_fallback_when_go_unavailable():
      """Go 不可用時，應降級到 Python 實作，不拋出例外。"""
      from src.models.incremental_json_database import IncrementalJSONDB

      with patch("src.models.incremental_json_database._GO_DB_AVAILABLE", False):
          db = IncrementalJSONDB("data/json_db")
          # Python fallback 執行不拋例外即可
          try:
              db.get_video("FALLBACK-001")
          except Exception as e:
              pytest.fail(f"Python fallback 不應拋出例外: {e}")
  ```

- [ ] **Step 3: Run test to verify it fails**

  ```bash
  python -m pytest tests/test_incremental_db_go_delegation.py -v
  ```

  Expected: FAIL — `db_update_video` not imported in `incremental_json_database.py`

- [ ] **Step 4: Add Go delegation to `src/models/incremental_json_database.py`**

  At top of file, after existing imports, add:

  ```python
  try:
      from services.go_api.db import db_get_video, db_update_video, db_list_videos
      _GO_DB_AVAILABLE = True
  except ImportError:
      try:
          from src.services.go_api.db import db_get_video, db_update_video, db_list_videos
          _GO_DB_AVAILABLE = True
      except ImportError:
          _GO_DB_AVAILABLE = False
  ```

  In `IncrementalJSONDB.get_video()`, prepend delegation:

  ```python
  def get_video(self, code: str) -> dict | None:
      """取得影片資料，優先委派 Go CLI。"""
      if _GO_DB_AVAILABLE:
          try:
              result = db_get_video(code, db_dir=self.db_dir)
              if result.get("success"):
                  return result.get("video")
              return None
          except Exception as e:
              logger.debug(f"Go db_get_video 失敗，降級 Python: {e}")
      return self._get_video_python(code)
  ```

  Rename existing `get_video()` body to `_get_video_python()`.

  In `IncrementalJSONDB.update_video()`, prepend delegation:

  ```python
  def update_video(self, code: str, data: dict) -> bool:
      """更新影片資料，優先委派 Go CLI。"""
      if _GO_DB_AVAILABLE:
          try:
              result = db_update_video(code, data, db_dir=self.db_dir)
              if result.get("success"):
                  return True
          except Exception as e:
              logger.debug(f"Go db_update_video 失敗，降級 Python: {e}")
      return self._update_video_python(code, data)
  ```

  Rename existing `update_video()` body to `_update_video_python()`.

- [ ] **Step 5: Run delegation tests**

  ```bash
  python -m pytest tests/test_incremental_db_go_delegation.py -v
  ```

  Expected: 4 passed

- [ ] **Step 6: Run full suite to verify no regression**

  ```bash
  python -m pytest tests/ -v --tb=short -q
  ```

  Expected: All passed

- [ ] **Step 7: Run Go tests**

  ```bash
  go test ./pkg/... -v
  ```

  Expected: All passed

- [ ] **Step 8: Commit**

  ```bash
  git add src/models/incremental_json_database.py tests/test_incremental_db_go_delegation.py
  git commit -m "refactor(db): delegate get_video/update_video to Go CLI in IncrementalJSONDB"
  ```

---

## Self-Review

**Spec coverage check:**
- ✅ `pkg/cache` Get/Set/Delete → Task 1
- ✅ CLI `cache get|set|delete` → Task 2
- ✅ `go_api/cache.py` thin wrapper → Task 3
- ✅ `cache_manager.py` delegation → Task 4
- ✅ `incremental_json_database.py` delegation → Task 5
- ✅ Python fallback for all paths → Tasks 4, 5

**No placeholders:** All tasks have complete code blocks.

**Type consistency:**
- `cache_set` / `cache_get` / `cache_delete` → consistent across `go_api/cache.py`, `cache_manager.py`, tests
- `db_get_video` / `db_update_video` → matches existing `go_api/db.py` signatures
- `_go_cache_set` / `_go_cache_get` / `_go_cache_delete` → internal aliases, consistent usage

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-05-phase4-cache-and-incremental-db-go-migration.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, two-stage review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session with checkpoints for review

Which approach?
