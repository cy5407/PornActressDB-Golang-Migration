@echo off
REM Actress Classifier - Rate Limiter Build Targets (Windows Batch)
REM Usage: run.bat [target]

setlocal enabledelayedexpansion

if "%1"=="" goto help
if "%1"=="help" goto help
if "%1"=="test" goto test
if "%1"=="test-race" goto test_race
if "%1"=="test-cover" goto test_cover
if "%1"=="test-integration" goto test_integration
if "%1"=="bench" goto bench
if "%1"=="lint" goto lint
if "%1"=="fmt" goto fmt
if "%1"=="build" goto build
if "%1"=="clean" goto clean
if "%1"=="all-checks" goto all_checks
if "%1"=="dev" goto dev

echo Error: Unknown target "%1%"
goto help

:help
echo.
echo Actress Classifier - Rate Limiter Build Targets
echo.
echo Testing:
echo   run.bat test         - 執行所有單元測試
echo   run.bat test-race    - 執行並發競態條件檢測
echo   run.bat test-cover   - 執行測試並生成覆蓋率報告
echo   run.bat test-integration - 執行整合測試
echo.
echo Code Quality:
echo   run.bat bench        - 執行效能基準測試
echo   run.bat lint         - 執行 golangci-lint 靜態分析
echo   run.bat fmt          - 格式化程式碼 (gofmt + goimports)
echo.
echo Maintenance:
echo   run.bat build        - 建構模組
echo   run.bat clean        - 清理產物
echo.
echo Workflows:
echo   run.bat all-checks   - 完整品質檢查
echo   run.bat dev          - 開發者工作流程
echo.
goto end

:test
echo.
echo 🧪 Running unit tests...
go test -v ./internal/ratelimit
goto end

:test_race
echo.
echo 🔍 Running race detector...
go test -v -race ./internal/ratelimit
if errorlevel 1 (
    echo ❌ Unit tests failed
    exit /b 1
)
go test -v -race ./tests/integration
if errorlevel 1 (
    echo ❌ Integration tests failed
    exit /b 1
)
echo ✅ No race conditions detected
goto end

:test_cover
echo.
echo 📊 Running tests with coverage analysis...
go test ./internal/ratelimit -coverprofile=coverage.out -covermode=atomic
if errorlevel 1 (
    echo ❌ Tests failed
    exit /b 1
)
echo ✅ Coverage report generated (coverage.out)
goto end

:test_integration
echo.
echo 🔗 Running integration tests...
go test -v ./tests/integration
goto end

:bench
echo.
echo ⚡ Running performance benchmarks...
go test ./internal/ratelimit -bench=. -benchmem -run=^$
goto end

:lint
echo.
echo 📝 Running golangci-lint...
golangci-lint run ./internal/ratelimit ./tests/integration
goto end

:fmt
echo.
echo ✨ Formatting code...
gofmt -w ./internal/ratelimit ./tests/integration
echo ✅ Code formatted
goto end

:build
echo.
echo 🔨 Building module...
go build ./internal/ratelimit
if errorlevel 1 (
    echo ❌ Build failed
    exit /b 1
)
echo ✅ Build successful
goto end

:clean
echo.
echo 🧹 Cleaning build artifacts...
if exist coverage.out del /f coverage.out
if exist coverage.html del /f coverage.html
go clean ./internal/ratelimit ./tests/integration
echo ✅ Clean complete
goto end

:all_checks
echo.
echo 🔄 Running all quality checks...
call :test
if errorlevel 1 goto fail
call :test_race
if errorlevel 1 goto fail
call :test_cover
if errorlevel 1 goto fail
call :lint
if errorlevel 1 goto fail
echo.
echo ✅ All quality checks passed!
goto end

:dev
echo.
echo 🔄 Running development workflow...
call :fmt
if errorlevel 1 goto fail
call :test
if errorlevel 1 goto fail
call :lint
if errorlevel 1 goto fail
echo.
echo ✅ Development workflow complete!
goto end

:fail
echo.
echo ❌ Build failed
exit /b 1

:end
