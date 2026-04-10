# 女優分類系統 - 多階段建置 Dockerfile
# Task 3: 補充測試環境配置
#
# 階段一：Go 建置環境
FROM golang:1.25.0-bookworm AS go-builder

WORKDIR /build

# 複製 Go 模組定義（利用快取層）
COPY go.mod go.sum ./
RUN go mod download

# 複製 Go 原始碼
COPY cmd/ ./cmd/
COPY pkg/ ./pkg/

# 建置 classifier CLI
RUN go build -o classifier ./cmd/scanner

# 執行 Go 單元測試
RUN go test ./pkg/... -v -race -coverprofile=/tmp/go-coverage.out 2>&1 | tee /tmp/go-test-results.txt

# ─────────────────────────────────────────────
# 階段二：Python 執行環境 + Go CLI 整合
FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

# 複製 Go CLI 執行檔（from go-builder 階段）
COPY --from=go-builder /build/classifier ./classifier.exe
COPY --from=go-builder /tmp/go-coverage.out /tmp/go-coverage.out
COPY --from=go-builder /tmp/go-test-results.txt /tmp/go-test-results.txt

# 確保 classifier.exe 有執行權限（Task 9 相關）
RUN chmod +x ./classifier.exe

# 安裝系統相依（用於 tkinter 等 GUI 元件）
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-tk \
    && rm -rf /var/lib/apt/lists/*

# 複製 Python 相依清單並安裝（利用快取層）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案原始碼
COPY pkg/ ./pkg/
COPY src/ ./src/
COPY tests/ ./tests/
COPY tools/ ./tools/
COPY major_studios.json ./
COPY config.ini.example ./config.ini

# 建立必要的目錄結構
RUN mkdir -p data/json_db cache logs

# 設定環境變數
ENV PYTHONPATH=/app
ENV CLASSIFIER_EXE=/app/classifier.exe

# 預設命令：執行所有測試
CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]

# ─────────────────────────────────────────────
# 階段三（可選）：僅測試環境（不包含生產相依）
FROM runtime AS test

# 安裝測試專用工具
RUN pip install --no-cache-dir \
    pytest-xdist \
    pytest-timeout

# 設定測試執行命令
CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=long", "--timeout=60"]
