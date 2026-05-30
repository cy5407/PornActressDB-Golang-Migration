# deadcode-all.ps1 — 雙 binary 死碼交集腳本
#
# 目的:消除「`deadcode ./cmd/scanner` 把只有 wails 用的函數誤報死碼」的假陽性。
# 做法:同時對兩個 binary 跑 `deadcode`,各自輸出 unreachable 清單,
#       **取交集**(只有兩個 binary 都不可達才算真死碼),排除 `*_test.go`。
#
# 兩個 binary 起點:
#   1. Root module (actress-classifier)  → ./cmd/scanner
#   2. Wails module (wails-app)          → wails-app/ 內 deadcode .
#
# 注意:wails-app 是獨立 module(自己的 go.mod),且 module name 不同,
#       所以必須用 `-filter=`(空 regex)才能看到 wails 端對 actress-classifier/pkg/*
#       的可達性分析,否則預設 filter 會只看 wails-app 自己 module。
#
# 用法:
#   pwsh scripts/deadcode-all.ps1                    # 預設輸出
#   pwsh scripts/deadcode-all.ps1 -DeadcodeExe ...   # 自訂 deadcode 路徑
#
# 退出碼:任一 deadcode 子命令非零退出,本腳本也非零退出。

[CmdletBinding()]
param(
    # deadcode 執行檔路徑;預設找 PATH 內的 deadcode,找不到再退而求其次找 GOPATH/bin。
    [string]$DeadcodeExe = ""
)

$ErrorActionPreference = 'Stop'

# ---------- 0) 找 deadcode 執行檔 ----------
function Resolve-Deadcode {
    param([string]$Hint)
    if ($Hint) {
        if (Test-Path -LiteralPath $Hint -PathType Leaf) { return (Resolve-Path -LiteralPath $Hint).Path }
        throw "找不到 deadcode 執行檔:$Hint"
    }
    $cmd = Get-Command deadcode -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    # fallback: %GOPATH%/bin/deadcode(.exe)
    $gopath = $env:GOPATH
    if (-not $gopath) {
        $goEnv = & go env GOPATH 2>$null
        if ($LASTEXITCODE -eq 0 -and $goEnv) { $gopath = $goEnv.Trim() }
    }
    if ($gopath) {
        foreach ($name in @('deadcode.exe', 'deadcode')) {
            $cand = Join-Path $gopath "bin\$name"
            if (Test-Path -LiteralPath $cand -PathType Leaf) { return (Resolve-Path -LiteralPath $cand).Path }
        }
    }
    throw "找不到 deadcode。請先 `go install golang.org/x/tools/cmd/deadcode@latest`,或用 -DeadcodeExe 指定路徑。"
}

# ---------- 1) 鎖定 repo root(這個腳本的 ../) ----------
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$wailsDir = Join-Path $repoRoot 'wails-app'

if (-not (Test-Path -LiteralPath (Join-Path $repoRoot 'go.mod'))) {
    throw "repo root 沒有 go.mod:$repoRoot"
}
if (-not (Test-Path -LiteralPath (Join-Path $wailsDir 'go.mod'))) {
    throw "wails-app 沒有 go.mod:$wailsDir"
}

$deadcode = Resolve-Deadcode -Hint $DeadcodeExe
Write-Host "[deadcode-all] 使用 deadcode: $deadcode"
Write-Host "[deadcode-all] repo root  : $repoRoot"
Write-Host "[deadcode-all] wails dir  : $wailsDir"
Write-Host ""

# ---------- 2) 跑 deadcode -json 兩次,parse 成 fully-qualified 名稱清單 ----------

# 用 `-filter=` 空字串 => 不限制 module,才看得到跨 module 的 actress-classifier/pkg/*
# JSON shape(每筆):
#   [{ "Path": "<pkg-import-path>", "Funcs": [{ "Name": "<sym>",
#                                                "Position": { "File": "..." } }] }]

function Invoke-Deadcode {
    param(
        [string]$WorkDir,
        [string[]]$Pkgs,
        [string]$Label
    )
    Write-Host "[deadcode-all] [$Label] 跑 deadcode -filter= -json $($Pkgs -join ' ') (cwd=$WorkDir)..."
    Push-Location $WorkDir
    try {
        # 注意:deadcode 把分析摘要寫 stderr;結果走 stdout
        $stdout = & $deadcode '-filter=' '-json' @Pkgs
        $exit = $LASTEXITCODE
        if ($exit -ne 0) {
            throw "[$Label] deadcode 退出碼非零($exit),工作目錄=$WorkDir,套件=$($Pkgs -join ' ')"
        }
        if (-not $stdout) { return @() }
        $raw = ($stdout -join "`n").Trim()
        if (-not $raw -or $raw -eq 'null') { return @() }
        $parsed = $raw | ConvertFrom-Json
        # 單筆物件時 ConvertFrom-Json 不會包成陣列,統一成陣列
        if ($parsed -isnot [System.Array]) { $parsed = @($parsed) }
        return $parsed
    }
    finally {
        Pop-Location
    }
}

function Get-DeadSymbolSet {
    param(
        [Parameter(Mandatory)] [AllowNull()] $Packages
    )
    # 回傳 HashSet[string](case-sensitive),元素為 "<pkg-import-path>.<sym>"
    # 排除任何 Position.File 結尾為 _test.go 的(deadcode 預設不掃 test,但 -test 可能會;
    # 這裡明確過濾保險)
    $set = [System.Collections.Generic.HashSet[string]]::new()
    if (-not $Packages) { return $set }
    foreach ($pkg in $Packages) {
        $pkgPath = $pkg.Path
        if (-not $pkgPath) { continue }
        $funcs = $pkg.Funcs
        if (-not $funcs) { continue }
        foreach ($fn in $funcs) {
            $file = $null
            if ($fn.Position) { $file = $fn.Position.File }
            if ($file) {
                # Windows 反斜線 + Unix 斜線都處理
                $fileNorm = $file -replace '\\', '/'
                if ($fileNorm.EndsWith('_test.go')) { continue }
            }
            $name = $fn.Name
            if (-not $name) { continue }
            [void]$set.Add("$pkgPath.$name")
        }
    }
    return $set
}

# 第一次:root 從 ./cmd/scanner 起點
$rootJson = Invoke-Deadcode -WorkDir $repoRoot -Pkgs @('./cmd/scanner') -Label 'root cmd/scanner'

# 第二次:wails-app 從當前目錄起點(wails-app 內有 main package)
$wailsJson = Invoke-Deadcode -WorkDir $wailsDir -Pkgs @('.') -Label 'wails-app'

$rootDead = Get-DeadSymbolSet -Packages $rootJson
$wailsDead = Get-DeadSymbolSet -Packages $wailsJson

Write-Host ""
Write-Host "[deadcode-all] root cmd/scanner unreachable(非測試):$($rootDead.Count)"
Write-Host "[deadcode-all] wails-app       unreachable(非測試):$($wailsDead.Count)"
Write-Host ""

# ---------- 3) 計算交集 + only-one-side(差集) ----------

$intersection = [System.Collections.Generic.SortedSet[string]]::new()
foreach ($s in $rootDead) {
    if ($wailsDead.Contains($s)) { [void]$intersection.Add($s) }
}

$onlyRoot = [System.Collections.Generic.SortedSet[string]]::new()
foreach ($s in $rootDead) {
    if (-not $wailsDead.Contains($s)) { [void]$onlyRoot.Add($s) }
}

$onlyWails = [System.Collections.Generic.SortedSet[string]]::new()
foreach ($s in $wailsDead) {
    if (-not $rootDead.Contains($s)) { [void]$onlyWails.Add($s) }
}

# ---------- 4) 輸出 ----------

Write-Host "==== Real dead code (unreachable from BOTH binaries) ===="
Write-Host "# 兩個 binary 都看不到 → 真死碼,可安全刪除(刪前還是建議 grep 確認 reflect / //go:linkname 沒在用)。"
Write-Host "# 共 $($intersection.Count) 個符號。"
if ($intersection.Count -eq 0) {
    Write-Host "(無)"
} else {
    foreach ($s in $intersection) { Write-Host "  $s" }
}
Write-Host ""

Write-Host "==== Single-binary-only (DO NOT DELETE — used by the other binary) ===="
Write-Host "# 只在其中一邊 dead,代表另一邊在用。刪掉會打壞另一個 binary。"
Write-Host ""
Write-Host "-- Dead in cmd/scanner only (wails-app uses these) ---- $($onlyRoot.Count) 個"
if ($onlyRoot.Count -eq 0) {
    Write-Host "(無)"
} else {
    foreach ($s in $onlyRoot) { Write-Host "  $s" }
}
Write-Host ""
Write-Host "-- Dead in wails-app only (cmd/scanner uses these) ---- $($onlyWails.Count) 個"
if ($onlyWails.Count -eq 0) {
    Write-Host "(無)"
} else {
    foreach ($s in $onlyWails) { Write-Host "  $s" }
}
Write-Host ""

Write-Host "==== Summary ===="
Write-Host "  root  dead = $($rootDead.Count)"
Write-Host "  wails dead = $($wailsDead.Count)"
Write-Host "  intersect  = $($intersection.Count)  (真死碼)"
Write-Host "  only-root  = $($onlyRoot.Count)      (wails 在用 → 勿刪)"
Write-Host "  only-wails = $($onlyWails.Count)     (cmd/scanner 在用 → 勿刪)"

exit 0
