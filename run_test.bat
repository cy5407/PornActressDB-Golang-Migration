@echo off
echo 🚀 啟動女優分類系統測試...
cd /d "%~dp0"

REM 檢查Python是否可用
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 找不到Python，請確保Python已安裝並加入PATH
    echo 🔍 嘗試使用py命令...
    py --version >nul 2>&1
    if errorlevel 1 (
        echo ❌ 也找不到py命令
        pause
        exit /b 1
    ) else (
        echo ✅ 找到py命令
        py run.py
    )
) else (
    echo ✅ 找到python命令
    python run.py
)

pause