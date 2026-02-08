# Springo Agent Teams - 设计文档

> 版本: 1.0
> 创建日期: 2026-02-06
> 状态: DRAFT

---

## 1. 概述

### 1.1 什么是 Agent Teams

Agent Teams 是一个多 Agent 协作系统，允许多个 AI Agent 实例并行工作、相互通信、协调任务，像一个真正的开发团队一样完成复杂项目。

### 1.2 设计目标

| 目标 | 说明 |
|------|------|
| **并行执行** | 多个 Agent 同时处理项目的不同部分 |
| **自主协调** | Agents 之间自动协调，减少人工干预 |
| **任务管理** | 共享任务列表，支持依赖关系和状态追踪 |
| **消息通信** | Agent 之间的直接消息和广播通信 |
| **兼容性** | 与现有 Springo 架构无缝集成 |

### 1.3 与 Claude Code Agent Teams 的对比

| 特性 | Claude Code | Springo (设计) |
|------|-------------|----------------|
| 架构 | CLI + 本地进程 | FastAPI + 后台任务 |
| 存储 | 本地文件系统 | 本地文件 + 可选 Redis |
| 通信 | 文件 Inbox | WebSocket + 文件 |
| 前端 | Terminal (tmux/iTerm2) | Electron GUI |
| 可视化 | Split Panes | 专用 Teams Panel |

---

## 2. 核心架构

### 2.1 系统组件

```
┌─────────────────────────────────────────────────────────────────┐
│                        Springo Frontend                          │
│                    (Electron + Teams Panel)                      │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ WebSocket / REST API
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Springo FastAPI Backend                     │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    Teams Router (/v1/teams)                  │ │
│  │  - POST /teams              创建团队                        │ │
│  │  - GET /teams               列出团队                        │ │
│  │  - POST /teams/{id}/spawn   生成 Teammate                   │ │
│  │  - POST /teams/{id}/message 发送消息                        │ │
│  │  - POST /teams/{id}/tasks   创建任务                        │ │
│  │  - DELETE /teams/{id}       清理团队                        │ │
│  └─────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    Teams Service Layer                       │ │
│  │  - TeamManager: 团队生命周期管理                             │ │
│  │  - AgentOrchestrator: Agent 实例协调                        │ │
│  │  - TaskManager: 任务队列和依赖管理                          │ │
│  │  - MessageBroker: 消息路由和投递                            │ │
│  └─────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    Agent Executor Pool                       │ │
│  │  - BackgroundAgent: 独立运行的 Agent 实例                   │ │
│  │  - BedrockClient: Claude API 调用                           │ │
│  │  - ToolExecutor: MCP 工具执行                               │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Storage Layer                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Teams     │  │   Tasks     │  │       Messages          │  │
│  │   Config    │  │   Queue     │  │       (Inboxes)         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│        ~/.springo/teams/{name}/config.json                       │
│        ~/.springo/tasks/{name}/*.json                            │
│        ~/.springo/teams/{name}/inboxes/*.json                    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件说明

#### 2.2.1 Team (团队)

```python
@dataclass
class Team:
    name: str                    # 团队名称 (唯一标识)
    description: str             # 团队描述
    lead_agent_id: str           # 领导 Agent ID
    members: List[TeamMember]    # 成员列表
    created_at: datetime
    status: TeamStatus           # active, paused, completed, cleaned
```

#### 2.2.2 TeamMember (团队成员)

```python
@dataclass
class TeamMember:
    agent_id: str               # Agent 唯一 ID (name@team)
    name: str                   # 显示名称
    agent_type: AgentType       # leader, worker, reviewer, researcher
    model: str                  # claude-3-5-sonnet, haiku, opus
    color: str                  # UI 显示颜色
    status: AgentStatus         # idle, working, waiting, shutdown
    current_task_id: Optional[str]
    joined_at: datetime
```

#### 2.2.3 Task (任务)

```python
@dataclass
class Task:
    id: str                     # 任务 ID (递增数字)
    team_name: str              # 所属团队
    subject: str                # 任务主题
    description: str            # 详细描述
    status: TaskStatus          # pending, in_progress, completed, blocked
    owner: Optional[str]        # 当前负责人 agent_id
    dependencies: List[str]     # 依赖的任务 ID 列表
    created_at: datetime
    completed_at: Optional[datetime]
    result: Optional[str]       # 完成结果
```

#### 2.2.4 Message (消息)

```python
@dataclass
class Message:
    id: str                     # 消息 ID
    type: MessageType           # text, task_update, shutdown_request, etc.
    from_agent: str             # 发送者
    to_agent: str               # 接收者 (或 "broadcast")
    content: Any                # 消息内容
    timestamp: datetime
    read: bool                  # 是否已读
```

---

## 3. API 设计

### 3.1 Teams Router 端点

```
POST   /v1/teams                      # 创建团队
GET    /v1/teams                      # 列出所有团队
GET    /v1/teams/{team_name}          # 获取团队详情
DELETE /v1/teams/{team_name}          # 删除/清理团队

POST   /v1/teams/{team_name}/spawn    # 生成新 Teammate
POST   /v1/teams/{team_name}/shutdown # 请求 Teammate 关闭
GET    /v1/teams/{team_name}/members  # 列出团队成员

POST   /v1/teams/{team_name}/tasks           # 创建任务
GET    /v1/teams/{team_name}/tasks           # 列出任务
GET    /v1/teams/{team_name}/tasks/{task_id} # 获取任务详情
PATCH  /v1/teams/{team_name}/tasks/{task_id} # 更新任务状态
POST   /v1/teams/{team_name}/tasks/{task_id}/claim  # 认领任务

POST   /v1/teams/{team_name}/messages           # 发送消息
GET    /v1/teams/{team_name}/messages/{agent_id} # 获取 Agent 收件箱
POST   /v1/teams/{team_name}/broadcast          # 广播消息
```

### 3.2 请求/响应模型

#### 创建团队

```python
# POST /v1/teams
class CreateTeamRequest(BaseModel):
    name: str
    description: str
    initial_tasks: Optional[List[TaskCreate]] = None

class CreateTeamResponse(BaseModel):
    success: bool
    team: Team
    lead_agent_id: str
```

#### 生成 Teammate

```python
# POST /v1/teams/{team_name}/spawn
class SpawnTeammateRequest(BaseModel):
    name: str                           # Teammate 名称
    agent_type: str = "worker"          # worker, reviewer, researcher
    model: str = "claude-3-5-sonnet-20241022"
    prompt: str                         # 初始指令
    tools: Optional[List[str]] = None   # 允许使用的工具
    auto_claim_tasks: bool = True       # 是否自动认领任务

class SpawnTeammateResponse(BaseModel):
    success: bool
    agent_id: str
    status: str
```

#### 发送消息

```python
# POST /v1/teams/{team_name}/messages
class SendMessageRequest(BaseModel):
    from_agent: str
    to_agent: str           # agent_id 或 "broadcast"
    message_type: str = "text"
    content: Any

class SendMessageResponse(BaseModel):
    success: bool
    message_id: str
```

### 3.3 WebSocket 事件 (实时通信)

```
WS /v1/teams/{team_name}/ws

Events (Server -> Client):
- team_update: 团队状态变化
- member_joined: 新成员加入
- member_left: 成员离开
- task_created: 新任务创建
- task_updated: 任务状态更新
- message_received: 新消息到达
- agent_output: Agent 输出流

Events (Client -> Server):
- send_message: 发送消息
- claim_task: 认领任务
- update_task: 更新任务
```

---

## 4. 数据存储设计

### 4.1 文件结构

```
~/.springo/
├── teams/
│   └── {team-name}/
│       ├── config.json              # 团队配置
│       └── inboxes/
│           ├── team-lead.json       # Leader 收件箱
│           ├── worker-1.json        # Worker 收件箱
│           └── ...
├── tasks/
│   └── {team-name}/
│       ├── 1.json                   # 任务 1
│       ├── 2.json                   # 任务 2
│       └── ...
└── agents/
    └── {agent-id}/
        ├── context.json             # Agent 上下文
        └── history.jsonl            # Agent 对话历史
```

### 4.2 Team Config 示例

```json
{
  "name": "feature-auth",
  "description": "Implementing OAuth2 authentication",
  "leadAgentId": "team-lead@feature-auth",
  "createdAt": "2026-02-06T23:00:00Z",
  "status": "active",
  "members": [
    {
      "agentId": "team-lead@feature-auth",
      "name": "team-lead",
      "agentType": "leader",
      "model": "claude-3-5-sonnet-20241022",
      "color": "#4A90D9",
      "status": "idle",
      "currentTaskId": null,
      "joinedAt": "2026-02-06T23:00:00Z"
    },
    {
      "agentId": "security-reviewer@feature-auth",
      "name": "security-reviewer",
      "agentType": "reviewer",
      "model": "claude-3-5-sonnet-20241022",
      "color": "#D94A4A",
      "status": "working",
      "currentTaskId": "2",
      "joinedAt": "2026-02-06T23:01:00Z"
    }
  ]
}
```

### 4.3 Task 示例

```json
{
  "id": "2",
  "teamName": "feature-auth",
  "subject": "Security Review",
  "description": "Review authentication module for security vulnerabilities",
  "status": "in_progress",
  "owner": "security-reviewer@feature-auth",
  "dependencies": ["1"],
  "createdAt": "2026-02-06T23:00:30Z",
  "completedAt": null,
  "result": null
}
```

### 4.4 Message 示例

```json
{
  "id": "msg-001",
  "type": "text",
  "fromAgent": "team-lead@feature-auth",
  "toAgent": "security-reviewer@feature-auth",
  "content": "Please prioritize reviewing the JWT token validation",
  "timestamp": "2026-02-06T23:05:00Z",
  "read": false
}
```

---

## 5. Agent 执行模型

### 5.1 Agent 生命周期

```
┌─────────┐     ┌──────────┐     ┌─────────┐     ┌──────────┐
│  SPAWN  │ --> │  INIT    │ --> │ WORKING │ --> │ SHUTDOWN │
└─────────┘     └──────────┘     └─────────┘     └──────────┘
                     │                │
                     ▼                ▼
               Load Context     Execute Tasks
               Load Tools       Send Messages
               Join Team        Claim Tasks
```

### 5.2 Agent 执行循环

```python
async def agent_loop(agent: Agent):
    """Agent 主执行循环"""
    while not agent.should_shutdown:
        # 1. 检查收件箱
        messages = await agent.check_inbox()
        for msg in messages:
            await agent.handle_message(msg)
        
        # 2. 检查是否有待处理任务
        if agent.current_task is None and agent.auto_claim:
            task = await agent.claim_available_task()
            if task:
                agent.current_task = task
        
        # 3. 执行当前任务
        if agent.current_task:
            result = await agent.work_on_task()
            if result.completed:
                await agent.complete_task(result)
                agent.current_task = None
        
        # 4. 如果空闲，通知 Leader
        if agent.current_task is None:
            await agent.notify_idle()
        
        # 5. 短暂休眠
        await asyncio.sleep(1)
```

### 5.3 Agent 与 Bedrock 交互

```python
async def work_on_task(self, task: Task) -> TaskResult:
    """执行任务，使用 Bedrock Claude"""
    
    # 构建 System Prompt
    system_prompt = self.build_system_prompt(task)
    
    # 构建消息
    messages = [
        {"role": "user", "content": task.description}
    ]
    
    # 调用 Bedrock (支持流式)
    async for event in self.bedrock.invoke_stream(
        model=self.model,
        system=system_prompt,
        messages=messages,
        tools=self.available_tools
    ):
        # 处理工具调用
        if event.type == "tool_use":
            result = await self.execute_tool(event)
            messages.append({"role": "assistant", "content": event})
            messages.append({"role": "user", "content": result})
        
        # 处理文本输出
        elif event.type == "text":
            await self.stream_output(event.text)
    
    return TaskResult(...)
```

---

## 6. 协作模式

### 6.1 支持的协作模式

| 模式 | 描述 | 适用场景 |
|------|------|----------|
| **Leader** | 层级式任务分配，Leader 协调所有工作 | 复杂项目管理 |
| **Swarm** | 并行处理相似工作，自动认领任务 | 批量代码审查 |
| **Pipeline** | 顺序多阶段工作流，有依赖关系 | CI/CD 流程 |
| **Council** | 多视角决策，Agents 讨论和投票 | 架构设计评审 |
| **Watchdog** | 质量监控，持续审查其他 Agent 的工作 | 安全审计 |

### 6.2 模式示例: Parallel Code Review

```
┌─────────────────────────────────────────────────────────────┐
│                      Team Lead                               │
│                  (Coordinator)                               │
└─────────────────────────────────────────────────────────────┘
           │              │              │
           ▼              ▼              ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │ Security │   │ Perform- │   │   Test   │
    │ Reviewer │   │   ance   │   │ Coverage │
    └──────────┘   └──────────┘   └──────────┘
           │              │              │
           ▼              ▼              ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │ Task #1  │   │ Task #2  │   │ Task #3  │
    │ Security │   │ Perf.    │   │ Tests    │
    └──────────┘   └──────────┘   └──────────┘
           │              │              │
           └──────────────┼──────────────┘
                          ▼
                   ┌──────────┐
                   │ Findings │
                   │  Report  │
                   └──────────┘
```

### 6.3 模式示例: Pipeline

```
┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
│ Task 1 │ -> │ Task 2 │ -> │ Task 3 │ -> │ Task 4 │
│Research│    │ Design │    │Implement│   │ Review │
└────────┘    └────────┘    └────────┘    └────────┘
    │             │              │             │
    ▼             ▼              ▼             ▼
┌────────┐   ┌────────┐    ┌────────┐    ┌────────┐
│Researcher│  │Architect│   │Developer│   │Reviewer│
└────────┘   └────────┘    └────────┘    └────────┘
```

---

## 7. 前端 UI 设计

### 7.1 Teams Panel 布局

```
┌─────────────────────────────────────────────────────────────────┐
│ Teams                                                     [+]   │
├─────────────────────────────────────────────────────────────────┤
│ ▼ feature-auth (3 members, 5 tasks)                            │
│   ├─ [Lead] team-lead          ● idle                          │
│   ├─ [Worker] security-rev     ● working on #2                 │
│   └─ [Worker] test-coverage    ● working on #3                 │
│                                                                 │
│ ▶ refactor-api (2 members, 3 tasks)                            │
├─────────────────────────────────────────────────────────────────┤
│ Tasks for: feature-auth                              [+ Add]    │
├─────────────────────────────────────────────────────────────────┤
│ ✓ #1 Research OAuth providers        (completed)               │
│ ◐ #2 Security Review                 (in_progress) @security   │
│ ◐ #3 Test Coverage Analysis          (in_progress) @test       │
│ ○ #4 Implement JWT validation        (pending) blocked by #2   │
│ ○ #5 Write documentation             (pending) blocked by #4   │
├─────────────────────────────────────────────────────────────────┤
│ Messages                                              [Refresh] │
├─────────────────────────────────────────────────────────────────┤
│ [security-rev -> team-lead] Found 2 potential vulnerabilities  │
│ [team-lead -> security-rev] Please document them in detail     │
│ [test-coverage -> team-lead] Coverage analysis complete: 78%   │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 Agent Output Panel

```
┌─────────────────────────────────────────────────────────────────┐
│ Agent: security-reviewer@feature-auth                    [Stop] │
├─────────────────────────────────────────────────────────────────┤
│ Current Task: #2 Security Review                               │
│ Status: Analyzing authentication/jwt_validator.py              │
├─────────────────────────────────────────────────────────────────┤
│ > Checking JWT token validation...                             │
│ > [Tool Call] read_file: authentication/jwt_validator.py       │
│ > Found potential issue: Missing token expiration check        │
│ > [Tool Call] grep: "exp" in authentication/                   │
│ > Confirmed: Token expiration not validated                    │
│ > Documenting finding...                                       │
│ > [Sending message to team-lead]                               │
│ █                                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. 实现计划

### 8.1 Phase 1: 核心基础 (3 天)

| 任务 | 优先级 | 估时 |
|------|--------|------|
| 设计并实现数据模型 (Team, Task, Message) | P0 | 0.5 天 |
| 实现 TeamManager 服务 | P0 | 1 天 |
| 实现 TaskManager 服务 | P0 | 0.5 天 |
| 实现 MessageBroker 服务 | P0 | 0.5 天 |
| 实现 Teams Router API | P0 | 0.5 天 |

### 8.2 Phase 2: Agent 执行 (3 天)

| 任务 | 优先级 | 估时 |
|------|--------|------|
| 实现 AgentOrchestrator | P0 | 1 天 |
| 实现 BackgroundAgent 执行循环 | P0 | 1 天 |
| 集成 Bedrock 和工具执行 | P0 | 0.5 天 |
| 实现 Agent 间消息传递 | P1 | 0.5 天 |

### 8.3 Phase 3: 前端集成 (2 天)

| 任务 | 优先级 | 估时 |
|------|--------|------|
| 实现 WebSocket 实时通信 | P0 | 0.5 天 |
| 实现 Teams Panel UI | P0 | 1 天 |
| 实现 Agent Output Panel | P1 | 0.5 天 |

### 8.4 Phase 4: 测试和优化 (2 天)

| 任务 | 优先级 | 估时 |
|------|--------|------|
| 编写 E2E 测试 | P0 | 1 天 |
| 性能优化和错误处理 | P1 | 0.5 天 |
| 文档编写 | P1 | 0.5 天 |

**总计: 10 天**

---

## 9. 风险和缓解措施

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Agent 执行成本高 | 高 | 使用 Haiku 模型；任务批处理；限制并行数 |
| Agent 协调复杂 | 中 | 简化通信协议；明确责任边界 |
| 消息丢失 | 中 | 文件持久化；消息确认机制 |
| 死锁 (任务依赖) | 中 | 依赖检测；超时机制 |
| 资源泄漏 | 中 | 自动清理；超时关闭 |

---

## 10. 未来扩展

### 10.1 V2 功能

- [ ] 跨项目团队共享
- [ ] Agent 能力学习和优化
- [ ] 自定义 Agent 类型插件
- [ ] 团队模板
- [ ] 历史回放和调试

### 10.2 V3 功能

- [ ] 分布式 Agent 执行
- [ ] 多模型混合 (Opus + Sonnet + Haiku)
- [ ] Agent 市场
- [ ] 可视化工作流编辑器

---

## 附录 A: 与 Claude Code 的兼容性

为了与 Claude Code Agent Teams 保持兼容，Springo 将支持以下环境变量：

```bash
SPRINGO_AGENT_TEAMS=1              # 启用 Agent Teams
SPRINGO_TEAM_NAME=my-team          # 当前团队名称
SPRINGO_AGENT_ID=worker-1          # 当前 Agent ID
SPRINGO_AGENT_TYPE=worker          # Agent 类型
```

文件存储结构与 Claude Code 兼容：

```
~/.springo/teams/    # 相当于 ~/.claude/teams/
~/.springo/tasks/    # 相当于 ~/.claude/tasks/
```

---

## 附录 B: API 完整参考

详见: `/docs/api/teams.md` (待创建)

---

## 附录 C: 消息类型定义

```python
class MessageType(Enum):
    TEXT = "text"                        # 普通文本消息
    TASK_UPDATE = "task_update"          # 任务状态更新
    TASK_CLAIM = "task_claim"            # 任务认领通知
    IDLE_NOTIFICATION = "idle_notification"  # 空闲通知
    SHUTDOWN_REQUEST = "shutdown_request"    # 关闭请求
    SHUTDOWN_RESPONSE = "shutdown_response"  # 关闭响应
    JOIN_REQUEST = "join_request"        # 加入请求
    JOIN_RESPONSE = "join_response"      # 加入响应
    PLAN_PROPOSAL = "plan_proposal"      # 计划提案
    PLAN_RESPONSE = "plan_response"      # 计划响应
    ERROR = "error"                      # 错误消息
```
