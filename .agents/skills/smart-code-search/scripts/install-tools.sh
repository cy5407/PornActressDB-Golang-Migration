#!/bin/bash

# install-tools.sh - fd 和 rg 工具安裝腳本
# 支援 Windows、macOS、Linux 多平台安裝

set -euo pipefail

# 色彩定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 檢測作業系統
detect_os() {
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
        echo "windows"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    else
        echo "unknown"
    fi
}

# 檢查命令是否存在
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 安裝 fd 工具
install_fd() {
    local os="$1"
    
    echo -e "${BLUE}📦 安裝 fd (檔案搜尋工具)...${NC}"
    
    case $os in
        "windows")
            if command_exists choco; then
                echo "使用 Chocolatey 安裝 fd..."
                choco install fd -y
            elif command_exists scoop; then
                echo "使用 Scoop 安裝 fd..."
                scoop install fd
            elif command_exists winget; then
                echo "使用 winget 安裝 fd..."
                winget install sharkdp.fd
            else
                echo -e "${YELLOW}⚠️  請手動安裝 fd：${NC}"
                echo "1. 前往 https://github.com/sharkdp/fd/releases"
                echo "2. 下載 Windows 版本的 fd.exe"
                echo "3. 將 fd.exe 放入 PATH 中"
                return 1
            fi
            ;;
        "macos")
            if command_exists brew; then
                echo "使用 Homebrew 安裝 fd..."
                brew install fd
            elif command_exists port; then
                echo "使用 MacPorts 安裝 fd..."
                sudo port install fd
            else
                echo -e "${YELLOW}⚠️  請先安裝 Homebrew：${NC}"
                echo '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
                return 1
            fi
            ;;
        "linux")
            if command_exists apt-get; then
                echo "使用 apt 安裝 fd..."
                sudo apt-get update
                sudo apt-get install -y fd-find
                # 建立 fd 別名 (Ubuntu 中叫 fdfind)
                if ! command_exists fd && command_exists fdfind; then
                    echo 'alias fd=fdfind' >> ~/.bashrc
                fi
            elif command_exists yum; then
                echo "使用 yum 安裝 fd..."
                sudo yum install -y fd-find
            elif command_exists pacman; then
                echo "使用 pacman 安裝 fd..."
                sudo pacman -S fd
            elif command_exists zypper; then
                echo "使用 zypper 安裝 fd..."
                sudo zypper install fd
            else
                echo -e "${YELLOW}⚠️  請手動安裝 fd：${NC}"
                echo "1. 前往 https://github.com/sharkdp/fd/releases"
                echo "2. 下載適合的 Linux 版本"
                echo "3. 解壓並放入 /usr/local/bin/"
                return 1
            fi
            ;;
        *)
            echo -e "${RED}❌ 不支援的作業系統：$OSTYPE${NC}"
            return 1
            ;;
    esac
}

# 安裝 ripgrep 工具
install_rg() {
    local os="$1"
    
    echo -e "${BLUE}📦 安裝 rg (內容搜尋工具)...${NC}"
    
    case $os in
        "windows")
            if command_exists choco; then
                echo "使用 Chocolatey 安裝 ripgrep..."
                choco install ripgrep -y
            elif command_exists scoop; then
                echo "使用 Scoop 安裝 ripgrep..."
                scoop install ripgrep
            elif command_exists winget; then
                echo "使用 winget 安裝 ripgrep..."
                winget install BurntSushi.ripgrep.GNU
            else
                echo -e "${YELLOW}⚠️  請手動安裝 ripgrep：${NC}"
                echo "1. 前往 https://github.com/BurntSushi/ripgrep/releases"
                echo "2. 下載 Windows 版本的 rg.exe"
                echo "3. 將 rg.exe 放入 PATH 中"
                return 1
            fi
            ;;
        "macos")
            if command_exists brew; then
                echo "使用 Homebrew 安裝 ripgrep..."
                brew install ripgrep
            elif command_exists port; then
                echo "使用 MacPorts 安裝 ripgrep..."
                sudo port install ripgrep
            else
                echo -e "${YELLOW}⚠️  請先安裝 Homebrew：${NC}"
                echo '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
                return 1
            fi
            ;;
        "linux")
            if command_exists apt-get; then
                echo "使用 apt 安裝 ripgrep..."
                sudo apt-get update
                sudo apt-get install -y ripgrep
            elif command_exists yum; then
                echo "使用 yum 安裝 ripgrep..."
                sudo yum install -y ripgrep
            elif command_exists pacman; then
                echo "使用 pacman 安裝 ripgrep..."
                sudo pacman -S ripgrep
            elif command_exists zypper; then
                echo "使用 zypper 安裝 ripgrep..."
                sudo zypper install ripgrep
            else
                echo -e "${YELLOW}⚠️  請手動安裝 ripgrep：${NC}"
                echo "1. 前往 https://github.com/BurntSushi/ripgrep/releases"
                echo "2. 下載適合的 Linux 版本"
                echo "3. 解壓並放入 /usr/local/bin/"
                return 1
            fi
            ;;
        *)
            echo -e "${RED}❌ 不支援的作業系統：$OSTYPE${NC}"
            return 1
            ;;
    esac
}

# 驗證安裝
verify_installation() {
    echo -e "${BLUE}🔍 驗證安裝結果...${NC}"
    
    if command_exists fd; then
        echo -e "${GREEN}✅ fd 安裝成功：${NC}"
        fd --version
    else
        echo -e "${RED}❌ fd 安裝失敗${NC}"
        return 1
    fi
    
    if command_exists rg; then
        echo -e "${GREEN}✅ rg 安裝成功：${NC}"
        rg --version
    else
        echo -e "${RED}❌ rg 安裝失敗${NC}"
        return 1
    fi
}

# 基礎測試
run_basic_test() {
    echo -e "${BLUE}🧪 執行基礎測試...${NC}"
    
    # 建立測試目錄
    mkdir -p /tmp/fd-rg-test
    cd /tmp/fd-rg-test
    
    # 建立測試檔案
    echo "function testFunction() {}" > test.js
    echo "const API_ENDPOINT = 'https://api.example.com'" > config.js
    mkdir -p src/components
    echo "export default Component" > src/components/Test.jsx
    
    echo "建立測試檔案完成"
    
    # 測試 fd
    echo -e "\n${YELLOW}測試 fd：${NC}"
    echo "尋找 .js 檔案："
    fd -e js
    
    echo -e "\n尋找 components 目錄："
    fd components --type d
    
    # 測試 rg  
    echo -e "\n${YELLOW}測試 rg：${NC}"
    echo "搜尋 function 關鍵字："
    rg "function"
    
    echo -e "\n搜尋 API_ENDPOINT："
    rg "API_ENDPOINT"
    
    # 清理
    cd ..
    rm -rf /tmp/fd-rg-test
    
    echo -e "${GREEN}✅ 基礎測試完成！${NC}"
}

# 設定最佳化配置
setup_config() {
    echo -e "${BLUE}⚙️  設定最佳化配置...${NC}"
    
    # fd 配置
    cat > ~/.fdignore << 'EOF'
# fd ignore 配置 - 排除不必要的目錄和檔案

# 依賴目錄
node_modules/
vendor/
.venv/
venv/
env/

# 建置目錄
dist/
build/
target/
out/
.next/
.nuxt/

# 版本控制
.git/
.svn/
.hg/

# IDE 檔案
.vscode/
.idea/
*.swp
*.swo
*~

# 系統檔案
.DS_Store
Thumbs.db

# 記錄檔案
*.log
logs/

# 暫存檔案
tmp/
temp/
cache/
.cache/
EOF

    # rg 配置
    cat > ~/.ripgreprc << 'EOF'
# ripgrep 配置檔案

# 智能大小寫搜尋
--smart-case

# 顯示行號
--line-number

# 自動偵測檔案類型
--type-add=web:*.{html,css,js,ts,jsx,tsx,vue,svelte}

# 排除目錄
--glob=!node_modules
--glob=!.git
--glob=!dist
--glob=!build
--glob=!target
--glob=!.next
--glob=!coverage

# 最大檔案大小 (2MB)
--max-filesize=2M
EOF

    echo -e "${GREEN}✅ 配置檔案已建立：${NC}"
    echo "  ~/.fdignore - fd 忽略規則"
    echo "  ~/.ripgreprc - rg 預設配置"
}

# 主函數
main() {
    echo -e "${CYAN}🚀 智能程式碼搜尋工具安裝程式${NC}"
    echo -e "${CYAN}═══════════════════════════════════${NC}"
    
    local os
    os=$(detect_os)
    
    echo "檢測到作業系統：$os"
    
    # 檢查是否已安裝
    local fd_installed=false
    local rg_installed=false
    
    if command_exists fd; then
        echo -e "${YELLOW}⚠️  fd 已安裝，跳過安裝${NC}"
        fd_installed=true
    fi
    
    if command_exists rg; then
        echo -e "${YELLOW}⚠️  rg 已安裝，跳過安裝${NC}"  
        rg_installed=true
    fi
    
    # 安裝工具
    if [[ "$fd_installed" == false ]]; then
        install_fd "$os" || {
            echo -e "${RED}❌ fd 安裝失敗${NC}"
            exit 1
        }
    fi
    
    if [[ "$rg_installed" == false ]]; then
        install_rg "$os" || {
            echo -e "${RED}❌ rg 安裝失敗${NC}"
            exit 1
        }
    fi
    
    # 驗證安裝
    verify_installation || {
        echo -e "${RED}❌ 工具驗證失敗${NC}"
        exit 1
    }
    
    # 執行測試
    run_basic_test || {
        echo -e "${RED}❌ 基礎測試失敗${NC}"
        exit 1
    }
    
    # 設定配置
    setup_config
    
    echo -e "${GREEN}🎉 安裝完成！${NC}"
    echo -e "${CYAN}═══════════════════════════════════${NC}"
    echo -e "${GREEN}✅ fd (檔案搜尋) 和 rg (內容搜尋) 已安裝就緒${NC}"
    echo ""
    echo -e "${BLUE}📚 使用指南：${NC}"
    echo "  fd --help     # 檢視 fd 說明"
    echo "  rg --help     # 檢視 rg 說明"
    echo ""
    echo -e "${BLUE}🔍 快速範例：${NC}"
    echo "  fd '*.js'     # 找所有 JavaScript 檔案"
    echo "  rg 'function' # 搜尋包含 function 的程式碼"
    echo ""
    echo -e "${YELLOW}💡 提示：重新開啟終端機以確保設定生效${NC}"
}

# 執行主函數
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi