#!/usr/bin/env pwsh
# Actress Classifier - Rate Limiter Build Automation (PowerShell)
# Usage: ./build.ps1 -Target test
# or: ./build.ps1 test

param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'test', 'test-race', 'test-cover', 'test-integration', 'bench', 'lint', 'fmt', 'build', 'clean', 'all-checks', 'dev')]
    [string]$Target = 'help'
)

$ErrorActionPreference = 'Stop'

function Show-Help {
    @"
Actress Classifier - Rate Limiter Build Targets

Testing:
  ./build.ps1 test              - Run all unit tests
  ./build.ps1 test-race         - Run race condition detector
  ./build.ps1 test-cover        - Run tests with coverage report
  ./build.ps1 test-integration  - Run integration tests

Code Quality:
  ./build.ps1 bench             - Run performance benchmarks
  ./build.ps1 lint              - Run golangci-lint static analysis
  ./build.ps1 fmt               - Format code (gofmt + goimports)

Maintenance:
  ./build.ps1 build             - Build module
  ./build.ps1 clean             - Clean build artifacts

Workflows:
  ./build.ps1 all-checks        - Complete quality checks
  ./build.ps1 dev               - Developer workflow
"@
}

function Invoke-Test {
    Write-Host "`n🧪 Running unit tests..." -ForegroundColor Cyan
    & go test -v ./internal/ratelimit
}

function Invoke-TestRace {
    Write-Host "`n🔍 Running race detector..." -ForegroundColor Cyan
    & go test -v -race ./internal/ratelimit
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Unit tests failed" -ForegroundColor Red
        exit 1
    }
    
    & go test -v -race ./tests/integration
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Integration tests failed" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "✅ No race conditions detected" -ForegroundColor Green
}

function Invoke-TestCover {
    Write-Host "`n📊 Running tests with coverage analysis..." -ForegroundColor Cyan
    & go test ./internal/ratelimit -coverprofile=coverage.out -covermode=atomic
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Tests failed" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "✅ Coverage report generated (coverage.out)" -ForegroundColor Green
}

function Invoke-TestIntegration {
    Write-Host "`n🔗 Running integration tests..." -ForegroundColor Cyan
    & go test -v ./tests/integration
}

function Invoke-Bench {
    Write-Host "`n⚡ Running performance benchmarks..." -ForegroundColor Cyan
    & go test ./internal/ratelimit -bench=. -benchmem -run='^$'
}

function Invoke-Lint {
    Write-Host "`n📝 Running golangci-lint..." -ForegroundColor Cyan
    & golangci-lint run ./internal/ratelimit ./tests/integration
}

function Invoke-Format {
    Write-Host "`n✨ Formatting code..." -ForegroundColor Cyan
    & gofmt -w ./internal/ratelimit ./tests/integration
    Write-Host "✅ Code formatted" -ForegroundColor Green
}

function Invoke-Build {
    Write-Host "`n🔨 Building module..." -ForegroundColor Cyan
    & go build ./internal/ratelimit
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Build failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Build successful" -ForegroundColor Green
}

function Invoke-Clean {
    Write-Host "`n🧹 Cleaning build artifacts..." -ForegroundColor Cyan
    Remove-Item -Force coverage.out -ErrorAction SilentlyContinue
    Remove-Item -Force coverage.html -ErrorAction SilentlyContinue
    & go clean ./internal/ratelimit ./tests/integration
    Write-Host "✅ Clean complete" -ForegroundColor Green
}

function Invoke-AllChecks {
    Write-Host "`n🔄 Running all quality checks..." -ForegroundColor Cyan
    Invoke-Test
    if ($LASTEXITCODE -ne 0) { exit 1 }
    
    Invoke-TestRace
    if ($LASTEXITCODE -ne 0) { exit 1 }
    
    Invoke-TestCover
    if ($LASTEXITCODE -ne 0) { exit 1 }
    
    Invoke-Lint
    if ($LASTEXITCODE -ne 0) { exit 1 }
    
    Write-Host "`n✅ All quality checks passed!" -ForegroundColor Green
}

function Invoke-Dev {
    Write-Host "`n🔄 Running developer workflow..." -ForegroundColor Cyan
    Invoke-Format
    if ($LASTEXITCODE -ne 0) { exit 1 }
    
    Invoke-Test
    if ($LASTEXITCODE -ne 0) { exit 1 }
    
    Invoke-Lint
    if ($LASTEXITCODE -ne 0) { exit 1 }
    
    Write-Host "`n✅ Development workflow complete!" -ForegroundColor Green
}

# Execute target
switch ($Target) {
    'help' { Show-Help }
    'test' { Invoke-Test }
    'test-race' { Invoke-TestRace }
    'test-cover' { Invoke-TestCover }
    'test-integration' { Invoke-TestIntegration }
    'bench' { Invoke-Bench }
    'lint' { Invoke-Lint }
    'fmt' { Invoke-Format }
    'build' { Invoke-Build }
    'clean' { Invoke-Clean }
    'all-checks' { Invoke-AllChecks }
    'dev' { Invoke-Dev }
    default { Show-Help }
}
