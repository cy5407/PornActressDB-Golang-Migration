# GitHub 快速設定腳本

# 請先在 GitHub 網站上建立新的儲存庫，然後修改以下變數
$USERNAME = "YOUR_GITHUB_USERNAME"     # 替換為您的 GitHub 使用者名稱
$REPO_NAME = "actress-classifier"      # 替換為您的儲存庫名稱 (可自訂)

Write-Host "🚀 準備推送到 GitHub..." -ForegroundColor Green
Write-Host "儲存庫: https://github.com/$USERNAME/$REPO_NAME" -ForegroundColor Yellow

# 檢查是否已有遠端設定
$existing_remote = git remote get-url origin 2>$null
if ($existing_remote) {
    Write-Host "⚠️ 發現現有遠端設定: $existing_remote" -ForegroundColor Yellow
    $response = Read-Host "是否要替換? (y/N)"
    if ($response -eq "y" -or $response -eq "Y") {
        git remote remove origin
        Write-Host "✅ 已移除現有遠端設定" -ForegroundColor Green
    } else {
        Write-Host "❌ 取消操作" -ForegroundColor Red
        exit
    }
}

# 確認變數已設定
if ($USERNAME -eq "YOUR_GITHUB_USERNAME") {
    Write-Host "❌ 請先修改腳本中的 USERNAME 變數" -ForegroundColor Red
    Write-Host "將 'YOUR_GITHUB_USERNAME' 替換為您的實際 GitHub 使用者名稱" -ForegroundColor Yellow
    exit
}

# 最終確認
Write-Host "`n即將執行以下操作:" -ForegroundColor Cyan
Write-Host "1. 添加遠端儲存庫: https://github.com/$USERNAME/$REPO_NAME.git" -ForegroundColor White
Write-Host "2. 重命名分支為 main" -ForegroundColor White
Write-Host "3. 推送所有檔案到 GitHub" -ForegroundColor White

$confirm = Read-Host "`n確定繼續? (y/N)"
if ($confirm -ne "y" -and $confirm -ne "Y") {
    Write-Host "❌ 操作已取消" -ForegroundColor Red
    exit
}

try {
    # 添加遠端儲存庫
    Write-Host "`n🔗 添加遠端儲存庫..." -ForegroundColor Blue
    git remote add origin "https://github.com/$USERNAME/$REPO_NAME.git"
    
    # 重命名分支
    Write-Host "🌿 設定主分支..." -ForegroundColor Blue
    git branch -M main
    
    # 推送到 GitHub
    Write-Host "📤 推送到 GitHub..." -ForegroundColor Blue
    git push -u origin main
    
    Write-Host "`n🎉 成功推送到 GitHub!" -ForegroundColor Green
    Write-Host "您的專案現在可以在以下網址查看:" -ForegroundColor Green
    Write-Host "https://github.com/$USERNAME/$REPO_NAME" -ForegroundColor Cyan
    
} catch {
    Write-Host "`n❌ 推送過程中發生錯誤:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "`n💡 可能的解決方案:" -ForegroundColor Yellow
    Write-Host "1. 確認 GitHub 儲存庫已建立" -ForegroundColor White
    Write-Host "2. 檢查網路連接" -ForegroundColor White
    Write-Host "3. 確認 GitHub 認證設定" -ForegroundColor White
}

Read-Host "`n按 Enter 鍵結束..."
