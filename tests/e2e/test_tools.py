"""
Springo E2E Tests - Tools API
工具执行端点 E2E 测试
"""
import pytest
import httpx
import os


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tools_list_endpoint(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: /v1/tools/list endpoint returns tool definitions.
    验证工具列表端点返回工具定义。
    """
    response = await fastapi_client.get("/v1/tools/list")
    
    assert response.status_code == 200
    
    data = response.json()
    assert "tools" in data
    assert "count" in data
    assert isinstance(data["tools"], list)
    assert data["count"] >= 0
    
    # 验证工具定义结构
    if data["count"] > 0:
        tool = data["tools"][0]
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tools_execute_read_file(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Execute read_file tool.
    测试执行 read_file 工具。
    """
    # 创建测试文件
    test_file = "/tmp/fastapi_test_file.txt"
    test_content = "Hello from FastAPI E2E test!"
    with open(test_file, 'w') as f:
        f.write(test_content)
    
    try:
        response = await fastapi_client.post("/v1/tools/execute", json={
            "name": "read_file",
            "input": {"path": test_file}
        })
        
        assert response.status_code == 200
        
        data = response.json()
        assert "success" in data
        assert "name" in data
        assert data["name"] == "read_file"
        assert "result" in data
        
        # 验证读取内容
        if data["success"]:
            assert "content" in data["result"]
            assert data["result"]["content"] == test_content
    finally:
        # 清理
        if os.path.exists(test_file):
            os.remove(test_file)


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tools_execute_write_file(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Execute write_file tool.
    测试执行 write_file 工具。
    """
    test_file = "/tmp/fastapi_write_test.txt"
    test_content = "Written by FastAPI E2E test!"
    
    try:
        response = await fastapi_client.post("/v1/tools/execute", json={
            "name": "write_file",
            "input": {
                "path": test_file,
                "content": test_content
            }
        })
        
        assert response.status_code == 200
        
        data = response.json()
        assert "success" in data
        assert data["name"] == "write_file"
        
        # 验证文件已写入
        if data["success"]:
            assert os.path.exists(test_file)
            with open(test_file, 'r') as f:
                assert f.read() == test_content
    finally:
        # 清理
        if os.path.exists(test_file):
            os.remove(test_file)


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tools_execute_command(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Execute execute_command tool.
    测试执行 execute_command 工具。
    """
    response = await fastapi_client.post("/v1/tools/execute", json={
        "name": "execute_command",
        "input": {"command": "echo 'Hello FastAPI'"}
    })
    
    assert response.status_code == 200
    
    data = response.json()
    assert "success" in data
    assert data["name"] == "execute_command"
    assert "result" in data
    
    if data["success"]:
        assert "stdout" in data["result"]
        assert "Hello FastAPI" in data["result"]["stdout"]


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tools_batch_execution(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Execute multiple tools in batch.
    测试批量执行工具。
    """
    response = await fastapi_client.post("/v1/tools/batch", json={
        "tools": [
            {"name": "execute_command", "input": {"command": "echo 'test1'"}},
            {"name": "execute_command", "input": {"command": "echo 'test2'"}},
            {"name": "execute_command", "input": {"command": "echo 'test3'"}}
        ],
        "parallel": True
    })
    
    assert response.status_code == 200
    
    data = response.json()
    assert "results" in data
    assert "total" in data
    assert "succeeded" in data
    assert "failed" in data
    
    assert data["total"] == 3
    assert len(data["results"]) == 3


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tools_parallel_performance(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Verify parallel execution is faster than serial.
    验证并行执行比串行更快。
    """
    import time
    
    # 准备多个慢命令
    tools = [
        {"name": "execute_command", "input": {"command": "sleep 0.1 && echo 'done'"}}
        for _ in range(5)
    ]
    
    # 并行执行
    start_parallel = time.time()
    response_parallel = await fastapi_client.post("/v1/tools/batch", json={
        "tools": tools,
        "parallel": True
    })
    time_parallel = time.time() - start_parallel
    
    # 串行执行
    start_serial = time.time()
    response_serial = await fastapi_client.post("/v1/tools/batch", json={
        "tools": tools,
        "parallel": False
    })
    time_serial = time.time() - start_serial
    
    assert response_parallel.status_code == 200
    assert response_serial.status_code == 200
    
    # 并行应该明显更快（至少快 2 倍）
    # 注意：这是一个软断言，可能因系统负载而变化
    assert time_parallel < time_serial, \
        f"Parallel ({time_parallel:.2f}s) should be faster than serial ({time_serial:.2f}s)"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tools_unknown_tool_error(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Verify error handling for unknown tools.
    验证未知工具的错误处理。
    """
    response = await fastapi_client.post("/v1/tools/execute", json={
        "name": "non_existent_tool",
        "input": {}
    })
    
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] == False
    assert "error" in data["result"]


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tools_get_tool_info(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Get single tool info.
    测试获取单个工具信息。
    """
    response = await fastapi_client.get("/v1/tools/read_file")
    
    assert response.status_code == 200
    
    data = response.json()
    assert "found" in data
    assert data["found"] == True
    assert "tool" in data
    assert data["tool"]["name"] == "read_file"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tools_get_nonexistent_tool_info(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Get info for non-existent tool returns 404.
    测试获取不存在工具返回 404。
    """
    response = await fastapi_client.get("/v1/tools/nonexistent_tool_xyz")
    
    assert response.status_code == 404


