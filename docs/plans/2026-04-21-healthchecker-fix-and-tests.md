# HealthChecker 修復與測試覆蓋實作計畫

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 修復 HealthChecker._start_health_check_task 的靜默 bug、補齊遺漏的 base_scraper 測試檔、並降低 update_domain_health 的 cognitive complexity。

**Architecture:** 採 TDD 方式逐層修復——先補測試確認 bug 存在，再修實作，最後重構降低複雜度。三個 Task 互相獨立，可依序執行。

**Tech Stack:** Python 3.12、pytest、asyncio、src/scrapers/base_scraper.py、tests/test_coverage_base_scraper.py

---

## Task 1：修復 `_start_health_check_task` 靜默 bug

**Objective:** `_start_health_check_task` 取得 event loop 後從未呼叫 `create_task()`，背景健康檢查根本不會啟動，卻不報錯。

**Files:**
- Modify: `src/scrapers/base_scraper.py`（`_start_health_check_task` 方法，約行 310–330）
- Test: `tests/test_coverage_base_scraper.py`（新建）

---

**Step 1：建立測試檔，寫失敗測試**

建立 `tests/test_coverage_base_scraper.py`，加入以下測試：

```python
"""base_scraper.HealthChecker 測試"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.scrapers.base_scraper import HealthChecker, HealthCheckConfig


def test_start_health_check_task_schedules_coroutine(event_loop):
    """_start_health_check_task 應該在 event loop 上排程背景任務"""
    scheduled_tasks = []

    config = HealthCheckConfig(enable_auto_recovery=True)
    hc = HealthChecker.__new__(HealthChecker)  # 繞過 __init__ 避免提早觸發
    hc.config = config
    hc.domain_health = {}
    hc.lock = asyncio.Lock()

    with patch.object(event_loop, "create_task", side_effect=lambda coro: scheduled_tasks.append(coro)) as mock_create:
        with patch("asyncio.get_running_loop", return_value=event_loop):
            hc._start_health_check_task()

    assert mock_create.called, "_start_health_check_task 應呼叫 loop.create_task()"
    assert len(scheduled_tasks) == 1
```

**Step 2：確認測試失敗**

```
pytest tests/test_coverage_base_scraper.py::test_start_health_check_task_schedules_coroutine -v
```
預期：**FAIL** — AssertionError: `_start_health_check_task` 應呼叫 `loop.create_task()`

---

**Step 3：修復實作**

在 `src/scrapers/base_scraper.py` 的 `_start_health_check_task` 方法，把取得 loop 後的空白補上 `create_task`：

```python
def _start_health_check_task(self):
    """啟動背景健康檢查任務"""

    async def health_check_worker():
        while True:
            try:
                await asyncio.sleep(self.config.check_interval)
                for domain in tuple(self.domain_health):
                    is_healthy = await self.check_domain_health(domain)
                    await self.update_domain_health(domain, is_healthy)
            except Exception as e:
                logger.error(f"健康檢查任務失敗: {e}")

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(health_check_worker())      # ← 這行是修復的關鍵
    except RuntimeError:
        logger.debug("⚠️ 無執行中的事件迴圈，略過自動健康檢查背景任務")
```

**Step 4：確認測試通過**

```
pytest tests/test_coverage_base_scraper.py::test_start_health_check_task_schedules_coroutine -v
```
預期：**PASS**

**Step 5：Commit**

```bash
git add src/scrapers/base_scraper.py tests/test_coverage_base_scraper.py
git commit -m "fix: HealthChecker._start_health_check_task 補上 loop.create_task() 呼叫"
```

---

## Task 2：補齊 HealthChecker 基本測試覆蓋

**Objective:** `tests/test_coverage_base_scraper.py` 目前只有一個測試；補齊 `update_domain_health`、`is_domain_healthy`、`check_domain_health` 的正常/邊界路徑覆蓋。

**Files:**
- Modify: `tests/test_coverage_base_scraper.py`

---

**Step 1：在 Task 1 測試檔末尾追加以下測試**

```python
@pytest.mark.asyncio
async def test_update_domain_health_marks_unhealthy_after_threshold():
    """連續失敗達到 failure_threshold 後，域名應被標記不健康"""
    config = HealthCheckConfig(failure_threshold=2, recovery_threshold=2)
    hc = HealthChecker(config)

    domain = "example.com"
    await hc.update_domain_health(domain, is_healthy=False)
    assert hc.domain_health[domain]["healthy"] is True  # 第一次失敗，尚未達門檻

    await hc.update_domain_health(domain, is_healthy=False)
    assert hc.domain_health[domain]["healthy"] is False  # 第二次，應標記不健康


@pytest.mark.asyncio
async def test_update_domain_health_recovers_after_threshold():
    """連續成功達到 recovery_threshold 後，域名應恢復健康"""
    config = HealthCheckConfig(failure_threshold=1, recovery_threshold=2)
    hc = HealthChecker(config)

    domain = "example.com"
    await hc.update_domain_health(domain, is_healthy=False)  # 標記不健康
    await hc.update_domain_health(domain, is_healthy=True)   # 第一次成功
    assert hc.domain_health[domain]["healthy"] is False       # 尚未恢復

    await hc.update_domain_health(domain, is_healthy=True)   # 第二次成功
    assert hc.domain_health[domain]["healthy"] is True        # 應恢復


def test_is_domain_healthy_unknown_domain_returns_true():
    """未知域名預設為健康"""
    hc = HealthChecker()
    assert hc.is_domain_healthy("unknown.example.com") is True


def test_is_domain_healthy_known_unhealthy_domain():
    """已知不健康域名應回傳 False"""
    hc = HealthChecker()
    hc.domain_health["bad.com"] = {
        "healthy": False,
        "consecutive_failures": 3,
        "consecutive_successes": 0,
        "last_check": 0,
        "total_checks": 3,
        "total_failures": 3,
    }
    assert hc.is_domain_healthy("bad.com") is False


@pytest.mark.asyncio
async def test_check_domain_health_returns_false_on_exception():
    """當 aiohttp 拋出例外時，check_domain_health 應安全回傳 False"""
    hc = HealthChecker()
    with patch("aiohttp.ClientSession") as mock_session:
        mock_session.side_effect = Exception("network error")
        result = await hc.check_domain_health("unreachable.example.com")
    assert result is False
```

**Step 2：跑測試確認全部通過**

```
pytest tests/test_coverage_base_scraper.py -v
```
預期：**5 passed**（含 Task 1 那一個）

**Step 3：Commit**

```bash
git add tests/test_coverage_base_scraper.py
git commit -m "test: 補齊 HealthChecker update/is_domain_healthy/check_domain_health 覆蓋"
```

---

## Task 3：降低 `update_domain_health` 的 cognitive complexity

**Objective:** `update_domain_health` 方法內有雙層 if/else 巢狀條件，Sonar 計算 cognitive complexity 偏高。提取兩個私有 helper 方法降低主方法複雜度。

**Files:**
- Modify: `src/scrapers/base_scraper.py`（`update_domain_health` 及新增兩個 helper）

---

**Step 1：確認現有測試仍能通過（回歸基準）**

```
pytest tests/test_coverage_base_scraper.py -v
```
預期：**5 passed**（確保重構前測試是綠的）

---

**Step 2：提取 helper 方法，重構 `update_domain_health`**

在 `update_domain_health` 同一個 class 內，新增兩個私有方法：

```python
def _apply_healthy_update(self, health_info: dict) -> None:
    """處理成功回應：遞增連續成功數，若達門檻則恢復健康"""
    health_info["consecutive_successes"] += 1
    health_info["consecutive_failures"] = 0

    if (
        not health_info["healthy"]
        and health_info["consecutive_successes"] >= self.config.recovery_threshold
    ):
        health_info["healthy"] = True
        domain = health_info.get("_domain_hint", "?")
        logger.info(f"✅ 域名 {domain} 已恢復健康")


def _apply_unhealthy_update(self, health_info: dict) -> None:
    """處理失敗回應：遞增連續失敗數，若達門檻則標記不健康"""
    health_info["consecutive_failures"] += 1
    health_info["consecutive_successes"] = 0
    health_info["total_failures"] += 1

    if (
        health_info["healthy"]
        and health_info["consecutive_failures"] >= self.config.failure_threshold
    ):
        health_info["healthy"] = False
        domain = health_info.get("_domain_hint", "?")
        logger.warning(f"⚠️ 域名 {domain} 被標記為不健康")
```

將 `update_domain_health` 改為：

```python
async def update_domain_health(self, domain: str, is_healthy: bool):
    """更新域名健康狀態"""
    async with self.lock:
        if domain not in self.domain_health:
            self.domain_health[domain] = {
                "healthy": True,
                "consecutive_failures": 0,
                "consecutive_successes": 0,
                "last_check": time.time(),
                "total_checks": 0,
                "total_failures": 0,
                "_domain_hint": domain,   # 供 helper 使用，不影響外部行為
            }

        health_info = self.domain_health[domain]
        health_info["last_check"] = time.time()
        health_info["total_checks"] += 1

        if is_healthy:
            self._apply_healthy_update(health_info)
        else:
            self._apply_unhealthy_update(health_info)
```

**Step 3：重跑測試確認行為不變**

```
pytest tests/test_coverage_base_scraper.py -v
```
預期：**5 passed**（行為完全不變）

**Step 4：補一個針對 helper 的直接測試（optional but good）**

```python
def test_apply_healthy_update_increments_successes():
    hc = HealthChecker()
    info = {"healthy": False, "consecutive_successes": 1, "consecutive_failures": 2,
            "total_failures": 2, "_domain_hint": "test.com"}
    hc.config = HealthCheckConfig(recovery_threshold=2)
    hc._apply_healthy_update(info)
    assert info["consecutive_successes"] == 2
    assert info["consecutive_failures"] == 0
    assert info["healthy"] is True   # 達到 recovery_threshold=2

def test_apply_unhealthy_update_increments_failures():
    hc = HealthChecker()
    info = {"healthy": True, "consecutive_failures": 1, "consecutive_successes": 0,
            "total_failures": 1, "_domain_hint": "test.com"}
    hc.config = HealthCheckConfig(failure_threshold=2)
    hc._apply_unhealthy_update(info)
    assert info["consecutive_failures"] == 2
    assert info["healthy"] is False  # 達到 failure_threshold=2
```

**Step 5：最終跑全部 base_scraper 測試**

```
pytest tests/test_coverage_base_scraper.py -v
```
預期：**7 passed**

**Step 6：Commit**

```bash
git add src/scrapers/base_scraper.py tests/test_coverage_base_scraper.py
git commit -m "refactor: 提取 _apply_healthy/unhealthy_update 降低 update_domain_health cognitive complexity"
```

---

## 驗收條件

- [ ] `pytest tests/test_coverage_base_scraper.py -v` → 7 passed, 0 failed
- [ ] `pytest tests/` → 整體測試無回歸
- [ ] `src/scrapers/base_scraper.py` 的 `HealthChecker._start_health_check_task` 有 `loop.create_task()` 呼叫
- [ ] `update_domain_health` 方法本體行數 ≤ 15 行（提取後）
