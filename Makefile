# Springo 本地构建与安装
# 使用方法: make install

.PHONY: all build install uninstall clean backend frontend help

# 配置
APP_NAME := Springo
INSTALL_DIR := /Applications
BACKEND_DIST := dist/springo-backend
FRONTEND_DIST := springo-app/dist

# 默认目标
all: help

help:
	@echo "╔═══════════════════════════════════════════╗"
	@echo "║         Springo 构建工具                  ║"
	@echo "╚═══════════════════════════════════════════╝"
	@echo ""
	@echo "可用命令:"
	@echo "  make install    - 构建并安装到 /Applications"
	@echo "  make build      - 仅构建（不安装）"
	@echo "  make uninstall  - 卸载应用"
	@echo "  make clean      - 清理构建产物"
	@echo "  make backend    - 仅构建后端"
	@echo "  make frontend   - 仅构建前端"
	@echo ""

# 构建后端 (PyInstaller)
backend:
	@echo "→ 构建后端..."
	@if [ ! -d "venv" ]; then \
		python3 -m venv venv; \
	fi
	@. venv/bin/activate && pip install -q pyinstaller -r requirements.txt
	@. venv/bin/activate && pyinstaller --onefile --name springo-backend \
		--hidden-import=flask \
		--hidden-import=boto3 \
		--hidden-import=botocore \
		--collect-all tiktoken \
		full_proxy_server.py
	@echo "✓ 后端构建完成"

# 构建前端 (Electron)
frontend: backend
	@echo "→ 构建前端..."
	@cd springo-app && npm install --silent && npm run build
	@echo "✓ 前端构建完成"

# 完整构建
build: frontend
	@echo "✓ 构建完成: $(FRONTEND_DIST)"

# 安装到 /Applications
install: build
	@echo "→ 安装 $(APP_NAME)..."
	@# 关闭正在运行的应用
	@pkill -x "$(APP_NAME)" 2>/dev/null || true
	@sleep 1
	@# 删除旧版本
	@rm -rf "$(INSTALL_DIR)/$(APP_NAME).app"
	@# 复制新版本
	@cp -R "$(FRONTEND_DIST)/mac-arm64/$(APP_NAME).app" "$(INSTALL_DIR)/" 2>/dev/null || \
		cp -R "$(FRONTEND_DIST)/mac/$(APP_NAME).app" "$(INSTALL_DIR)/"
	@# 移除隔离属性
	@xattr -cr "$(INSTALL_DIR)/$(APP_NAME).app" 2>/dev/null || true
	@echo ""
	@echo "╔═══════════════════════════════════════════╗"
	@echo "║         安装成功！                        ║"
	@echo "╚═══════════════════════════════════════════╝"
	@echo ""
	@echo "应用位置: $(INSTALL_DIR)/$(APP_NAME).app"
	@echo ""
	@echo "运行: open /Applications/$(APP_NAME).app"

# 快速安装（跳过构建，使用已有的构建产物）
install-quick:
	@echo "→ 快速安装 $(APP_NAME)..."
	@if [ ! -d "$(FRONTEND_DIST)/mac-arm64/$(APP_NAME).app" ] && [ ! -d "$(FRONTEND_DIST)/mac/$(APP_NAME).app" ]; then \
		echo "✗ 未找到构建产物，请先运行 make build"; \
		exit 1; \
	fi
	@pkill -x "$(APP_NAME)" 2>/dev/null || true
	@sleep 1
	@rm -rf "$(INSTALL_DIR)/$(APP_NAME).app"
	@cp -R "$(FRONTEND_DIST)/mac-arm64/$(APP_NAME).app" "$(INSTALL_DIR)/" 2>/dev/null || \
		cp -R "$(FRONTEND_DIST)/mac/$(APP_NAME).app" "$(INSTALL_DIR)/"
	@xattr -cr "$(INSTALL_DIR)/$(APP_NAME).app" 2>/dev/null || true
	@echo "✓ 安装完成"

# 卸载
uninstall:
	@echo "→ 卸载 $(APP_NAME)..."
	@pkill -x "$(APP_NAME)" 2>/dev/null || true
	@rm -rf "$(INSTALL_DIR)/$(APP_NAME).app"
	@echo "✓ 卸载完成"
	@echo ""
	@read -p "是否同时删除配置文件 (~/.springo)? [y/N] " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		rm -rf ~/.springo; \
		echo "✓ 配置文件已删除"; \
	fi

# 清理构建产物
clean:
	@echo "→ 清理构建产物..."
	@rm -rf build dist springo-app/dist
	@rm -rf __pycache__ */__pycache__ */*/__pycache__
	@rm -f *.spec
	@echo "✓ 清理完成"
