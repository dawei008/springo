# Springo (Claude Bedrock Proxy) 项目规范

## 测试规范

> **强制要求**：本项目的所有测试必须是端到端（E2E）测试，且必须通过 Electron 应用执行。禁止使用独立的单元测试、浏览器测试或其他绕过 Electron 的测试方式。

### 端到端测试原则

1. **唯一测试入口**：Electron 应用是所有测试的唯一入口点
2. **真实环境验证**：测试必须在真实的 Electron 运行时环境中进行，确保功能在实际使用场景下正常工作
3. **全链路覆盖**：测试应覆盖从用户界面到后端服务的完整链路

### 默认测试环境：Electron

所有 UI 和功能测试必须基于 Electron 应用进行，而非 Web 浏览器。

**测试方式：**
```bash
# 使用 Playwright 连接到运行中的 Electron 应用
python tests/test_xxx.py
```

**测试前置条件：**
1. Electron 应用必须已启动并启用远程调试端口
2. 启动命令：`cd springo-app && npm start`
3. 调试端口：`http://localhost:9222`

**测试代码模板：**
```python
from playwright.async_api import async_playwright

async def test_feature():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]
        # 执行测试...
```

### 修改后重启和测试规范

**必须重启 Electron 应用的情况：**

| 修改的文件 | 是否需要重启 | 说明 |
|-----------|-------------|------|
| `main.js` | ✅ 必须重启 | Electron 主进程代码 |
| `preload.js` | ✅ 必须重启 | 预加载脚本，暴露 API |
| `renderer/index.html` | ❌ 刷新即可 | 渲染进程代码，页面刷新生效 |
| `full_proxy_server.py` | ❌ 自动重载 | Flask debug 模式自动重载 |
| `mcp_tools.py` | ❌ 自动重载 | 被服务器导入，自动重载 |

**重启流程：**
```bash
# 1. 在运行 Electron 的终端按 Ctrl+C 停止
# 2. 重新启动
cd springo-app && npm start
```

**修改后必须测试：**
每次新增功能或修改代码后，必须通过 Playwright 进行 Electron 测试验证：

```python
# 快速验证模板
import asyncio
from playwright.async_api import async_playwright

async def quick_test():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]
        await page.reload()  # 刷新加载最新代码
        await asyncio.sleep(2)

        # 验证新功能...
        result = await page.evaluate("typeof newFunction === 'function'")
        print(f"功能可用: {result}")

asyncio.run(quick_test())
```

### 特殊情况处理

如果由于以下原因无法进行 Electron 测试，**必须先询问用户确认**：

1. Electron 应用未启动或无法连接
2. 需要测试的功能与 Electron 环境不兼容
3. 需要进行纯后端 API 测试（无 UI 交互）
4. 性能测试或压力测试场景

**询问示例：**
> "Electron 应用当前无法连接，是否可以使用 Web 浏览器进行测试？"

## 项目结构

```
claude-cowork-bedrock-proxy/
├── full_proxy_server.py    # Flask 后端服务器
├── mcp_tools.py            # MCP 工具定义和实现
├── springo-app/            # Electron 桌面应用
│   ├── main.js             # Electron 主进程
│   ├── renderer/
│   │   └── index.html      # 前端界面
│   └── package.json
├── tests/                  # 测试文件目录
│   ├── test_file_browser.py
│   └── test_unified_tools.py
└── CLAUDE.md               # 本文件
```

## 开发规范

### UI/UX 规范

> **禁止使用 Emoji**：在 Springo 的所有 UI 界面和代码中，**禁止使用 emoji 字符**。应使用 SVG 图标替代。
>
> - 聊天头像：使用 SVG 图标（参考 `app.js` 中的 `dogIcon`、`userIcon` 定义）
> - 状态指示：使用 SVG 图标或 CSS 样式
> - 按钮图标：使用 SVG 或 Unicode 符号（如 `↻`、`×`）
> - 系统提示词已配置禁止 Claude 在回复中使用 emoji

### 后端服务器
- 端口：`8080`
- 健康检查：`GET /health`
- 工具执行：`POST /v1/tools/execute`
  - 请求体：`{"name": "tool_name", "input": {...}}`

### 前端开发
- 所有前端代码在 `springo-app/renderer/index.html`
- 使用 CSS 变量进行主题管理
- API 基础 URL：`BASE_URL` 变量
- 图标使用 SVG（参考 `index.html` 中的 welcome-icon 样式）

### 工具开发
- 工具定义在 `mcp_tools.py` 的 `TOOL_DEFINITIONS` 列表
- 工具处理函数在 `TOOL_HANDLERS` 字典
- 统一工具模式：`git`、`browser` 使用 `action` 参数路由

## 常用命令

```bash
# 启动后端服务器
python full_proxy_server.py

# 启动 Electron 应用
cd springo-app && npm start

# 运行测试
python tests/test_file_browser.py
python tests/test_unified_tools.py
```
