# Tasks: `safe_request` 重構（Cognitive Complexity 38 → <15）

**目標檔案**：`src/services/safe_javdb_searcher.py`
**目標函式**：`safe_request` (L240–L321)
**設計決策**：六個 helper 統一簽名 `-> int | None`
- `None` = 放棄（caller 應立即 `return None`）
- `int` = 下一輪的 `current_retry` 值（caller 設定後讓 `while True` 迴圈繼續）

---

## 契約保留清單（實作完成後逐項對照）

- [ ] `safe_request` 對外簽名不變：`(self, url: str, retry_count: int = 0) -> Any | None`
- [ ] 永不 raise，所有錯誤仍在內部吞掉
- [ ] 副作用順序不動：`_prepare_request_context` → `_apply_cooldown_if_needed` → `_calculate_request_delay` + `time.sleep` → `session.get()` → `_record_request_sent` → status 判斷
- [ ] 200 的 `_reset_consecutive_errors()` 位置不動
- [ ] 403 log 含 `_increment_consecutive_errors()` 回傳的連續錯誤次數
- [ ] 403 retry 前仍呼叫 `_recreate_session()`
- [ ] 429 log 不含連續錯誤次數（原本就沒捕捉回傳值）
- [ ] Timeout 達上限只保留最初的 warning，不補 error log
- [ ] ConnectError 重試前 `time.sleep(10 + current_retry * 5)` 指數退避
- [ ] Exception 路徑用 `logger.error`
- [ ] 日限觸發（`_prepare_request_context` 回傳 `None`）直接 return，不 retry
- [ ] 鎖的粒度不變：helper 不持有 `self._lock`，state 更新仍走 `_increment_consecutive_errors` 等子函式

---

## Step 1 — 新增六個 helper

放在 `_recreate_session` (L374) 之後、`clear_cache_for_code` (L378) 之前。

```python
def _handle_error_status(self, status: int, current_retry: int) -> int | None:
    if status == 403:
        return self._handle_403(current_retry)
    if status == 429:
        return self._handle_429(current_retry)
    logger.warning(f"⚠️ JAVDB 請求失敗: {status}")
    return None

def _handle_403(self, current_retry: int) -> int | None:
    consecutive_errors = self._increment_consecutive_errors()
    logger.warning(f"⚠️ 收到 403,連續錯誤 {consecutive_errors} 次")
    if current_retry < 2:
        wait_time = 30 + _random_delay(15, 45)
        if wait_time <= self.max_retry_wait_seconds:
            self._recreate_session()
            logger.info(f"🔄 更換瀏覽器指紋,等待 {wait_time:.1f} 秒後重試...")
            time.sleep(wait_time)
            return current_retry + 1
    logger.error("❌ 403 重試失敗,JAVDB 可能需要更強的反爬蟲策略")
    return None

def _handle_429(self, current_retry: int) -> int | None:
    self._increment_consecutive_errors()
    if current_retry < 3:
        wait_time = 20 + _random_delay(10, 30)
        if wait_time <= self.max_retry_wait_seconds:
            logger.warning(f"⚠️ 收到 429,等待 {wait_time:.1f} 秒後重試...")
            time.sleep(wait_time)
            return current_retry + 1
    logger.error("❌ 429 重試次數過多,放棄請求")
    return None

def _handle_timeout_error(self, current_retry: int) -> int | None:
    logger.warning("⏰ JAVDB 請求超時")
    self._increment_consecutive_errors()
    if current_retry < 2:
        return current_retry + 1
    return None

def _handle_connect_error(self, current_retry: int) -> int | None:
    logger.warning("🔌 JAVDB 連線失敗")
    self._increment_consecutive_errors()
    if current_retry < 2:
        time.sleep(10 + current_retry * 5)
        return current_retry + 1
    return None

def _handle_unknown_error(self, e: Exception, current_retry: int) -> int | None:
    logger.error(f"❌ JAVDB 請求過程中出錯: {e}")
    self._increment_consecutive_errors()
    if current_retry < 1:
        time.sleep(5)
        return current_retry + 1
    return None
```

---

## Step 2 — 替換 `safe_request` 主體

把 L240–L321 整個函式替換為：

```python
def safe_request(self, url: str, retry_count: int = 0) -> Any | None:
    """安全的 HTTP 請求方法（支援 curl_cffi 和 httpx 雙引擎）"""
    current_retry = retry_count

    while True:
        try:
            session, consecutive_errors = self._prepare_request_context()
            if session is None:
                return None
            session = self._apply_cooldown_if_needed(session, consecutive_errors)
            time.sleep(self._calculate_request_delay(consecutive_errors, current_retry))

            response = session.get(url)
            self._record_request_sent()
            status = response.status_code

            if status == 200:
                self._reset_consecutive_errors()
                logger.debug("✅ JAVDB 請求成功: %s", status)
                return response

            next_retry = self._handle_error_status(status, current_retry)
            if next_retry is None:
                return None
            current_retry = next_retry

        except httpx.TimeoutException:
            next_retry = self._handle_timeout_error(current_retry)
            if next_retry is None:
                return None
            current_retry = next_retry

        except httpx.ConnectError:
            next_retry = self._handle_connect_error(current_retry)
            if next_retry is None:
                return None
            current_retry = next_retry

        except Exception as e:
            next_retry = self._handle_unknown_error(e, current_retry)
            if next_retry is None:
                return None
            current_retry = next_retry
```

---

## Step 3 — 驗證

### 3.1 必須通過的既有測試（`tests/test_safe_javdb_searcher.py`）

- [ ] `test_403_retry_wait_over_limit_should_give_up_without_long_sleep` — 驗證 `wait_time > max_retry_wait_seconds` 時直接放棄、不長 sleep
- [ ] `test_403_retry_can_reenter_without_deadlock` — 驗證 sleep 序列 `[0.0, 30.0, 2.0]`
- [ ] `test_create_session_closes_previous_client` — 此測試與重構無關,但必須仍綠
- [ ] `test_consecutive_errors_trigger_cooldown_and_reset` — 驗證連續錯誤達 5 時 cooldown 並重置
- [ ] `test_safe_request_does_not_hold_lock_during_cooldown_sleep` — 驗證 cooldown 期間不持有 lock
- [ ] `test_search_javdb_no_fallback_on_mismatch` — mock `safe_request` 的行為契約
- [ ] `test_search_javdb_detail_page_code_mismatch_returns_none` — 同上

### 3.2 執行指令

```powershell
# 單元測試
python -m pytest tests\test_safe_javdb_searcher.py -q -p no:cacheprovider

# 全量測試
python -m pytest tests\ -q -p no:cacheprovider

# Sonar 驗證（依專案實際 CI 設定）
# 確認 safe_request 與六個 helper 的 CC 都 < 15
```

---

## Step 4 — Rollback 方案

若測試失敗或 production 出現回歸：

```powershell
git revert <commit-sha>
```

此重構**無新增依賴、無新增狀態欄位、無新增外部行為**，revert 後立即回到原狀,無需額外 cleanup。

---

## 預估 CC 結果

| 函式 | 預估 CC |
|---|---|
| `safe_request` | ~10 |
| `_handle_error_status` | ~3 |
| `_handle_403` | ~3 |
| `_handle_429` | ~3 |
| `_handle_timeout_error` | ~2 |
| `_handle_connect_error` | ~2 |
| `_handle_unknown_error` | ~2 |

全部應低於 15（需 Sonar 實測確認）。

---

## 注意事項

1. **不要複製「討論記錄」裡的第一份草稿**,該版本用的是 `tuple[bool, int]`,是被否決的舊設計
2. **不要合併 helper**：`_handle_error_status` 看似只 dispatch,但它讓主迴圈三個 `except` 分支結構完全對稱,合併回去會讓 CC 再爬上來
3. **`_handle_unknown_error` 的 `e` 參數不可省**：`logger.error` 需要包含 exception 訊息,否則會丟失錯誤上下文
