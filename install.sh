#!/bin/bash
#
# Springo 一键安装脚本
# 使用方法: curl -fsSL https://raw.githubusercontent.com/dawei008/springo/main/install.sh | bash
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
REPO="dawei008/springo"
APP_NAME="Springo"
INSTALL_DIR="/Applications"

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════╗"
echo "║         Springo 安装程序                  ║"
echo "║   AI Assistant powered by AWS Bedrock     ║"
echo "╚═══════════════════════════════════════════╝"
echo -e "${NC}"

# 检测系统架构
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    ARCH_NAME="arm64"
    echo -e "${GREEN}✓${NC} 检测到 Apple Silicon (arm64)"
elif [ "$ARCH" = "x86_64" ]; then
    ARCH_NAME="x64"
    echo -e "${GREEN}✓${NC} 检测到 Intel Mac (x86_64)"
else
    echo -e "${RED}✗${NC} 不支持的架构: $ARCH"
    exit 1
fi

# 检查是否为 macOS
if [ "$(uname)" != "Darwin" ]; then
    echo -e "${RED}✗${NC} 此脚本仅支持 macOS"
    exit 1
fi

# 获取最新版本
echo -e "${BLUE}→${NC} 获取最新版本信息..."
LATEST_RELEASE=$(curl -s "https://api.github.com/repos/${REPO}/releases/latest")

if [ -z "$LATEST_RELEASE" ] || echo "$LATEST_RELEASE" | grep -q "Not Found"; then
    echo -e "${RED}✗${NC} 无法获取版本信息，请检查网络连接"
    exit 1
fi

VERSION=$(echo "$LATEST_RELEASE" | grep '"tag_name"' | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/')
echo -e "${GREEN}✓${NC} 最新版本: ${VERSION}"

# 构建下载 URL (优先使用 ZIP，更可靠)
DOWNLOAD_URL=$(echo "$LATEST_RELEASE" | grep "browser_download_url" | grep "${ARCH_NAME}-mac.zip" | head -1 | sed -E 's/.*"browser_download_url": *"([^"]+)".*/\1/')

if [ -z "$DOWNLOAD_URL" ]; then
    # 尝试 DMG
    DOWNLOAD_URL=$(echo "$LATEST_RELEASE" | grep "browser_download_url" | grep "${ARCH_NAME}.dmg" | head -1 | sed -E 's/.*"browser_download_url": *"([^"]+)".*/\1/')
    USE_DMG=true
else
    USE_DMG=false
fi

if [ -z "$DOWNLOAD_URL" ]; then
    echo -e "${RED}✗${NC} 未找到适合您系统的安装包"
    exit 1
fi

echo -e "${GREEN}✓${NC} 下载地址: ${DOWNLOAD_URL}"

# 创建临时目录
TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT

# 下载
echo -e "${BLUE}→${NC} 正在下载 Springo..."
if [ "$USE_DMG" = true ]; then
    DOWNLOAD_FILE="$TMP_DIR/Springo.dmg"
else
    DOWNLOAD_FILE="$TMP_DIR/Springo.zip"
fi

curl -L --progress-bar -o "$DOWNLOAD_FILE" "$DOWNLOAD_URL"

if [ ! -f "$DOWNLOAD_FILE" ]; then
    echo -e "${RED}✗${NC} 下载失败"
    exit 1
fi
echo -e "${GREEN}✓${NC} 下载完成"

# 关闭正在运行的 Springo
if pgrep -x "Springo" > /dev/null; then
    echo -e "${YELLOW}!${NC} 检测到 Springo 正在运行，正在关闭..."
    pkill -x "Springo" || true
    sleep 2
fi

# 删除旧版本
if [ -d "${INSTALL_DIR}/${APP_NAME}.app" ]; then
    echo -e "${BLUE}→${NC} 移除旧版本..."
    rm -rf "${INSTALL_DIR}/${APP_NAME}.app"
fi

# 安装
echo -e "${BLUE}→${NC} 正在安装..."

if [ "$USE_DMG" = true ]; then
    # DMG 安装方式
    MOUNT_POINT="$TMP_DIR/mount"
    mkdir -p "$MOUNT_POINT"

    hdiutil attach "$DOWNLOAD_FILE" -mountpoint "$MOUNT_POINT" -nobrowse -quiet

    if [ -d "$MOUNT_POINT/${APP_NAME}.app" ]; then
        cp -R "$MOUNT_POINT/${APP_NAME}.app" "${INSTALL_DIR}/"
    else
        echo -e "${RED}✗${NC} DMG 中未找到应用程序"
        hdiutil detach "$MOUNT_POINT" -quiet
        exit 1
    fi

    hdiutil detach "$MOUNT_POINT" -quiet
else
    # ZIP 安装方式
    unzip -q "$DOWNLOAD_FILE" -d "$TMP_DIR"

    # 查找 .app
    APP_PATH=$(find "$TMP_DIR" -name "*.app" -type d | head -1)

    if [ -z "$APP_PATH" ]; then
        echo -e "${RED}✗${NC} ZIP 中未找到应用程序"
        exit 1
    fi

    cp -R "$APP_PATH" "${INSTALL_DIR}/"
fi

echo -e "${GREEN}✓${NC} 安装完成"

# 移除隔离属性 (关键步骤 - 绕过 Gatekeeper)
echo -e "${BLUE}→${NC} 配置应用权限..."
xattr -cr "${INSTALL_DIR}/${APP_NAME}.app" 2>/dev/null || true
echo -e "${GREEN}✓${NC} 权限配置完成"

# 完成
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         安装成功！                        ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════╝${NC}"
echo ""
echo -e "应用位置: ${BLUE}${INSTALL_DIR}/${APP_NAME}.app${NC}"
echo ""
echo -e "${YELLOW}首次运行说明:${NC}"
echo "1. 打开 Springo 应用"
echo "2. 配置 AWS 凭证 (Access Key 或 AWS Profile)"
echo "3. 开始使用 AI 助手"
echo ""
echo -e "${BLUE}提示:${NC} 如果提示"无法验证开发者"，请前往:"
echo "    系统设置 → 隐私与安全性 → 点击"仍要打开""
echo ""

# 询问是否立即打开
read -p "是否立即打开 Springo? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    open "${INSTALL_DIR}/${APP_NAME}.app"
fi
