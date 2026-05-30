# verify.ps1 — 本機統一驗證腳本
#
# 用法:
#   pwsh scripts/verify.ps1            # 完整跑 5 個工具鏈步驟 (含所有 test)
#   pwsh scripts/verify.ps1 -Quick     # 只跑靜態檢查 (build/vet/fmt/clippy)，跳過 test
#
# 步驟順序 (任一步非零退出時整個腳本以該步 exit code 退出):
#   1/5 root Go         : go build ./...; go vet ./...; go test ./... -count=1
#   2/5 wails-app Go    : go build ./...; go test ./backend -count=1
#   3/5 Rust tools-rs   : cargo fmt --check; cargo clippy -- -D warnings; cargo test
#   4/5 Python pytest   : python -m pytest tests/ -q -p no:cacheprovider
#
# 注意:
#   - 步驟編號分母為 5 是包含 Quick 模式下被略過的 Python 步驟在內的固定編號。
#   - Quick 模式下 step 4 (Python) 整段跳過 (打印 SKIP)；step 1/2/3 內的 test 子步驟也跳過。
#   - 使用 Push-Location / Pop-Location 安全切換子目錄。

[CmdletBinding()]
param(
    [switch]$Quick
)

$ErrorActionPreference = "Stop"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT  = Resolve-Path (Join-Path $SCRIPT_DIR "..")

# 將「步驟 N/5 失敗」轉成 throw，由最外層 catch 統一處理 exit code。
function Invoke-Step {
    param(
        [Parameter(Mandatory)] [int]    $StepNumber,
        [Parameter(Mandatory)] [string] $Description,
        [Parameter(Mandatory)] [scriptblock] $Action
    )

    Write-Host "==> [step $StepNumber/5] $Description" -ForegroundColor Cyan
    try {
        & $Action
    } catch {
        Write-Host "==> [step $StepNumber/5] FAIL" -ForegroundColor Red
        # 重拋給最外層 catch；exit code 由 caller 決定。
        throw
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Host "==> [step $StepNumber/5] FAIL (exit $LASTEXITCODE)" -ForegroundColor Red
        # 用 throw 把 exit code 一起傳出去。
        throw [System.Management.Automation.RuntimeException]::new(
            "step $StepNumber failed with exit code $LASTEXITCODE"
        )
    }

    Write-Host "==> [step $StepNumber/5] OK" -ForegroundColor Green
}

# 子步驟封裝：跑一條指令並在非零退出時 throw。供同一個 step 內串多條命令使用。
function Invoke-Cmd {
    param(
        [Parameter(Mandatory)] [string] $Label,
        [Parameter(Mandatory)] [scriptblock] $Cmd
    )

    Write-Host "    -> $Label" -ForegroundColor DarkGray
    & $Cmd
    if ($LASTEXITCODE -ne 0) {
        throw "sub-command failed ($Label) with exit code $LASTEXITCODE"
    }
}

Push-Location $REPO_ROOT
try {
    # -------------------------------------------------------------------------
    # Step 1/5 : root Go
    # -------------------------------------------------------------------------
    Invoke-Step -StepNumber 1 -Description "root Go: build + vet$(if (-not $Quick) { ' + test' })" -Action {
        Invoke-Cmd -Label "go build ./..." -Cmd { go build ./... }
        Invoke-Cmd -Label "go vet ./..."   -Cmd { go vet ./... }
        if (-not $Quick) {
            Invoke-Cmd -Label "go test ./... -count=1" -Cmd { go test ./... -count=1 }
        } else {
            Write-Host "    -> go test ./... (SKIP: -Quick)" -ForegroundColor DarkGray
        }
    }

    # -------------------------------------------------------------------------
    # Step 2/5 : wails-app Go (子目錄)
    #   - 注意: wails-app/main.go 用 `//go:embed all:frontend/dist`,
    #     直接 `go build ./...` 在沒先跑 `wails build` 的本機 worktree 會失敗
    #     (frontend/dist 為 gitignored 的前端建置產物)。
    #   - 本腳本驗證的是 Go 部分編譯與後端測試,因此限定 build/test 範圍
    #     為 `./backend` (與 CLAUDE.md「wails-app 測試 = go test .\backend -v」對齊)。
    # -------------------------------------------------------------------------
    Invoke-Step -StepNumber 2 -Description "wails-app Go: build ./backend$(if (-not $Quick) { ' + test ./backend' })" -Action {
        Push-Location (Join-Path $REPO_ROOT "wails-app")
        try {
            Invoke-Cmd -Label "go build ./backend" -Cmd { go build ./backend }
            if (-not $Quick) {
                Invoke-Cmd -Label "go test ./backend -count=1" -Cmd { go test ./backend -count=1 }
            } else {
                Write-Host "    -> go test ./backend (SKIP: -Quick)" -ForegroundColor DarkGray
            }
        } finally {
            Pop-Location
        }
    }

    # -------------------------------------------------------------------------
    # Step 3/5 : Rust tools-rs (子目錄，三步必跑)
    # -------------------------------------------------------------------------
    Invoke-Step -StepNumber 3 -Description "Rust tools-rs: fmt --check + clippy$(if (-not $Quick) { ' + test' })" -Action {
        Push-Location (Join-Path $REPO_ROOT "tools-rs")
        try {
            Invoke-Cmd -Label "cargo fmt --check"           -Cmd { cargo fmt --check }
            Invoke-Cmd -Label "cargo clippy -- -D warnings" -Cmd { cargo clippy -- -D warnings }
            if (-not $Quick) {
                Invoke-Cmd -Label "cargo test" -Cmd { cargo test }
            } else {
                Write-Host "    -> cargo test (SKIP: -Quick)" -ForegroundColor DarkGray
            }
        } finally {
            Pop-Location
        }
    }

    # -------------------------------------------------------------------------
    # Step 4/5 : Python pytest (Quick 模式整段跳過)
    # -------------------------------------------------------------------------
    if (-not $Quick) {
        Invoke-Step -StepNumber 4 -Description "Python pytest: tests/" -Action {
            Invoke-Cmd -Label "python -m pytest tests/ -q -p no:cacheprovider" -Cmd {
                python -m pytest tests/ -q -p no:cacheprovider
            }
        }
    } else {
        Write-Host "==> [step 4/5] Python pytest (SKIP: -Quick)" -ForegroundColor Yellow
    }

    # -------------------------------------------------------------------------
    # Step 5/5 : 收尾 (預留位；目前無額外動作，仍按格式輸出讓整個流程顯示 5/5)
    # -------------------------------------------------------------------------
    Invoke-Step -StepNumber 5 -Description "summary" -Action {
        Write-Host "    -> all preceding steps reported OK or SKIP" -ForegroundColor DarkGray
        $global:LASTEXITCODE = 0
    }

    Write-Host ""
    if ($Quick) {
        Write-Host "verify.ps1 -Quick: all static checks PASSED" -ForegroundColor Green
    } else {
        Write-Host "verify.ps1: all steps PASSED" -ForegroundColor Green
    }
    exit 0
} catch {
    Write-Host ""
    Write-Host "verify.ps1: FAILED - $($_.Exception.Message)" -ForegroundColor Red
    # 子命令失敗時 $LASTEXITCODE 為實際 exit code；若被改回 0 則退 1。
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    } else {
        exit 1
    }
} finally {
    Pop-Location
}
