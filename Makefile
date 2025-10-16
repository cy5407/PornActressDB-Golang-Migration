.PHONY: help test test-race test-cover bench lint fmt clean build

# 預設目標
help:
	@echo "Actress Classifier - Rate Limiter Build Targets"
	@echo ""
	@echo "Testing:"
	@echo "  make test        - 執行所有單元測試"
	@echo "  make test-race   - 執行並發競態條件檢測"
	@echo "  make test-cover  - 執行測試並生成覆蓋率報告"
	@echo ""
	@echo "Code Quality:"
	@echo "  make bench       - 執行效能基準測試"
	@echo "  make lint        - 執行 golangci-lint 靜態分析"
	@echo "  make fmt         - 格式化程式碼 (gofmt + goimports)"
	@echo ""
	@echo "Maintenance:"
	@echo "  make build       - 建構模組"
	@echo "  make clean       - 清理產物"
	@echo ""

# 執行所有單元測試
test:
	@echo "🧪 Running unit tests..."
	go test -v ./internal/ratelimit

# 執行並發競態條件檢測
test-race:
	@echo "🔍 Running race detector..."
	go test -v -race ./internal/ratelimit
	go test -v -race ./tests/integration
	@echo "✅ No race conditions detected"

# 執行測試並生成覆蓋率報告
test-cover:
	@echo "📊 Running tests with coverage analysis..."
	go test ./internal/ratelimit -coverprofile=coverage.out -covermode=atomic
	@go tool cover -func=coverage.out | grep total
	@echo "✅ Coverage report generated (coverage.out)"

# 執行整合測試
test-integration:
	@echo "🔗 Running integration tests..."
	go test -v ./tests/integration

# 執行效能基準測試
bench:
	@echo "⚡ Running performance benchmarks..."
	go test ./internal/ratelimit -bench=. -benchmem -run=^$$

# 執行 golangci-lint 靜態分析
lint:
	@echo "📝 Running golangci-lint..."
	golangci-lint run ./internal/ratelimit ./tests/integration

# 格式化程式碼
fmt:
	@echo "✨ Formatting code..."
	gofmt -w ./internal/ratelimit ./tests/integration
	goimports -w ./internal/ratelimit ./tests/integration
	@echo "✅ Code formatted"

# 建構模組
build:
	@echo "🔨 Building module..."
	go build ./internal/ratelimit
	@echo "✅ Build successful"

# 清理產物
clean:
	@echo "🧹 Cleaning build artifacts..."
	rm -f coverage.out coverage.html
	go clean ./internal/ratelimit ./tests/integration
	@echo "✅ Clean complete"

# 完整品質檢查
all-checks: test test-race test-cover lint
	@echo ""
	@echo "✅ All quality checks passed!"

# 開發者工作流程：格式化 → 測試 → 檢查覆蓋率
dev: fmt test lint
	@echo ""
	@echo "✅ Development workflow complete!"
