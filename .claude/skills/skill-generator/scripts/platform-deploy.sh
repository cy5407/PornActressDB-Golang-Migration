#!/bin/bash

# platform-deploy.sh v2.0 - 跨平台 AI Agent 技能部署腳本
# 基於 Anthropic Agent Skills 開放標準 (https://agentskills.io) 
# 官方技能庫參考: https://github.com/anthropics/skills/
# 支援: Claude Code、GitHub Copilot、VS Code Insiders、Copilot CLI、Codex CLI

set -euo pipefail

VERSION="2.0.0"

# 🎨 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# 📊 平台配置 (基於 2026 年 2 月最新支援狀況)
declare -A PLATFORM_PATHS=(
    ["claude-code"]=".claude/skills"
    ["github-copilot-project"]=".github/skills"        # 專案級
    ["github-copilot-global"]=".claude/skills"         # 全域共用
    ["vs-code"]=".claude/skills"                       # 主要位置
    ["vs-code-alt"]=".github/skills"                   # 替代位置
    ["copilot-cli"]="$HOME/.copilot/skills"            # GitHub Copilot CLI 全域
    ["codex-cli"]="$HOME/.codex/skills"                # Codex CLI 全域
)

declare -A PLATFORM_DESCRIPTIONS=(
    ["claude-code"]="Claude Code (專案級)"
    ["github-copilot-project"]="GitHub Copilot (專案級)"
    ["github-copilot-global"]="GitHub Copilot CLI (全域)"
    ["vs-code"]="VS Code Insiders"
    ["codex-cli"]="Codex CLI (全域)"
)

# 使用說明
usage() {
    echo -e "${CYAN}🚀 跨平台 AI Agent 技能部署工具${NC}"
    echo ""
    echo "用法: $0 [命令] [技能名稱] [平台...]"
    echo ""
    echo "命令:"
    echo "  deploy    部署技能到指定平台"
    echo "  sync      同步技能到多個平台"  
    echo "  remove    從平台移除技能"
    echo "  list      列出已部署的技能"
    echo "  check     檢查平台相容性"
    echo ""
    echo "平台選項:"
    echo "  claude-code              Claude Code 專案級技能"
    echo "  github-copilot-project   GitHub Copilot 專案級技能"  
    echo "  github-copilot-global    GitHub Copilot CLI 全域技能"
    echo "  vs-code                  VS Code Insiders"
    echo "  codex-cli                Codex CLI 全域技能"
    echo "  all                      所有支援的平台"
    echo ""
    echo "範例:"
    echo "  $0 deploy my-skill claude-code"
    echo "  $0 sync my-skill claude-code,github-copilot-project"
    echo "  $0 deploy my-skill all"
    echo "  $0 check my-skill"
    echo ""
    exit 1
}

# 印出狀態訊息
print_status() {
    local status=$1
    local message=$2
    case $status in
        "ok")
            echo -e "${GREEN}✅${NC} $message"
            ;;
        "warn")
            echo -e "${YELLOW}⚠️${NC} $message"
            ;;
        "error")
            echo -e "${RED}❌${NC} $message"
            ;;
        "info")
            echo -e "${BLUE}ℹ️${NC} $message"
            ;;
        "progress")
            echo -e "${CYAN}🔄${NC} $message"
            ;;
    esac
}

# 檢查技能是否存在
check_skill_exists() {
    local skill_name=$1
    local skill_path=".claude/skills/$skill_name"
    
    if [ ! -d "$skill_path" ]; then
        print_status "error" "技能不存在: $skill_path"
        return 1
    fi
    
    if [ ! -f "$skill_path/SKILL.md" ]; then
        print_status "error" "技能檔案不存在: $skill_path/SKILL.md"
        return 1
    fi
    
    return 0
}

# 檢查技能的平台相容性
check_skill_compatibility() {
    local skill_name=$1
    local skill_file=".claude/skills/$skill_name/SKILL.md"
    
    # 檢查是否使用 Claude Code 特有功能
    local has_context_fork=$(grep -q "context:\s*fork" "$skill_file" && echo "true" || echo "false")
    local has_hooks=$(grep -q "hooks:" "$skill_file" && echo "true" || echo "false")
    local has_dynamic_context=$(grep -q "!\`" "$skill_file" && echo "true" || echo "false")
    
    declare -A compatibility=(
        ["claude-code"]="true"
        ["github-copilot-project"]="true"
        ["github-copilot-global"]="true"
        ["vs-code"]="true"
        ["codex-cli"]="true"
    )
    
    # 如果使用 Claude Code 特有功能，其他平台標記為不相容
    if [ "$has_context_fork" = "true" ] || [ "$has_hooks" = "true" ] || [ "$has_dynamic_context" = "true" ]; then
        compatibility["github-copilot-project"]="partial"
        compatibility["github-copilot-global"]="partial"
        compatibility["vs-code"]="partial"
        compatibility["codex-cli"]="partial"
    fi
    
    echo "claude-code:${compatibility[claude-code]}"
    echo "github-copilot-project:${compatibility[github-copilot-project]}"
    echo "github-copilot-global:${compatibility[github-copilot-global]}"
    echo "vs-code:${compatibility[vs-code]}"
    echo "codex-cli:${compatibility[codex-cli]}"
}

# 創建平台特定的技能版本
create_platform_version() {
    local skill_name=$1
    local platform=$2
    local source_dir=".claude/skills/$skill_name"
    local temp_dir="/tmp/skill-deploy-$$"
    
    # 複製原始技能到暫存目錄
    cp -r "$source_dir" "$temp_dir"
    
    # 根據平台調整技能內容
    case $platform in
        "github-copilot-project"|"github-copilot-global"|"vs-code"|"codex-cli")
            # 移除 Claude Code 特有功能
            sed -i '/^context:/d' "$temp_dir/SKILL.md"
            sed -i '/^agent:/d' "$temp_dir/SKILL.md"
            sed -i '/^hooks:/,/^[a-zA-Z]/{ /^[a-zA-Z]/!d; }' "$temp_dir/SKILL.md"
            sed -i 's/!\`[^`]*\`//g' "$temp_dir/SKILL.md"
            
            # 添加平台相容性說明
            echo "" >> "$temp_dir/SKILL.md"
            echo "## 平台相容性" >> "$temp_dir/SKILL.md"
            echo "此技能已針對 ${PLATFORM_DESCRIPTIONS[$platform]} 進行最佳化。" >> "$temp_dir/SKILL.md"
            echo "部分 Claude Code 進階功能已移除以確保相容性。" >> "$temp_dir/SKILL.md"
            ;;
    esac
    
    echo "$temp_dir"
}

# 部署技能到指定平台
deploy_to_platform() {
    local skill_name=$1
    local platform=$2
    local target_path="${PLATFORM_PATHS[$platform]}/$skill_name"
    
    print_status "progress" "部署 $skill_name 到 ${PLATFORM_DESCRIPTIONS[$platform]}"
    
    # 檢查目標路徑
    if [[ $target_path == /* ]]; then
        # 絕對路徑 (全域技能)
        target_dir=$(dirname "$target_path")
    else
        # 相對路徑 (專案技能)  
        target_dir="$target_path"
    fi
    
    # 創建目標目錄
    mkdir -p "$(dirname "$target_path")"
    
    # 創建平台特定版本
    local temp_skill_dir=$(create_platform_version "$skill_name" "$platform")
    
    # 複製技能到目標位置
    if [ -d "$target_path" ]; then
        print_status "warn" "目標位置已存在，將覆蓋: $target_path"
        rm -rf "$target_path"
    fi
    
    cp -r "$temp_skill_dir" "$target_path"
    
    # 清理暫存檔案
    rm -rf "$temp_skill_dir"
    
    print_status "ok" "已部署到: $target_path"
}

# 同步技能到多個平台
sync_skill() {
    local skill_name=$1
    local platforms_str=$2
    
    # 解析平台列表
    IFS=',' read -ra platforms <<< "$platforms_str"
    
    # 展開 "all" 平台
    if [[ " ${platforms[@]} " =~ " all " ]]; then
        platforms=("claude-code" "github-copilot-project" "github-copilot-global" "vs-code" "codex-cli")
    fi
    
    echo -e "${CYAN}🔄 同步技能: $skill_name${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # 檢查技能相容性
    local compatibility_info=$(check_skill_compatibility "$skill_name")
    
    # 部署到每個平台
    for platform in "${platforms[@]}"; do
        if [ -z "${PLATFORM_PATHS[$platform]}" ]; then
            print_status "error" "不支援的平台: $platform"
            continue
        fi
        
        # 檢查相容性
        local compat=$(echo "$compatibility_info" | grep "^$platform:" | cut -d: -f2)
        case $compat in
            "true")
                deploy_to_platform "$skill_name" "$platform"
                ;;
            "partial")
                print_status "warn" "部分相容: ${PLATFORM_DESCRIPTIONS[$platform]} (已移除進階功能)"
                deploy_to_platform "$skill_name" "$platform"
                ;;
            *)
                print_status "error" "不相容: ${PLATFORM_DESCRIPTIONS[$platform]}"
                ;;
        esac
    done
    
    echo ""
    print_status "ok" "同步完成"
}

# 從平台移除技能
remove_skill() {
    local skill_name=$1
    local platforms_str=$2
    
    IFS=',' read -ra platforms <<< "$platforms_str"
    
    if [[ " ${platforms[@]} " =~ " all " ]]; then
        platforms=("claude-code" "github-copilot-project" "github-copilot-global" "vs-code" "codex-cli")
    fi
    
    echo -e "${CYAN}🗑️  移除技能: $skill_name${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    for platform in "${platforms[@]}"; do
        local target_path="${PLATFORM_PATHS[$platform]}/$skill_name"
        
        if [ -d "$target_path" ]; then
            rm -rf "$target_path"
            print_status "ok" "已從 ${PLATFORM_DESCRIPTIONS[$platform]} 移除"
        else
            print_status "info" "技能不存在於 ${PLATFORM_DESCRIPTIONS[$platform]}"
        fi
    done
}

# 列出已部署的技能
list_skills() {
    echo -e "${CYAN}📋 已部署的技能${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    for platform in "${!PLATFORM_PATHS[@]}"; do
        local skills_dir="${PLATFORM_PATHS[$platform]}"
        
        echo -e "\n${BLUE}${PLATFORM_DESCRIPTIONS[$platform]}${NC}: $skills_dir"
        
        if [ -d "$skills_dir" ]; then
            local count=0
            for skill_dir in "$skills_dir"/*; do
                if [ -d "$skill_dir" ] && [ -f "$skill_dir/SKILL.md" ]; then
                    local skill_name=$(basename "$skill_dir")
                    echo "  ✅ $skill_name"
                    ((count++))
                fi
            done
            
            if [ $count -eq 0 ]; then
                echo "  📭 無技能"
            fi
        else
            echo "  📭 目錄不存在"
        fi
    done
}

# 檢查技能相容性
check_compatibility() {
    local skill_name=$1
    
    echo -e "${CYAN}🔍 檢查技能相容性: $skill_name${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    if ! check_skill_exists "$skill_name"; then
        return 1
    fi
    
    local compatibility_info=$(check_skill_compatibility "$skill_name")
    
    echo ""
    printf "%-25s %-15s %-10s\n" "平台" "相容性" "說明"
    echo "────────────────────────────────────────────────────"
    
    for platform in "${!PLATFORM_DESCRIPTIONS[@]}"; do
        local compat=$(echo "$compatibility_info" | grep "^$platform:" | cut -d: -f2)
        local status_icon=""
        local description=""
        
        case $compat in
            "true")
                status_icon="✅ 完全相容"
                description="支援所有功能"
                ;;
            "partial")
                status_icon="⚠️  部分相容"
                description="移除進階功能"
                ;;
            *)
                status_icon="❌ 不相容"
                description="無法使用"
                ;;
        esac
        
        printf "%-25s %-15s %-10s\n" "${PLATFORM_DESCRIPTIONS[$platform]}" "$status_icon" "$description"
    done
    
    echo ""
    
    # 提供建議
    local has_advanced_features=$(echo "$compatibility_info" | grep -q ":partial" && echo "true" || echo "false")
    if [ "$has_advanced_features" = "true" ]; then
        print_status "info" "此技能使用 Claude Code 進階功能"
        print_status "info" "建議: 為其他平台建立簡化版本，或使用通用範本重新建立"
    else
        print_status "ok" "此技能完全跨平台相容"
    fi
}

# 主程式
main() {
    if [ $# -eq 0 ]; then
        usage
    fi
    
    local command=$1
    shift
    
    case $command in
        "deploy")
            if [ $# -lt 2 ]; then
                print_status "error" "用法: $0 deploy <技能名稱> <平台>"
                exit 1
            fi
            
            local skill_name=$1
            local platform=$2
            
            if ! check_skill_exists "$skill_name"; then
                exit 1
            fi
            
            if [ "$platform" = "all" ]; then
                sync_skill "$skill_name" "all"
            else
                sync_skill "$skill_name" "$platform"
            fi
            ;;
            
        "sync")
            if [ $# -lt 2 ]; then
                print_status "error" "用法: $0 sync <技能名稱> <平台1,平台2,...>"
                exit 1
            fi
            
            local skill_name=$1
            local platforms=$2
            
            if ! check_skill_exists "$skill_name"; then
                exit 1
            fi
            
            sync_skill "$skill_name" "$platforms"
            ;;
            
        "remove")
            if [ $# -lt 2 ]; then
                print_status "error" "用法: $0 remove <技能名稱> <平台>"
                exit 1
            fi
            
            remove_skill "$1" "$2"
            ;;
            
        "list")
            list_skills
            ;;
            
        "check")
            if [ $# -lt 1 ]; then
                print_status "error" "用法: $0 check <技能名稱>"
                exit 1
            fi
            
            check_compatibility "$1"
            ;;
            
        *)
            print_status "error" "未知命令: $command"
            usage
            ;;
    esac
}

# 如果腳本被直接執行
if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi