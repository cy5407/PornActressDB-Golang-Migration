# JAVDB 403 修復任務清單

**建立日期**: 2026-04-03
**更新日期**: 2026-04-03
**關聯報告**: [JAVDB_403_ERROR_ANALYSIS.md](./JAVDB_403_ERROR_ANALYSIS.md)

---

## Task 0：引入 curl_cffi 取代 httpx 繞過 Cloudflare [Critical — 根治 403]

**目的**: JAVDB 使用 Cloudflare 反爬蟲，httpx 的 TLS 指紋被識別為非瀏覽器導致 403。
curl_cffi 能模擬真實瀏覽器的 TLS/JA3/HTTP2 指紋，不需要開瀏覽器，輕量且快速。

**新增依賴**: `curl_cffi>=0.7.0`

### Step 0-1：安裝 curl_cffi

```bash
pip install curl_cffi>=0.7.0
```

在 `requirements.txt` 新增一行：
```
curl_cffi>=0.7.0        # 模擬瀏覽器 TLS 指紋，繞過 Cloudflare 反爬蟲
```

### Step 0-2：修改 safe_javdb_searcher.py — import 區塊

將：
```python
import httpx
```

改為：
```python
# 優先使用 curl_cffi 模擬瀏覽器 TLS 指紋繞過 Cloudflare
try:
    from curl_cffi import requests as cffi_requests  # curl_cffi HTTP 客戶端
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

import httpx  # fallback HTTP 客戶端
```

### Step 0-3：修改 create_session() — 建立 curl_cffi Session

將原本的 `httpx.Client` 建立邏輯替換為 curl_cffi 優先：

```python
def create_session(self):
    """建立模擬真實瀏覽器的 session（優先使用 curl_cffi）"""
    # 關閉舊 session
    previous_session = getattr(self, "session", None)
    if previous_session is not None and hasattr(previous_session, "close"):
        try:
            previous_session.close()
        except Exception as e:
            logger.warning(f"⚠️ 關閉舊 JAVDB session 失敗: {e}")

    # 瀏覽器指紋列表（curl_cffi impersonate 參數）
    browser_fingerprints = [
        "chrome124",   # Chrome 124
        "chrome120",   # Chrome 120
        "chrome119",   # Chrome 119
        "edge101",     # Edge 101
        "safari17_0",  # Safari 17.0
    ]

    # 共用 headers（兩種 session 都會用到）
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en-US;q=0.7,en;q=0.6",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }

    if HAS_CURL_CFFI:
        # === curl_cffi 模式：模擬瀏覽器 TLS 指紋 ===
        self._impersonate = secure_choice(browser_fingerprints)  # 隨機選擇瀏覽器指紋
        self.session = cffi_requests.Session(
            impersonate=self._impersonate,  # 模擬指定瀏覽器的 TLS/JA3 指紋
            headers=headers,
            timeout=30.0,
        )
        self._session_type = "curl_cffi"
        logger.info(f"🛡️ 使用 curl_cffi 建立 session - 指紋: {self._impersonate}")
    else:
        # === httpx fallback 模式 ===
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        ]
        headers["User-Agent"] = secure_choice(user_agents)

        # 隨機添加可選標頭
        if randbelow(2) == 1:
            headers["DNT"] = "1"
        if randbelow(2) == 1:
            headers["Referer"] = "https://www.google.com/"

        self.session = httpx.Client(
            headers=headers,
            follow_redirects=True,
            timeout=30.0,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            default_encoding="utf-8",
        )
        self._session_type = "httpx"
        logger.warning("⚠️ curl_cffi 不可用，使用 httpx fallback（TLS 指紋可能被 Cloudflare 偵測）")

    self.request_count = 0
```

### Step 0-4：修改 safe_request() — 統一請求介面

curl_cffi 和 httpx 的 response 物件 API 略有不同，需要統一處理：

```python
def safe_request(self, url: str, retry_count: int = 0):
    """安全的 HTTP 請求方法（支援 curl_cffi 和 httpx 雙引擎）"""
    with self._lock:
        # ... 既有的每日限制和 session 檢查邏輯保持不變 ...

        try:
            # 智能隨機延遲
            base_delay = _random_delay(self.min_delay, self.max_delay)
            if retry_count > 0:
                base_delay += retry_count * 2.0
            time.sleep(base_delay)

            # === 根據 session 類型發送請求 ===
            if self._session_type == "curl_cffi":
                response = self.session.get(url)  # curl_cffi 請求
            else:
                response = self.session.get(url)  # httpx 請求

            self.request_count += 1
            self.stats["today_count"] += 1
            self.stats["total_requests"] += 1

            # 取得狀態碼（兩種 client 的屬性名稱相同）
            status = response.status_code

            if status == 200:
                self.consecutive_errors = 0  # 成功時重置連續錯誤計數
                return response

            # --- 403 處理：換指紋重試 ---
            elif status == 403:
                self.consecutive_errors += 1
                logger.warning(f"⚠️ 收到 403，連續錯誤 {self.consecutive_errors} 次")

                if retry_count < 2:
                    self.create_session()  # 換一組瀏覽器指紋
                    wait_time = 30 + _random_delay(15, 45)  # 等待 45~75 秒
                    if wait_time <= self.max_retry_wait_seconds:
                        logger.info(f"🔄 更換瀏覽器指紋，等待 {wait_time:.1f} 秒後重試...")
                        time.sleep(wait_time)
                        return self.safe_request(url, retry_count + 1)
                logger.error("❌ 403 重試失敗，JAVDB 可能需要更強的反爬蟲策略")
                return None

            # --- 429 處理 ---
            elif status == 429:
                self.consecutive_errors += 1
                if retry_count < 3:
                    wait_time = 20 + _random_delay(10, 30)  # 等待 30~50 秒
                    if wait_time <= self.max_retry_wait_seconds:
                        logger.warning(f"⚠️ 收到 429，等待 {wait_time:.1f} 秒後重試...")
                        time.sleep(wait_time)
                        return self.safe_request(url, retry_count + 1)
                return None

            else:
                logger.warning(f"⚠️ JAVDB 請求失敗: {status}")
                return None

        except Exception as e:
            logger.error(f"❌ JAVDB 請求過程中出錯: {e}")
            if retry_count < 1:
                time.sleep(5)
                return self.safe_request(url, retry_count + 1)
            return None
```

### Step 0-5：首次請求前先暖機（取得 Cloudflare Cookie）

在 `__init__` 最後加入首頁暖機：

```python
# 暖機：先訪問首頁取得 Cloudflare cookie
self._warmup()
```

新增方法：
```python
def _warmup(self):
    """訪問 JAVDB 首頁取得 Cloudflare cf_clearance cookie"""
    try:
        logger.info("🔥 JAVDB 首頁暖機中...")
        time.sleep(_random_delay(1.0, 2.0))  # 短暫延遲模擬人類行為

        if self._session_type == "curl_cffi":
            resp = self.session.get("https://javdb.com")  # 訪問首頁取得 cookie
        else:
            resp = self.session.get("https://javdb.com")

        if resp.status_code == 200:
            logger.info("✅ JAVDB 首頁暖機成功，已取得 session cookie")
        else:
            logger.warning(f"⚠️ JAVDB 首頁回應 {resp.status_code}，暖機可能失敗")
    except Exception as e:
        logger.warning(f"⚠️ JAVDB 首頁暖機失敗: {e}")
```

### Step 0-6：驗證

```bash
# 1. 確認 curl_cffi 安裝成功
python -c "from curl_cffi import requests; print('curl_cffi OK')"

# 2. 測試 JAVDB 連線（應該不再 403）
python -c "
from curl_cffi import requests
resp = requests.get('https://javdb.com', impersonate='chrome124')
print(f'Status: {resp.status_code}')
print(f'Title: {resp.text[:200]}')
"

# 3. 測試完整搜尋器初始化
python -c "
import sys; sys.path.insert(0, 'src')
from services.safe_javdb_searcher import SafeJAVDBSearcher
s = SafeJAVDBSearcher()
print(f'Session type: {s._session_type}')
print(f'max_retry_wait: {s.max_retry_wait_seconds}')
"
```

---

## Task 1：修復 403/429 重試等待時間邏輯 [Critical]

**檔案**: `src/services/safe_javdb_searcher.py`

**問題**: `max_retry_wait_seconds = 60` 但 403 等待時間計算為 180~300 秒，重試永遠被跳過。

> 注意：Task 0 的 `safe_request()` 改寫已包含此修復。若 Task 0 已完成，本 Task 僅需驗證。

**修復要點**:
1. `max_retry_wait_seconds` 調高為 `300.0`
2. 403 等待時間：`30 + random(15, 45)` = 45~75 秒（原本 180~300 秒）
3. 429 等待時間：`20 + random(10, 30)` = 30~50 秒（原本 90~150 秒）
4. 新增 `self.consecutive_errors` 連續錯誤計數器
5. 成功時重置計數器，失敗時遞增

**驗證**:
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from services.safe_javdb_searcher import SafeJAVDBSearcher
s = SafeJAVDBSearcher()
print(f'max_retry_wait: {s.max_retry_wait_seconds}')  # 應為 300.0
print(f'consecutive_errors: {s.consecutive_errors}')   # 應為 0
"
```

---

## Task 2：移除級聯搜尋中的 JAVDB 階段 [Medium]

**檔案**: `src/services/web_searcher.py`, `src/ui/main_gui.py`, `src/services/classifier_core.py`

**修改內容**:

1. **`web_searcher.py`** — `batch_cascade_search()` 方法：
   - 移除 `enable_javdb` 參數（或固定為 False）
   - 移除「第三階段：JAVDB 備援搜尋」的整段邏輯
   - 更新進度訊息，移除「第三階段」相關文字

2. **`main_gui.py`** — `_japanese_search_worker()` 方法：
   - 直接呼叫 AV-WIKI 搜尋，不再走級聯路徑的 JAVDB 部分
   - 更新 UI 標題文字：「AV-WIKI → JAVDB 自動備援」→「AV-WIKI 批次搜尋 + JAVDB 獨立搜尋」
   - 移除級聯搜尋勾選框（`cascade_var`、`cascade_check`），因為沒有 JAVDB 備援後級聯只有一層

3. **`classifier_core.py`** — `process_and_search_cascade()` 方法：
   - 移除 JAVDB 相關邏輯或將 `enable_cascade` 預設改為 False

**注意**: 不要動到 `start_javdb_search`、`_javdb_search_worker`、`process_and_search_javdb`、`search_javdb_only` — 這些是獨立 JAVDB 按鈕的功能，必須保留。

**驗證**:
```bash
# 確認級聯搜尋不再觸發 JAVDB
grep -n "javdb\|JAVDB" src/services/web_searcher.py | grep -i cascade
# 確認獨立 JAVDB 按鈕仍正常
grep -n "search_javdb_only\|process_and_search_javdb" src/services/classifier_core.py
```

---

## Task 3：增加自適應速率控制 [Enhancement]

**檔案**: `src/services/safe_javdb_searcher.py`

> 注意：Task 0 已包含 `consecutive_errors` 基礎實作。本 Task 為進階版本。

**進階實作**:
```python
# 在 safe_request() 的延遲計算中加入指數退避：
adaptive_multiplier = 2 ** min(self.consecutive_errors, 5)  # 最大 32 倍
base_delay = _random_delay(self.min_delay, self.max_delay) * adaptive_multiplier

# 連續錯誤超過閾值時主動暫停整個 session：
if self.consecutive_errors >= 5:
    cooldown = 300  # 連續 5 次失敗後冷卻 5 分鐘
    logger.warning(f"🧊 連續 {self.consecutive_errors} 次失敗，冷卻 {cooldown} 秒")
    time.sleep(cooldown)
    self.create_session()  # 重建 session 換指紋
    self.consecutive_errors = 0
```

---

## Task 4：更新 GUI 文字與搜尋選項 [Low]

**檔案**: `src/ui/main_gui.py`

**修改內容**:
- 標題列：「級聯搜尋版」→「智慧搜尋版」
- 副標題：「支援 AV-WIKI → JAVDB 自動備援」→「AV-WIKI 批次搜尋 + JAVDB 獨立搜尋」
- 移除「啟用級聯搜尋」勾選框（級聯只剩 AV-WIKI 一層，無需勾選）

---

## 執行順序

```
Task 0（curl_cffi 反爬蟲）  ← 根治 403，最高優先
  ↓
Task 1（重試邏輯修復）      ← Task 0 已涵蓋大部分，僅需驗證
  ↓
Task 2（移除級聯 JAVDB）    ← 減少不必要的 JAVDB 請求量
  ↓
Task 4（更新 GUI 文字）     ← 配合 Task 2 的 UI 調整
  ↓
Task 3（自適應速率控制）    ← 長期穩定性改善
```

---

## 變更紀錄

| 日期 | 變更內容 |
|------|---------|
| 2026-04-03 | 初版：Task 1~4 |
| 2026-04-03 | 新增 Task 0（curl_cffi 反爬蟲對策），調整執行順序 |
