# Phase 9 Go 遷移收尾計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 根據 OpenClaw 審閱報告（`openclaw-review/OPENCLAW_AUDIT_2026-04-06.md`），完成 Python→Go 遷移的三個收尾工作：e2e 整合驗證、GoBridgeError 語意細化、IncrementalJSONDB 過渡層清理。

**Architecture:** Go 已是唯一核心真相來源，Python 只保留 GUI / 薄橋接 / 例外處理。本計畫不新增功能，只補強測試證據、修清語意歧義、移除 Python 業務殘留。

**Tech Stack:** Python 3.11+、Go 1.24.5、pytest、`classifier.exe`（Go CLI）

**OpenClaw 原文判斷：**  
> 「這個 migration 已經從『能不能做』進入『要不要把殘留整理乾淨』的階段了。」

---

## 背景：OpenClaw 指出的三大缺口

| # | 缺口 | 影響 |
|---|------|------|
| 1 | **e2e 驗證不足** — 現有測試全用 mock，沒有真正執行 classifier.exe | 「函式存在」≠「CLI 打通」，測試沒有價值 |
| 2 | **GoBridgeError 語意不清** — 無法區分「資料不存在」vs「CLI 失敗」vs「JSON 解析失敗」 | 上層把「真實不存在」誤當「系統壞掉」，或反過來 |
| 3 | **IncrementalJSONDB 雙份業務邏輯** — `add_video`/`delete_video` 仍在 Python，不走 Go | 過渡層膨脹，雙邊維護成本 |

---

## 檔案異動清單

### Phase 9A（e2e 測試）

| 操作 | 檔案 |
|------|------|
| **新建** | `tests/integration/test_go_cli_e2e.py` |
| **新建** | `tests/integration/__init__.py` |
| **新建** | `tests/integration/conftest.py` |

### Phase 9B（GoBridgeError 語意細化）

| 操作 | 檔案 |
|------|------|
| **修改** | `src/services/go_runner.py`（新增 3 個 exception 子類） |
| **修改** | `src/models/json_database.py`（呼叫方 catch 改成精確子類） |
| **修改** | `src/scrapers/cache_manager.py`（同上） |
| **新建** | `tests/test_go_runner_errors.py` |

### Phase 9C（IncrementalJSONDB 清理）

| 操作 | 檔案 |
|------|------|
| **修改** | `src/models/incremental_json_database.py`（`add_video`/`delete_video` 委派 Go） |
| **修改** | `tests/test_incremental_db.py`（更新相關測試） |
| **修改** | `tests/test_incremental_db_go_delegation.py`（補測試） |

---

## Phase 9A：e2e 整合驗證

> 目標：建立真正執行 `classifier.exe` 的整合測試，不使用 mock。  
> 現有 16 個測試全使用 `/nonexistent/path/classifier.exe`，等同沒有 e2e 保障。

---

### Task 9A-1：建立 integration 測試基礎設施

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/conftest.py`

- [ ] **Step 1：建立 `__init__.py`**

```python
# tests/integration/__init__.py
# 整合測試套件：真正執行 classifier.exe，不使用 mock
```

- [ ] **Step 2：建立 `conftest.py`**

```python
# tests/integration/conftest.py
import os
import pytest
import tempfile
import shutil
from pathlib import Path


@pytest.fixture(scope="session")
def go_exe():
    """確認 classifier.exe 可用，否則 skip 整個 session。"""
    # 搜尋路徑
    candidates = [
        Path(__file__).parents[2] / "classifier.exe",
        Path(__file__).parents[2] / "classifier",
        Path(os.getcwd()) / "classifier.exe",
    ]
    for c in candidates:
        if c.exists() and os.access(c, os.X_OK):
            return str(c)
    pytest.skip("classifier.exe 不存在，跳過 e2e 整合測試（需先執行 go build -o classifier.exe ./cmd/scanner）")


@pytest.fixture
def temp_data_dir(tmp_path):
    """建立帶有最小初始資料的暫存資料目錄。"""
    data_dir = tmp_path / "json_db"
    data_dir.mkdir()
    # 最小合法 JSON 資料庫
    (data_dir / "data.json").write_text(
        '{"videos": {}, "actresses": {}, "links": []}',
        encoding="utf-8"
    )
    return str(data_dir)


@pytest.fixture
def runner(go_exe):
    """回傳已初始化的 GoCommandRunner。"""
    from src.services.go_runner import GoCommandRunner
    return GoCommandRunner(go_exe)
```

- [ ] **Step 3：確認 classifier.exe 存在**

```powershell
# 若不存在，先建置
go build -o classifier.exe ./cmd/scanner
# 確認可執行
.\classifier.exe help
```

預期輸出：包含 `Usage:` 的說明文字。

- [ ] **Step 4：Commit**

```bash
git add tests/integration/
git commit -m "test(e2e): 建立 integration 測試基礎設施"
```

---

### Task 9A-2：db CLI e2e 測試

**Files:**
- Create: `tests/integration/test_go_cli_e2e.py`

- [ ] **Step 1：寫 db 子命令測試**

```python
# tests/integration/test_go_cli_e2e.py
import json
import pytest


class TestDbCLI:
    """db 子命令 e2e 測試。"""

    def test_db_update_and_get(self, runner, temp_data_dir):
        """update → get 應能取回相同資料。"""
        code = "TEST-001"
        payload = json.dumps({"title": "測試影片", "actresses": ["測試女優"]})

        # update
        result = runner.run_json([
            "db", "update", code,
            "-data", payload,
            "-data-dir", temp_data_dir,
        ])
        assert result.get("success") is True, f"update 失敗: {result}"

        # get
        video = runner.run_json(["db", "get", code, "-data-dir", temp_data_dir])
        assert video["code"] == code
        assert video["title"] == "測試影片"

    def test_db_delete(self, runner, temp_data_dir):
        """新增後 delete，再 get 應回傳 not_found。"""
        code = "TEST-DEL"
        runner.run_json([
            "db", "update", code,
            "-data", '{"title": "待刪"}',
            "-data-dir", temp_data_dir,
        ])

        runner.run_json(["db", "delete", code, "-data-dir", temp_data_dir])

        from src.services.go_runner import GoBridgeError
        with pytest.raises(GoBridgeError):
            runner.run_json(["db", "get", code, "-data-dir", temp_data_dir])

    def test_db_list(self, runner, temp_data_dir):
        """list 應回傳 array。"""
        result = runner.run_json(["db", "list", "-data-dir", temp_data_dir])
        assert isinstance(result, list)

    def test_db_stats(self, runner, temp_data_dir):
        """stats 應包含 total 欄位。"""
        result = runner.run_json(["db", "stats", "-data-dir", temp_data_dir])
        assert "total" in result

    def test_db_backup_create_and_list(self, runner, temp_data_dir):
        """backup-create 後，backup-list 應至少有 1 筆。"""
        runner.run_json(["db", "backup-create", "-data-dir", temp_data_dir])
        backups = runner.run_json(["db", "backup-list", "-data-dir", temp_data_dir])
        assert isinstance(backups, list)
        assert len(backups) >= 1
```

- [ ] **Step 2：執行測試（應通過）**

```powershell
python -m pytest tests/integration/test_go_cli_e2e.py::TestDbCLI -v
```

預期：5 個 PASSED。若 `skip`，代表 classifier.exe 不存在，先 build。

- [ ] **Step 3：Commit**

```bash
git add tests/integration/test_go_cli_e2e.py
git commit -m "test(e2e): db CLI update/get/delete/list/stats/backup"
```

---

### Task 9A-3：cache / identify / scan CLI e2e 測試

**Files:**
- Modify: `tests/integration/test_go_cli_e2e.py`

- [ ] **Step 1：補 cache、identify、scan 測試類**

```python
# 加入 test_go_cli_e2e.py 末尾

class TestCacheCLI:
    """cache 子命令 e2e 測試。"""

    def test_cache_set_get_delete(self, runner, tmp_path):
        cache_dir = str(tmp_path / "cache")
        key = "test-key-001"
        value = json.dumps({"data": "hello"})

        runner.run_json(["cache", "set", key, "-value", value, "-dir", cache_dir])
        got = runner.run_json(["cache", "get", key, "-dir", cache_dir])
        assert json.loads(got.get("value", "{}")) == {"data": "hello"}

        runner.run_json(["cache", "delete", key, "-dir", cache_dir])

    def test_cache_stats(self, runner, tmp_path):
        cache_dir = str(tmp_path / "cache")
        result = runner.run_json(["cache", "stats", "-dir", cache_dir])
        assert "total_entries" in result or "total" in result


class TestIdentifyCLI:
    """identify 子命令 e2e 測試。"""

    def test_identify_known_code(self, runner):
        """STARS-001 應能識別片商（S1 或未知，但不應 crash）。"""
        result = runner.run_json(["identify", "STARS-001"])
        assert "studio" in result or "code" in result

    def test_identify_list(self, runner):
        """list 應回傳已知片商陣列。"""
        result = runner.run_json(["identify", "-list"])
        assert isinstance(result, list)
        assert len(result) > 0


class TestScanCLI:
    """scan 子命令 e2e 測試。"""

    def test_scan_empty_dir(self, runner, tmp_path):
        """掃描空目錄應回傳 0 個結果。"""
        result = runner.run_json(["scan", "-dir", str(tmp_path)])
        files = result.get("files", result if isinstance(result, list) else [])
        assert isinstance(files, list)

    def test_scan_with_files(self, runner, tmp_path):
        """目錄放入含番號的假檔案，scan 應提取番號。"""
        (tmp_path / "STARS-707.mp4").write_text("fake")
        (tmp_path / "FC2-PPV-123456.mp4").write_text("fake")

        result = runner.run_json(["scan", "-dir", str(tmp_path)])
        files = result.get("files", result if isinstance(result, list) else [])
        codes = [f.get("code", "") for f in files]
        assert "STARS-707" in codes
```

- [ ] **Step 2：執行測試**

```powershell
python -m pytest tests/integration/test_go_cli_e2e.py -v
```

預期：所有測試 PASSED（或 SKIPPED，若 CLI 不支援某子命令的精確格式，記錄差異）。

- [ ] **Step 3：Commit**

```bash
git add tests/integration/test_go_cli_e2e.py
git commit -m "test(e2e): cache/identify/scan CLI 整合測試"
```

---

### Task 9A-4：Python bridge e2e 驗證

**Files:**
- Modify: `tests/integration/test_go_cli_e2e.py`

- [ ] **Step 1：補 Python bridge 整合測試**

```python
# 加入 test_go_cli_e2e.py 末尾

class TestPythonBridgeE2E:
    """確認 Python bridge 能正確呼叫 Go CLI 並取得預期回傳。"""

    def test_go_bridge_is_available(self, go_exe):
        """GoBridge.is_available 應為 True。"""
        from src.services.go_bridge import GoBridge
        bridge = GoBridge(exe_path=go_exe)
        assert bridge.is_available is True

    def test_db_get_video_not_found_returns_none(self, go_exe, temp_data_dir):
        """db_get_video 找不到資料時，應回傳 None（非 raise）。"""
        from src.services.go_api.db import db_get_video
        from src.services.go_runner import GoCommandRunner
        runner = GoCommandRunner(go_exe)
        result = db_get_video("NOTEXIST-999", data_dir=temp_data_dir, runner=runner)
        assert result is None

    def test_db_update_and_get_via_bridge(self, go_exe, temp_data_dir):
        """bridge update → get 流程完整打通。"""
        from src.services.go_api.db import db_update_video, db_get_video
        from src.services.go_runner import GoCommandRunner
        runner = GoCommandRunner(go_exe)

        ok = db_update_video(
            "BRIDGE-001",
            {"title": "Bridge Test", "actresses": []},
            data_dir=temp_data_dir,
            runner=runner,
        )
        assert ok is True

        video = db_get_video("BRIDGE-001", data_dir=temp_data_dir, runner=runner)
        assert video is not None
        assert video["title"] == "Bridge Test"
```

- [ ] **Step 2：執行 bridge e2e**

```powershell
python -m pytest tests/integration/test_go_cli_e2e.py::TestPythonBridgeE2E -v
```

預期：3 個 PASSED。

- [ ] **Step 3：Commit**

```bash
git add tests/integration/test_go_cli_e2e.py
git commit -m "test(e2e): Python bridge → Go CLI 完整打通驗證"
```

---

## Phase 9B：GoBridgeError 語意細化

> 目標：讓呼叫端能精確區分三種失敗，不再全部吃到 `GoBridgeError`。  
> 現況：`GoBridgeError` 是單一 exception，無法區分：  
> - `GoBridgeNotFoundError`：CLI 回傳 404/not_found（資料不存在，正常）  
> - `GoBridgeExecError`：CLI 執行失敗（returncode != 0）  
> - `GoBridgeJSONError`：stdout 不是合法 JSON

---

### Task 9B-1：新增 exception 子類

**Files:**
- Modify: `src/services/go_runner.py`
- Create: `tests/test_go_runner_errors.py`

- [ ] **Step 1：先寫失敗測試**

```python
# tests/test_go_runner_errors.py
import pytest
from unittest.mock import patch, MagicMock
import subprocess

from src.services.go_runner import (
    GoCommandRunner,
    GoBridgeError,
    GoBridgeExecError,
    GoBridgeNotFoundError,
    GoBridgeJSONError,
)


def make_runner():
    return GoCommandRunner("/fake/classifier.exe")


class TestGoBridgeErrorHierarchy:
    def test_exec_error_is_go_bridge_error(self):
        assert issubclass(GoBridgeExecError, GoBridgeError)

    def test_not_found_error_is_go_bridge_error(self):
        assert issubclass(GoBridgeNotFoundError, GoBridgeError)

    def test_json_error_is_go_bridge_error(self):
        assert issubclass(GoBridgeJSONError, GoBridgeError)


class TestGoCommandRunnerErrors:
    def test_nonzero_returncode_raises_exec_error(self):
        runner = make_runner()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "some error"
        with patch("src.services.go_runner.run_subprocess", return_value=mock_result):
            with pytest.raises(GoBridgeExecError):
                runner.run(["db", "get", "FAKE"])

    def test_not_found_in_stderr_raises_not_found_error(self):
        runner = make_runner()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "video not found: FAKE-001"
        with patch("src.services.go_runner.run_subprocess", return_value=mock_result):
            with pytest.raises(GoBridgeNotFoundError):
                runner.run(["db", "get", "FAKE-001"])

    def test_invalid_json_raises_json_error(self):
        runner = make_runner()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json {"
        with patch("src.services.go_runner.run_subprocess", return_value=mock_result):
            with pytest.raises(GoBridgeJSONError):
                runner.run_json(["db", "list"])
```

- [ ] **Step 2：確認測試失敗（子類尚未定義）**

```powershell
python -m pytest tests/test_go_runner_errors.py -v
```

預期：`ImportError: cannot import name 'GoBridgeExecError'`

- [ ] **Step 3：在 `go_runner.py` 新增三個子類**

在 `class GoBridgeError(Exception):` 之後加入：

```python
class GoBridgeExecError(GoBridgeError):
    """Go CLI 執行失敗（returncode != 0）。"""
    def __init__(self, message: str, returncode: int = -1):
        super().__init__(message)
        self.returncode = returncode


class GoBridgeNotFoundError(GoBridgeError):
    """資料不存在（Go CLI 正常執行但回傳 not found）。"""
    pass


class GoBridgeJSONError(GoBridgeError):
    """Go CLI stdout 不是合法 JSON。"""
    pass
```

- [ ] **Step 4：更新 `run()` 以發出正確子類**

將 `GoCommandRunner.run()` 中的錯誤分支改為：

```python
if check and result.returncode != 0:
    stderr = result.stderr.strip()
    error_msg = stderr or f"命令失敗，返回碼: {result.returncode}"
    # 若 stderr 含 "not found" 語意，視為 NotFound
    not_found_keywords = ("not found", "no such", "does not exist", "找不到")
    if any(kw in error_msg.lower() for kw in not_found_keywords):
        raise GoBridgeNotFoundError(error_msg)
    raise GoBridgeExecError(error_msg, returncode=result.returncode)
```

將 `parse_json()` 中的錯誤分支改為：

```python
except json.JSONDecodeError as e:
    raise GoBridgeJSONError(f"JSON 解析失敗: {e}\n輸出: {output[:200]}")
```

- [ ] **Step 5：執行測試確認通過**

```powershell
python -m pytest tests/test_go_runner_errors.py -v
```

預期：6 個 PASSED。

- [ ] **Step 6：確認全套 226 測試仍通過**

```powershell
python -m pytest tests/ -x --tb=short -q
```

預期：226 passed。

- [ ] **Step 7：Commit**

```bash
git add src/services/go_runner.py tests/test_go_runner_errors.py
git commit -m "feat: GoBridgeError 語意細化 — ExecError/NotFoundError/JSONError 子類"
```

---

### Task 9B-2：呼叫方 catch 精確化

**Files:**
- Modify: `src/models/json_database.py`（`get_video`、`get_actress_info` 的 except 分支）
- Modify: `src/scrapers/cache_manager.py`（各方法的 except 分支）

- [ ] **Step 1：更新 `json_database.py` — get_video 的 except**

找到 `get_video` 方法（形如 `except GoBridgeError`），改為：

```python
from src.services.go_runner import GoBridgeError, GoBridgeNotFoundError

# 原本：
# except GoBridgeError:
#     return None

# 改為：
except GoBridgeNotFoundError:
    return None   # ← 資料確實不存在，正常回傳 None
except GoBridgeError as e:
    raise RuntimeError(f"Go CLI 執行失敗: {e}") from e  # ← 系統錯誤，往上拋
```

- [ ] **Step 2：更新 `cache_manager.py`**

找到 `cache_get()` 的 except 分支，同理：

```python
from src.services.go_runner import GoBridgeError, GoBridgeNotFoundError

except GoBridgeNotFoundError:
    return None   # ← key 不存在，正常
except GoBridgeError as e:
    logger.warning(f"⚠️ cache_get 執行失敗: {e}")
    return None   # ← cache 失敗可接受降級
```

- [ ] **Step 3：執行全套測試**

```powershell
python -m pytest tests/ -x --tb=short -q
```

預期：226 passed（含新增的 go_runner_errors 測試）。

- [ ] **Step 4：Commit**

```bash
git add src/models/json_database.py src/scrapers/cache_manager.py
git commit -m "refactor: 呼叫方 catch 精確化 — 區分 NotFound vs ExecError"
```

---

## Phase 9C：IncrementalJSONDB 過渡層清理

> 目標：`add_video()`/`delete_video()` 仍在 Python 實作 journal 寫入邏輯，應委派 Go（與 `update_video` 一致）。  
> 這是 OpenClaw 報告中「雙份業務邏輯」的最後殘留。

---

### Task 9C-1：了解現狀並寫測試

**Files:**
- Modify: `tests/test_incremental_db_go_delegation.py`

- [ ] **Step 1：確認現有 add_video 是 Python 路徑**

```powershell
Select-String -Path src\models\incremental_json_database.py -Pattern "def add_video|def delete_video" 
```

預期輸出：找到 `def add_video` 和 `def delete_video`，且方法體無 `_go_db_` 呼叫。

- [ ] **Step 2：在 `test_incremental_db_go_delegation.py` 補委派測試**

```python
# 加入 test_incremental_db_go_delegation.py

def test_add_video_calls_go(monkeypatch, tmp_path):
    """add_video 應委派 Go CLI，不走 Python journal 邏輯。"""
    from src.models.incremental_json_database import IncrementalJSONDB

    called = []

    def fake_go_update(code, data, data_dir=None, runner=None):
        called.append(code)
        return True

    monkeypatch.setattr(
        "src.models.incremental_json_database._go_db_update_video",
        fake_go_update,
    )

    db = IncrementalJSONDB(str(tmp_path))
    db._GO_DB_AVAILABLE = True
    db.add_video({"code": "INCR-001", "title": "test"})

    assert "INCR-001" in called, "add_video 應呼叫 _go_db_update_video"


def test_delete_video_calls_go(monkeypatch, tmp_path):
    """delete_video 應委派 Go CLI，不走 Python journal 邏輯。"""
    from src.models.incremental_json_database import IncrementalJSONDB

    called = []

    def fake_go_delete(code, data_dir=None, runner=None):
        called.append(code)
        return True

    monkeypatch.setattr(
        "src.models.incremental_json_database._go_db_delete_video",
        fake_go_delete,
    )

    db = IncrementalJSONDB(str(tmp_path))
    db._GO_DB_AVAILABLE = True
    db.delete_video("INCR-DEL")

    assert "INCR-DEL" in called, "delete_video 應呼叫 _go_db_delete_video"
```

- [ ] **Step 3：執行測試（預期 FAIL）**

```powershell
python -m pytest tests/test_incremental_db_go_delegation.py::test_add_video_calls_go tests/test_incremental_db_go_delegation.py::test_delete_video_calls_go -v
```

預期：FAIL（`add_video`/`delete_video` 目前不呼叫 `_go_db_*`）。

---

### Task 9C-2：委派 Go

**Files:**
- Modify: `src/models/incremental_json_database.py`

- [ ] **Step 1：在 `incremental_json_database.py` 頂部確認 import**

確認已有：
```python
from src.services.go_api.db import (
    db_get_video as _go_db_get_video,
    db_update_video as _go_db_update_video,
    db_delete_video as _go_db_delete_video,
)
```

若無，加入。

- [ ] **Step 2：改寫 `add_video()`**

找到現有 `def add_video(self, video: VideoDict):` 方法，替換為：

```python
def add_video(self, video: VideoDict):
    """新增影片記錄（委派 Go）。"""
    code = video.get("code") or video.get("id", "")
    if not code:
        raise ValueError("影片資料缺少 code 欄位")

    if self._GO_DB_AVAILABLE:
        ok = _go_db_update_video(code, dict(video), data_dir=str(self.data_dir))
        if ok:
            return
        raise RuntimeError(f"Go add_video 回傳失敗: {code}")
    raise RuntimeError(f"Go CLI 不可用，無法新增影片: {code}")
```

- [ ] **Step 3：改寫 `delete_video()`**

找到現有 `def delete_video(self, code: str):` 方法，替換為：

```python
def delete_video(self, code: str):
    """刪除影片記錄（委派 Go）。"""
    if self._GO_DB_AVAILABLE:
        ok = _go_db_delete_video(code, data_dir=str(self.data_dir))
        if ok:
            return
        raise RuntimeError(f"Go delete_video 回傳失敗: {code}")
    raise RuntimeError(f"Go CLI 不可用，無法刪除影片: {code}")
```

- [ ] **Step 4：執行委派測試（應通過）**

```powershell
python -m pytest tests/test_incremental_db_go_delegation.py -v
```

預期：所有測試 PASSED。

- [ ] **Step 5：執行全套測試**

```powershell
python -m pytest tests/ -x --tb=short -q
```

預期：全部 PASSED（包含新測試）。

- [ ] **Step 6：Commit**

```bash
git add src/models/incremental_json_database.py tests/test_incremental_db_go_delegation.py
git commit -m "refactor(Phase 9C): IncrementalJSONDB add_video/delete_video 委派 Go"
```

---

## Phase 9D：文件收尾

### Task 9D-1：更新 wiki

- [x] **Step 1：更新 wiki/log.md**

加入 Phase 9 完成記錄（格式同前，最新在上）。

- [x] **Step 2：更新 wiki/architecture/go-bridge.md 進度表**

在遷移進度表末尾加入：

```markdown
| Phase 9A | e2e 整合測試（db/cache/identify/scan/bridge） | ✅ 完成 |
| Phase 9B | GoBridgeError 語意細化（ExecError/NotFoundError/JSONError） | ✅ 完成 |
| Phase 9C | IncrementalJSONDB add_video/delete_video 委派 Go | ✅ 完成 |
```

- [x] **Step 3：產生 wiki-data.js**

```powershell
python3 wiki/gen_data.py
```

> commit / push 由人工或後續流程處理，避免在文件收尾階段混入非文件變更。

---

## 執行順序

```
9A-1 → 9A-2 → 9A-3 → 9A-4   （e2e 測試，不改 src）
        ↓
9B-1 → 9B-2                   （go_runner + 呼叫方，需 9A 通過確認後進行）
        ↓
9C-1 → 9C-2                   （IncrementalJSONDB，獨立，可與 9B 並行）
        ↓
9D-1                           （文件，最後）
```

---

## 完成標準

- [ ] `python -m pytest tests/ -x --tb=short -q` — 全部 PASSED
- [ ] `python -m pytest tests/integration/ -v` — 全部 PASSED（需 classifier.exe）
- [ ] `go test ./pkg/... -short` — 全部 PASSED
- [ ] OpenClaw 三大缺口全部關閉：e2e ✅、語意清晰 ✅、雙份業務邏輯 ✅

---

## 預估影響

| Phase | 新增測試數 | 程式碼異動 |
|-------|-----------|----------|
| 9A | ~15 個 e2e 測試 | 新建 3 個測試檔 |
| 9B | ~6 個 unit 測試 | go_runner.py +15 行，json_database.py 微修 |
| 9C | ~2 個 delegation 測試 | incremental_json_database.py -20 行（移除 Python journal 邏輯） |
