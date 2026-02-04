#!/bin/bash
#
# 创建 Springo 自解压安装包
# 将 ZIP 和安装脚本合并成一个可执行文件
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查构建产物
ZIP_FILE="springo-app/dist/Springo-1.0.0-arm64-mac.zip"
if [ ! -f "$ZIP_FILE" ]; then
    echo "错误: 未找到 $ZIP_FILE"
    echo "请先运行构建: cd springo-app && npm run build"
    exit 1
fi

OUTPUT="Springo-Installer.sh"

echo "创建安装包: $OUTPUT"

# 创建安装脚本头部
cat > "$OUTPUT" << 'INSTALLER_HEADER'
#!/bin/bash
#
# Springo 一键安装程序
# 使用方法: bash Springo-Installer.sh
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

APP_NAME="Springo"
INSTALL_DIR="/Applications"

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════╗"
echo "║         Springo 安装程序                  ║"
echo "║   AI Assistant powered by AWS Bedrock     ║"
echo "╚═══════════════════════════════════════════╝"
echo -e "${NC}"

# 检查 macOS
if [ "$(uname)" != "Darwin" ]; then
    echo -e "${RED}✗${NC} 此安装程序仅支持 macOS"
    exit 1
fi

# 检查架构
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    echo -e "${GREEN}✓${NC} Apple Silicon (arm64)"
elif [ "$ARCH" = "x86_64" ]; then
    echo -e "${YELLOW}!${NC} Intel Mac - 此版本为 ARM64，可能通过 Rosetta 运行"
else
    echo -e "${RED}✗${NC} 不支持的架构: $ARCH"
    exit 1
fi

# 创建临时目录
TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT

# 提取嵌入的 ZIP
echo -e "${BLUE}→${NC} 解压安装包..."
ARCHIVE_START=$(awk '/^__ARCHIVE_BELOW__$/{print NR + 1; exit 0; }' "$0")
tail -n +$ARCHIVE_START "$0" > "$TMP_DIR/app.zip"

# 解压
unzip -q "$TMP_DIR/app.zip" -d "$TMP_DIR"
echo -e "${GREEN}✓${NC} 解压完成"

# 查找 .app
APP_PATH=$(find "$TMP_DIR" -name "*.app" -type d | head -1)
if [ -z "$APP_PATH" ]; then
    echo -e "${RED}✗${NC} 未找到应用程序"
    exit 1
fi

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

# 移除隔离属性 (关键步骤)
echo -e "${BLUE}→${NC} 配置权限..."
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
echo -e "${YELLOW}首次运行:${NC}"
echo "1. 在 Applications 中打开 Springo"
echo "2. 配置 AWS 凭证"
echo "3. 开始使用"
echo ""

read -p "是否立即打开 Springo? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    open "${INSTALL_DIR}/${APP_NAME}.app"
fi

exit 0

__ARCHIVE_BELOW__
INSTALLER_HEADER

# 追加 ZIP 文件
cat "$ZIP_FILE" >> "$OUTPUT"

# 设置可执行权限
chmod +x "$OUTPUT"

# 显示结果
SIZE=$(ls -lh "$OUTPUT" | awk '{print $5}')
echo ""
echo "✓ 安装包创建成功!"
echo ""
echo "  文件: $OUTPUT"
echo "  大小: $SIZE"
echo ""
echo "使用方法:"
echo "  bash $OUTPUT"
echo ""
echo "或分发给用户后执行:"
echo "  bash Springo-Installer.sh"
