#!/bin/bash
#
# Springo 本地一键安装脚本
# 使用方法: ./local-install.sh
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

APP_NAME="Springo"
INSTALL_DIR="/Applications"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════╗"
echo "║      Springo 本地安装程序                 ║"
echo "║   AI Assistant powered by AWS Bedrock     ║"
echo "╚═══════════════════════════════════════════╝"
echo -e "${NC}"

cd "$SCRIPT_DIR"

# 检查是否有已构建的应用
APP_PATH=""
if [ -d "springo-app/dist/mac-arm64/${APP_NAME}.app" ]; then
    APP_PATH="springo-app/dist/mac-arm64/${APP_NAME}.app"
elif [ -d "springo-app/dist/mac/${APP_NAME}.app" ]; then
    APP_PATH="springo-app/dist/mac/${APP_NAME}.app"
fi

if [ -z "$APP_PATH" ]; then
    echo -e "${YELLOW}!${NC} 未找到已构建的应用，需要先构建"
    echo ""

    # 检查依赖
    echo -e "${BLUE}→${NC} 检查依赖..."

    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}✗${NC} 未安装 Python3"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Python3 已安装"

    if ! command -v node &> /dev/null; then
        echo -e "${RED}✗${NC} 未安装 Node.js"
        echo "  请安装: brew install node"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Node.js 已安装"

    # 构建后端
    echo -e "${BLUE}→${NC} 构建后端 (PyInstaller)..."
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    source venv/bin/activate
    pip install -q pyinstaller
    pip install -q -r requirements.txt

    pyinstaller --onefile --name springo-backend \
        --hidden-import=flask \
        --hidden-import=boto3 \
        --hidden-import=botocore \
        --collect-all tiktoken \
        --distpath dist \
        full_proxy_server.py 2>/dev/null

    deactivate
    echo -e "${GREEN}✓${NC} 后端构建完成"

    # 构建前端
    echo -e "${BLUE}→${NC} 构建前端 (Electron)..."
    cd springo-app
    npm install --silent
    npm run build
    cd ..
    echo -e "${GREEN}✓${NC} 前端构建完成"

    # 重新查找构建产物
    if [ -d "springo-app/dist/mac-arm64/${APP_NAME}.app" ]; then
        APP_PATH="springo-app/dist/mac-arm64/${APP_NAME}.app"
    elif [ -d "springo-app/dist/mac/${APP_NAME}.app" ]; then
        APP_PATH="springo-app/dist/mac/${APP_NAME}.app"
    fi
fi

if [ -z "$APP_PATH" ]; then
    echo -e "${RED}✗${NC} 构建失败"
    exit 1
fi

echo -e "${GREEN}✓${NC} 找到应用: $APP_PATH"

# 关闭正在运行的应用
if pgrep -x "$APP_NAME" > /dev/null; then
    echo -e "${YELLOW}!${NC} 关闭正在运行的 $APP_NAME..."
    pkill -x "$APP_NAME" || true
    sleep 2
fi

# 删除旧版本
if [ -d "${INSTALL_DIR}/${APP_NAME}.app" ]; then
    echo -e "${BLUE}→${NC} 移除旧版本..."
    rm -rf "${INSTALL_DIR}/${APP_NAME}.app"
fi

# 安装
echo -e "${BLUE}→${NC} 安装到 ${INSTALL_DIR}..."
cp -R "$APP_PATH" "${INSTALL_DIR}/"

# 移除隔离属性
echo -e "${BLUE}→${NC} 配置权限..."
xattr -cr "${INSTALL_DIR}/${APP_NAME}.app" 2>/dev/null || true

# 完成
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         安装成功！                        ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════╝${NC}"
echo ""
echo -e "应用位置: ${BLUE}${INSTALL_DIR}/${APP_NAME}.app${NC}"
echo ""
echo -e "${YELLOW}使用说明:${NC}"
echo "1. 打开 Springo 应用"
echo "2. 配置 AWS 凭证 (Access Key 或 AWS Profile)"
echo "3. 开始使用 AI 助手"
echo ""

# 询问是否立即打开
read -p "是否立即打开 Springo? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    open "${INSTALL_DIR}/${APP_NAME}.app"
fi
