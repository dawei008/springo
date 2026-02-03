#!/bin/bash
#
# Springo 卸载脚本
# 使用方法: curl -fsSL https://raw.githubusercontent.com/dawei008/springo/main/uninstall.sh | bash
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

APP_NAME="Springo"
INSTALL_DIR="/Applications"
CONFIG_DIR="$HOME/.springo"

echo -e "${BLUE}Springo 卸载程序${NC}"
echo ""

# 确认卸载
read -p "确定要卸载 Springo 吗? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "取消卸载"
    exit 0
fi

# 关闭正在运行的应用
if pgrep -x "Springo" > /dev/null; then
    echo -e "${YELLOW}→${NC} 关闭 Springo..."
    pkill -x "Springo" || true
    sleep 2
fi

# 删除应用
if [ -d "${INSTALL_DIR}/${APP_NAME}.app" ]; then
    echo -e "${BLUE}→${NC} 删除应用程序..."
    rm -rf "${INSTALL_DIR}/${APP_NAME}.app"
    echo -e "${GREEN}✓${NC} 应用已删除"
else
    echo -e "${YELLOW}!${NC} 应用不存在"
fi

# 询问是否删除配置
if [ -d "$CONFIG_DIR" ]; then
    echo ""
    read -p "是否同时删除配置文件 (~/.springo)? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo -e "${GREEN}✓${NC} 配置文件已删除"
    else
        echo -e "${YELLOW}!${NC} 配置文件保留在 $CONFIG_DIR"
    fi
fi

echo ""
echo -e "${GREEN}卸载完成${NC}"
