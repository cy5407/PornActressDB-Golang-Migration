# ===============================================
# Copilot Agent 快速啟動別名
# ===============================================
# 使用方式：將此檔案內容加入 PowerShell Profile
# 指令：notepad $PROFILE
# ===============================================

Write-Host "🤖 載入 Copilot Agent 工具..." -ForegroundColor Cyan

# ==================== 測試相關 ====================

function Test-All {
    <#
    .SYNOPSIS
    執行完整的自動化測試驗證
    #>
    Write-Host "`n🧪 執行 Agent 自動驗證..." -ForegroundColor Cyan
    python .github\agent_verify.py
}
Set-Alias -Name ta -Value Test-All

function Test-Python {
    <#
    .SYNOPSIS
    僅執行 Python 測試
    #>
    Write-Host "`n🐍 執行 Python 測試..." -ForegroundColor Yellow
    python -m pytest tests/ -v --tb=short
}
Set-Alias -Name tp -Value Test-Python

function Test-Go {
    <#
    .SYNOPSIS
    僅執行 Go 測試
    #>
    Write-Host "`n🔷 執行 Go 測試..." -ForegroundColor Blue
    go test ./... -v
}
Set-Alias -Name tg -Value Test-Go

# ==================== 建構相關 ====================

function Build-CLI {
    <#
    .SYNOPSIS
    建構 Go CLI 工具
    #>
    Write-Host "`n🔨 建構 classifier.exe..." -ForegroundColor Green
    go build -o classifier.exe ./cmd/scanner
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ 建構成功！" -ForegroundColor Green
        Write-Host "執行: .\classifier.exe --help" -ForegroundColor Gray
    }
    else {
        Write-Host "❌ 建構失敗" -ForegroundColor Red
    }
}
Set-Alias -Name bc -Value Build-CLI

function Build-All {
    <#
    .SYNOPSIS
    執行完整編譯檢查（Go + Python 語法）
    #>
    Write-Host "`n🏗️ 執行完整編譯檢查..." -ForegroundColor Magenta

    Write-Host "`n[1/2] Go 編譯檢查..." -ForegroundColor Cyan
    go build ./...

    Write-Host "`n[2/2] Python 語法檢查..." -ForegroundColor Cyan
    Get-ChildItem -Path src -Filter *.py -Recurse | Select-Object -First 10 | ForEach-Object {
        python -m py_compile $_.FullName
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✓ $($_.Name)" -ForegroundColor Green
        }
        else {
            Write-Host "  ✗ $($_.Name)" -ForegroundColor Red
        }
    }
}
Set-Alias -Name ba -Value Build-All

# ==================== Agent 相關 ====================

function Agent-Check {
    <#
    .SYNOPSIS
    檢查 Agent 設定檔案是否完整
    #>
    Write-Host "`n🤖 檢查 Copilot Agent 設定..." -ForegroundColor Magenta

    $files = @(
        @{Path = ".github\copilot-instructions.md"; Name = "Agent 指令檔" },
        @{Path = ".vscode\settings.json"; Name = "VS Code 設定" },
        @{Path = ".github\COPILOT_TEMPLATES.md"; Name = "任務範本" },
        @{Path = ".github\AGENT_LOG.md"; Name = "任務記錄" },
        @{Path = ".github\agent_verify.py"; Name = "驗證腳本" }
    )

    $allExist = $true
    foreach ($file in $files) {
        if (Test-Path $file.Path) {
            Write-Host "  ✅ $($file.Name)" -ForegroundColor Green
        }
        else {
            Write-Host "  ❌ $($file.Name) (找不到)" -ForegroundColor Red
            $allExist = $false
        }
    }

    if ($allExist) {
        Write-Host "`n✅ Agent 設定完整！" -ForegroundColor Green
    }
    else {
        Write-Host "`n⚠️ 部分檔案遺失，請檢查設定" -ForegroundColor Yellow
    }
}
Set-Alias -Name ac -Value Agent-Check

function Agent-Guide {
    <#
    .SYNOPSIS
    在預設編輯器中開啟 Agent 設定指南
    #>
    if (Test-Path ".github\AGENT_SETUP_GUIDE.md") {
        code ".github\AGENT_SETUP_GUIDE.md"
    }
    else {
        Write-Host "❌ 找不到設定指南" -ForegroundColor Red
    }
}
Set-Alias -Name ag -Value Agent-Guide

function Agent-Templates {
    <#
    .SYNOPSIS
    在預設編輯器中開啟任務範本
    #>
    if (Test-Path ".github\COPILOT_TEMPLATES.md") {
        code ".github\COPILOT_TEMPLATES.md"
    }
    else {
        Write-Host "❌ 找不到任務範本" -ForegroundColor Red
    }
}
Set-Alias -Name at -Value Agent-Templates

# ==================== 專案相關 ====================

function Project-Status {
    <#
    .SYNOPSIS
    顯示專案整體狀態摘要
    #>
    Write-Host "`n📊 專案狀態摘要" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray

    # Git 狀態
    $branch = git rev-parse --abbrev-ref HEAD 2>$null
    if ($branch) {
        Write-Host "  分支: $branch" -ForegroundColor White
    }

    # Go 模組
    if (Test-Path "go.mod") {
        $goVersion = (Get-Content go.mod | Select-String "^go ").ToString() -replace "go ", ""
        Write-Host "  Go: $goVersion" -ForegroundColor Blue
    }

    # Python 版本
    $pythonVersion = python --version 2>&1
    if ($pythonVersion) {
        Write-Host "  Python: $($pythonVersion -replace 'Python ', '')" -ForegroundColor Yellow
    }

    # CLI 是否存在
    if (Test-Path "classifier.exe") {
        $cliSize = (Get-Item "classifier.exe").Length / 1MB
        Write-Host "  CLI: classifier.exe ($([math]::Round($cliSize, 2)) MB)" -ForegroundColor Green
    }
    else {
        Write-Host "  CLI: ❌ 未建構 (執行 'bc' 建構)" -ForegroundColor Red
    }

    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
    Write-Host ""
}
Set-Alias -Name ps -Value Project-Status

# ==================== 快速修復 ====================

function Fix-Dependencies {
    <#
    .SYNOPSIS
    重新安裝專案相依套件
    #>
    Write-Host "`n📦 重新安裝相依套件..." -ForegroundColor Cyan

    Write-Host "[1/2] Python 套件..." -ForegroundColor Yellow
    pip install -r requirements.txt

    Write-Host "[2/2] Go 模組..." -ForegroundColor Blue
    go mod download

    Write-Host "✅ 相依套件已更新" -ForegroundColor Green
}
Set-Alias -Name fd -Value Fix-Dependencies

# ==================== 說明資訊 ====================

function Show-AgentHelp {
    <#
    .SYNOPSIS
    顯示所有可用的 Agent 指令
    #>
    Write-Host "`n🤖 Copilot Agent 工具指令" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
    Write-Host ""
    Write-Host "測試相關:" -ForegroundColor Yellow
    Write-Host "  ta  | Test-All         執行完整自動驗證"
    Write-Host "  tp  | Test-Python      執行 Python 測試"
    Write-Host "  tg  | Test-Go          執行 Go 測試"
    Write-Host ""
    Write-Host "建構相關:" -ForegroundColor Green
    Write-Host "  bc  | Build-CLI        建構 Go CLI"
    Write-Host "  ba  | Build-All        完整編譯檢查"
    Write-Host ""
    Write-Host "Agent 相關:" -ForegroundColor Magenta
    Write-Host "  ac  | Agent-Check      檢查設定檔案"
    Write-Host "  ag  | Agent-Guide      開啟設定指南"
    Write-Host "  at  | Agent-Templates  開啟任務範本"
    Write-Host ""
    Write-Host "專案相關:" -ForegroundColor Cyan
    Write-Host "  ps  | Project-Status   顯示專案狀態"
    Write-Host "  fd  | Fix-Dependencies 重新安裝相依套件"
    Write-Host ""
    Write-Host "說明:" -ForegroundColor White
    Write-Host "  ah  | Show-AgentHelp   顯示此說明"
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
}
Set-Alias -Name ah -Value Show-AgentHelp

# ==================== 載入完成 ====================

Write-Host "✅ Copilot Agent 工具已載入" -ForegroundColor Green
Write-Host "   輸入 'ah' 查看所有指令" -ForegroundColor Gray
Write-Host ""
