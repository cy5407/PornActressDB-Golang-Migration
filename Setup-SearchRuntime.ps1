param(
    [switch]$Launch
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$Requirements = Join-Path $Root "requirements.txt"
$Marker = Join-Path $VenvDir ".requirements.sha256"
$AppExe = Join-Path $Root "actress-classifier.exe"

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-PythonVersion($PythonCommand) {
    try {
        $output = & $PythonCommand -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        return [version]($output.Trim())
    } catch {
        return $null
    }
}

function Find-Python {
    $commands = @("py -3.12", "py -3.11", "py -3", "python", "python3")
    foreach ($command in $commands) {
        $parts = $command -split " "
        $exe = $parts[0]
        $args = @()
        if ($parts.Length -gt 1) {
            $args = $parts[1..($parts.Length - 1)]
        }
        $found = Get-Command $exe -ErrorAction SilentlyContinue
        if (-not $found) {
            continue
        }
        try {
            $versionText = & $exe @args -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
            $version = [version]($versionText.Trim())
            if ($version -ge [version]"3.11") {
                return @{ Exe = $exe; Args = $args; Version = $version }
            }
        } catch {
            continue
        }
    }
    return $null
}

if (-not (Test-Path $Requirements)) {
    Write-Host "requirements.txt was not found. Please run this from the complete portable bundle." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $AppExe)) {
    Write-Host "actress-classifier.exe was not found. Please run this from the complete portable bundle." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $VenvPython)) {
    Write-Step "Creating the Python search runtime"
    $python = Find-Python
    if (-not $python) {
        Write-Host "Python 3.11+ was not found." -ForegroundColor Red
        Write-Host "Please install Python 3.11 or newer and enable 'Add python.exe to PATH'."
        Write-Host "Download: https://www.python.org/downloads/windows/"
        exit 1
    }
    & $python.Exe @($python.Args + @("-m", "venv", $VenvDir))
}

$currentHash = (Get-FileHash -Algorithm SHA256 $Requirements).Hash
$installedHash = ""
if (Test-Path $Marker) {
    $installedHash = (Get-Content $Marker -Raw).Trim()
}

if ($currentHash -ne $installedHash) {
    Write-Step "Installing or updating search dependencies"
    & $VenvPython -m pip install --disable-pip-version-check -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    Set-Content -Path $Marker -Value $currentHash -Encoding ASCII
}

if ($Launch) {
    Write-Step "Starting Actress Classifier"
    Start-Process -FilePath $AppExe -WorkingDirectory $Root
}
