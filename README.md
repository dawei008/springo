# Springo

基于 AWS Bedrock 的独立 AI 助手桌面应用。

## 架构

```
┌─────────────────────────┐
│   Springo Desktop App   │
│   (Electron)            │
└───────────┬─────────────┘
            │ HTTP API
            │ localhost:8080
            ▼
┌─────────────────────────┐
│   Flask Backend Server  │
│                         │
│   - MCP 工具系统         │
│   - 上下文管理           │
│   - AWS 认证管理         │
└───────────┬─────────────┘
            │ AWS SDK
            ▼
┌─────────────────────────┐
│   AWS Bedrock           │
│   (Claude Models)       │
└─────────────────────────┘
```

## 功能特性

- **AWS Bedrock 集成** - 使用自有 AWS 账户调用 Claude 模型
- **28+ MCP 工具** - 文件系统、终端、Git、Web 搜索、浏览器自动化
- **上下文管理** - Token 计数和自动摘要
- **多认证方式** - AWS Profile、Access Keys、AWS SSO
- **技能系统** - 可扩展的技能模块

## 前置要求

1. **AWS 账户** - 已开通 Bedrock Claude 模型访问权限
2. **Python 3.10+**
3. **Node.js 18+**

## 快速开始

### 1. 安装依赖

```bash
cd claude-cowork-bedrock-proxy

# Python 依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Electron 依赖
cd springo-app
npm install
cd ..
```

### 2. 启动应用

**方式一：分开启动**

```bash
# 终端 1: 启动后端服务器
python full_proxy_server.py

# 终端 2: 启动 Electron 应用
cd springo-app && npm start
```

**方式二：通过 Electron 自动启动（开发中）**

```bash
cd springo-app && npm start
```

### 3. 配置 AWS 认证

打开应用后，点击设置图标配置 AWS 认证：

- **AWS Profile**: 从 `~/.aws/credentials` 选择已配置的 Profile
- **Access Key**: 手动输入 Access Key ID 和 Secret Access Key
- **AWS SSO**: 通过 IAM Identity Center 登录

## 目录结构

```
claude-cowork-bedrock-proxy/
├── full_proxy_server.py      # Flask 后端服务器
├── mcp_tools.py              # MCP 工具实现 (28+ 工具)
├── context_manager.py        # 上下文和 Token 管理
├── mcp_client.py             # 外部 MCP 服务器客户端
├── skill_loader.py           # 技能系统加载器
├── requirements.txt          # Python 依赖
│
├── auth/                     # AWS 认证模块
│   ├── config_manager.py     # 认证配置管理
│   ├── aws_profiles.py       # AWS Profile 解析
│   └── sso_handler.py        # AWS SSO 处理
│
├── ui/                       # Web UI (配置界面)
│   ├── routes.py             # Flask 路由
│   └── templates/
│       └── config.html       # 配置页面
│
├── springo-app/              # Electron 桌面应用
│   ├── main.js               # Electron 主进程
│   ├── preload.js            # 预加载脚本
│   ├── renderer/
│   │   └── index.html        # 主界面
│   └── package.json
│
├── skills/                   # 技能模块目录
├── workspace/                # 工作目录
└── tests/                    # 测试文件
```

## MCP 工具列表

| 分类 | 工具 | 描述 |
|------|------|------|
| **文件系统** | `read_file` | 读取文件内容 |
| | `write_file` | 写入文件 |
| | `list_directory` | 列出目录内容 |
| **终端** | `bash_run` | 执行 bash 命令 |
| **Git** | `git_status` | 获取 Git 状态 |
| | `git_diff` | 查看文件差异 |
| | `git_commit` | 提交代码 |
| | `git_push` | 推送代码 |
| **Web** | `web_search` | 网页搜索 (Brave/Tavily/Custom) |
| | `extract_webpage` | 提取网页内容 |
| **浏览器** | `browser_action` | Playwright 浏览器自动化 |

## AWS Bedrock 模型支持

| Anthropic Model | Bedrock Model ID |
|-----------------|------------------|
| claude-3-5-sonnet-20241022 | us.anthropic.claude-3-5-sonnet-20241022-v2:0 |
| claude-3-5-haiku-20241022 | us.anthropic.claude-3-5-haiku-20241022-v1:0 |
| claude-3-opus-20240229 | us.anthropic.claude-3-opus-20240229-v1:0 |
| claude-sonnet-4-20250514 | us.anthropic.claude-sonnet-4-20250514-v1:0 |
| claude-opus-4-5-20251101 | us.anthropic.claude-opus-4-5-20251101-v1:0 |

## API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/v1/messages` | POST | 发送消息 (兼容 Anthropic API) |
| `/v1/tools` | GET | 获取工具列表 |
| `/v1/tools/execute` | POST | 执行工具 |
| `/v1/skills` | GET | 获取技能列表 |
| `/v1/context/stats` | POST | 获取上下文统计 |

## 开发

### 运行测试

```bash
# 启动 Electron 应用 (启用调试端口)
cd springo-app && npm start

# 运行 Playwright 测试
python tests/test_file_browser.py
python tests/test_unified_tools.py
```

### 修改后重启规则

| 修改的文件 | 是否需要重启 |
|-----------|-------------|
| `main.js` | ✅ 重启 Electron |
| `preload.js` | ✅ 重启 Electron |
| `renderer/index.html` | ❌ 刷新页面即可 |
| `full_proxy_server.py` | ❌ 自动重载 |
| `mcp_tools.py` | ❌ 自动重载 |

## 故障排除

### 后端连接失败

```bash
# 检查后端是否运行
curl http://127.0.0.1:8080/health
```

### AWS 认证错误

```bash
# 验证 AWS 凭证
aws sts get-caller-identity

# 检查 Bedrock 模型访问权限
aws bedrock list-foundation-models --region us-east-1
```

## License

MIT License
