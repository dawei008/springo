# AgentCore Memory 测试场景

基于开发过程中踩过的坑，总结以下测试场景。

## 1. 策略 Namespace 发现测试

### 场景描述
验证 Refresh 按钮能获取到实际的策略 namespace（带随机后缀）。

### 测试步骤
1. 在 Settings 中启用 Memory
2. 点击 Refresh 按钮
3. 检查返回的 namespace

### 预期结果
```
✅ 正确: /strategies/ConversationFacts-Uqvc82478h/actors/springo/
❌ 错误: /strategies/ConversationFacts/actors/springo/  (缺少随机后缀)
```

### 验证命令
```bash
curl -s -X POST http://localhost:8080/v1/config/memory/strategies/refresh | jq '.strategies[].namespace'
```

---

## 2. EPISODIC Reflection 配置测试

### 场景描述
验证 EPISODIC 策略的 reflectionConfiguration 正确指向其他 LTM 策略。

### 测试步骤
1. 点击 Refresh 按钮
2. 检查 EPISODIC 策略的配置

### 预期结果
```json
{
  "type": "EPISODIC_MEMORY",
  "has_reflection": true,
  "reflection_namespaces": [
    "/strategies/ConversationFacts-xxx/actors/springo/",
    "/strategies/ConversationSummary-xxx/actors/springo/",
    "/strategies/UserPreferences-xxx/actors/springo/"
  ]
}
```

### 验证命令
```bash
curl -s -X POST http://localhost:8080/v1/config/memory/strategies/refresh | jq '.strategies[] | select(.type=="EPISODIC_MEMORY")'
```

---

## 3. EPISODIC 更新方式测试

### 场景描述
验证更新 EPISODIC reflection 必须通过 删除+重建 方式，而非 modifyMemoryStrategies。

### 背景
AWS API 的 `modifyMemoryStrategies` 对 EPISODIC reflection 有验证限制：
> "Reflection namespace must be the same as or a prefix of the episodic namespace"

### 测试步骤
1. 尝试使用 modifyMemoryStrategies 更新 EPISODIC reflection
2. 验证报错
3. 使用 delete + add 方式更新
4. 验证成功

### 预期结果
```python
# ❌ 失败 - modifyMemoryStrategies
client.update_memory(
    memoryId=memory_id,
    memoryStrategies={
        'modifyMemoryStrategies': [{
            'memoryStrategyId': episodic_id,
            'configuration': {'reflection': {...}}
        }]
    }
)
# Error: ValidationException

# ✅ 成功 - delete + add
client.update_memory(memoryStrategies={'deleteMemoryStrategies': [...]})
client.update_memory(memoryStrategies={'addMemoryStrategies': [...]})
```

---

## 4. 策略类型唯一性测试

### 场景描述
验证每种策略类型只能有一个实例。

### 测试步骤
1. 在已有 EPISODIC 策略的情况下，尝试添加第二个 EPISODIC

### 预期结果
```
❌ Error: Only one strategy of each type is allowed.
   Found multiple strategies of type: episodicMemoryStrategy
```

### 验证命令
```python
# 应该报错
client.update_memory(
    memoryId=memory_id,
    memoryStrategies={
        'addMemoryStrategies': [{
            'episodicMemoryStrategy': {'name': 'SecondEpisodic'}
        }]
    }
)
```

---

## 5. 服务器代码重载测试

### 场景描述
验证修改后端代码后，服务器是否正确加载新代码。

### 测试步骤
1. 修改 `full_proxy_server.py`
2. 添加新的日志语句（如 `logger.info("TEST_MARKER")`）
3. 调用 API
4. 检查服务器日志

### 预期结果
- **Debug 模式**: 自动重载，日志中出现 "TEST_MARKER"
- **非 Debug 模式**: 需要手动重启服务器

### 注意事项
```bash
# 检查服务器是否在 debug 模式
ps aux | grep full_proxy_server

# 如果没有 --debug 参数，需要手动重启
kill <pid> && python full_proxy_server.py
```

---

## 6. Memory Sync 异步测试

### 场景描述
验证消息同步是异步进行的，不会阻塞聊天。

### 测试步骤
1. 发送聊天消息
2. 立即检查 Memory 同步状态
3. 等待几秒后再检查

### 预期结果
```bash
# 消息发送后立即返回，不会等待同步完成
# 同步在后台进行

# 检查同步状态
curl -s http://localhost:8080/v1/memory/status | jq '.pending'
```

---

## 7. 配置持久化测试

### 场景描述
验证 Memory 配置正确保存到配置文件。

### 测试步骤
1. 在 Settings 中配置 Memory ID 和 Region
2. 点击 Refresh
3. 检查配置文件

### 预期结果
```bash
cat ~/.springo/config.json | jq '.memory'
# 应该包含:
# - memory_id
# - memory_region
# - ltm.strategies (带实际 namespace)
```

---

## 8. 策略自动创建测试

### 场景描述
验证 Refresh 时自动创建缺失的 LTM 策略。

### 测试步骤
1. 删除所有现有策略（或使用新的 Memory）
2. 点击 Refresh
3. 检查是否自动创建了 3 个 LTM 策略 + 1 个 EPISODIC

### 预期结果
```
自动创建:
- ConversationFacts (SEMANTIC)
- UserPreferences (USER_PREFERENCE)
- ConversationSummary (SUMMARIZATION)
- ConversationEpisodes (EPISODIC) with reflection
```

---

## 9. API 响应格式测试

### 场景描述
验证 get_memory API 响应的正确路径。

### 背景
之前的 bug：使用 `response.get('memoryStrategies')` 获取不到数据。

### 正确路径
```python
response = client.get_memory(memoryId=memory_id)
strategies = response['memory']['strategies']  # ✅ 正确
# NOT: response['memoryStrategies']  # ❌ 错误
```

### 验证命令
```python
import boto3
client = boto3.client('bedrock-agentcore-control', region_name='us-west-2')
response = client.get_memory(memoryId='your-memory-id')
print(response.keys())  # 应该包含 'memory'
print(response['memory'].keys())  # 应该包含 'strategies'
```

---

## 10. Starter Toolkit 兼容性测试

### 场景描述
验证 Starter Toolkit 的 MemoryManager 方法是否可用。

### 已知问题
`modify_strategy()` 方法有 bug：参数名 `strategyId` 应该是 `memoryStrategyId`

### 测试步骤
```python
from bedrock_agentcore_starter_toolkit.operations.memory import MemoryManager

manager = MemoryManager()
# 测试各方法
manager.get_memory(memory_id)  # ✅ 可用
manager.add_strategy(...)  # ✅ 可用
manager.modify_strategy(...)  # ❌ 有 bug
manager.delete_strategy(...)  # 待验证
```

---

## 快速测试脚本

```python
#!/usr/bin/env python3
"""Quick test script for Memory functionality."""

import requests
import json

BASE_URL = "http://localhost:8080"

def test_refresh():
    """Test strategy refresh."""
    resp = requests.post(f"{BASE_URL}/v1/config/memory/strategies/refresh")
    data = resp.json()

    assert data['success'], f"Refresh failed: {data.get('error')}"
    assert len(data['strategies']) >= 4, "Should have at least 4 strategies"

    # Check EPISODIC has reflection
    episodic = next((s for s in data['strategies'] if s['type'] == 'EPISODIC_MEMORY'), None)
    assert episodic, "EPISODIC strategy not found"
    assert episodic.get('has_reflection'), "EPISODIC should have reflection"
    assert len(episodic.get('reflection_namespaces', [])) >= 3, "Should reflect on 3 strategies"

    print("✅ All tests passed!")
    return data

if __name__ == "__main__":
    test_refresh()
```

---

## 参考

- [AgentCore Memory API 文档](https://docs.aws.amazon.com/bedrock-agentcore/)
- [Starter Toolkit 源码](https://github.com/aws/bedrock-agentcore-starter-toolkit)
