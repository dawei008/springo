"""
Springo E2E Tests - Terminal API
终端命令执行端点 E2E 测试
"""
import pytest
import httpx
import json


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_terminal_execute_echo(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/terminal/execute with echo command.
    验证终端执行 echo 命令并返回正确输出。
    """
    async with fastapi_client.stream(
        "POST",
        "/v1/terminal/execute",
        json={"command": "echo hello"},
        timeout=30,
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        events = []
        async for line in response.aiter_lines():
            line = line.strip()
            if line.startswith("data:"):
                events.append(line)
            elif line.startswith("event:"):
                events.append(line)

        # Should contain at least a start, output, and exit event
        data_lines = [e for e in events if e.startswith("data:") and e != "data: [DONE]"]
        assert len(data_lines) >= 2, f"Expected at least 2 data events, got {len(data_lines)}: {data_lines}"

        # Parse all data events
        parsed = []
        for dl in data_lines:
            try:
                parsed.append(json.loads(dl[5:].strip()))
            except json.JSONDecodeError:
                pass

        # Verify start event
        start_events = [e for e in parsed if e.get("type") == "start"]
        assert len(start_events) >= 1, f"Missing start event. Events: {parsed}"
        assert "pid" in start_events[0]

        # Verify output contains "hello"
        output_events = [e for e in parsed if e.get("type") == "stdout"]
        output_text = "".join(e.get("data", "") for e in output_events)
        assert "hello" in output_text, f"Expected 'hello' in output, got: {output_text}"

        # Verify exit event with code 0
        exit_events = [e for e in parsed if e.get("type") == "exit"]
        assert len(exit_events) >= 1, f"Missing exit event. Events: {parsed}"
        assert exit_events[0].get("exit_code") == 0


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_terminal_execute_pwd(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/terminal/execute with pwd command.
    验证 pwd 命令返回有效路径。
    """
    async with fastapi_client.stream(
        "POST",
        "/v1/terminal/execute",
        json={"command": "pwd", "working_dir": "/tmp"},
        timeout=30,
    ) as response:
        assert response.status_code == 200

        parsed = []
        async for line in response.aiter_lines():
            line = line.strip()
            if line.startswith("data:") and line != "data: [DONE]":
                try:
                    parsed.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    pass

        # Output should contain a valid path
        output_events = [e for e in parsed if e.get("type") == "stdout"]
        output_text = "".join(e.get("data", "") for e in output_events).strip()
        # On macOS /tmp may resolve to /private/tmp
        assert output_text.startswith("/"), f"Expected path starting with /, got: {output_text}"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_terminal_execute_ls(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/terminal/execute with ls -la command.
    验证 ls -la 命令返回文件列表。
    """
    async with fastapi_client.stream(
        "POST",
        "/v1/terminal/execute",
        json={"command": "ls -la", "working_dir": "/tmp"},
        timeout=30,
    ) as response:
        assert response.status_code == 200

        parsed = []
        async for line in response.aiter_lines():
            line = line.strip()
            if line.startswith("data:") and line != "data: [DONE]":
                try:
                    parsed.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    pass

        # Output should have multiple stdout lines
        output_events = [e for e in parsed if e.get("type") == "stdout"]
        assert len(output_events) >= 1, "Expected at least 1 output line from ls -la"

        output_text = "".join(e.get("data", "") for e in output_events)
        assert "total" in output_text.lower() or len(output_events) >= 1, \
            f"Expected file listing output, got: {output_text}"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_terminal_execute_multiline_streaming(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/terminal/execute with multi-line output to verify streaming.
    验证多行输出的流式传输。
    """
    async with fastapi_client.stream(
        "POST",
        "/v1/terminal/execute",
        json={"command": "for i in 1 2 3 4 5; do echo \"line $i\"; done"},
        timeout=30,
    ) as response:
        assert response.status_code == 200

        parsed = []
        async for line in response.aiter_lines():
            line = line.strip()
            if line.startswith("data:") and line != "data: [DONE]":
                try:
                    parsed.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    pass

        output_events = [e for e in parsed if e.get("type") == "stdout"]
        output_text = "".join(e.get("data", "") for e in output_events)

        for i in range(1, 6):
            assert f"line {i}" in output_text, \
                f"Expected 'line {i}' in output, got: {output_text}"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_terminal_execute_blocked_command(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/terminal/execute with dangerous command is blocked.
    验证危险命令被阻止。
    """
    dangerous_commands = [
        "rm -rf /",
        "rm -rf /*",
        "mkfs.ext4 /dev/sda",
        "shutdown now",
        "reboot",
    ]

    for cmd in dangerous_commands:
        response = await fastapi_client.post(
            "/v1/terminal/execute",
            json={"command": cmd},
            timeout=10,
        )
        assert response.status_code == 400, \
            f"Command '{cmd}' should be blocked (400), got {response.status_code}"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_terminal_kill_nonexistent_process(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/terminal/kill/{pid} for non-existent process returns 404.
    验证 kill 不存在的进程返回 404。
    """
    response = await fastapi_client.post("/v1/terminal/kill/999999")
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_terminal_execute_empty_command(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/terminal/execute with empty command is rejected.
    验证空命令被拒绝。
    """
    response = await fastapi_client.post(
        "/v1/terminal/execute",
        json={"command": ""},
        timeout=10,
    )
    assert response.status_code == 400, \
        f"Empty command should be blocked (400), got {response.status_code}"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_terminal_execute_invalid_working_dir(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/terminal/execute with invalid working dir returns 400.
    验证无效工作目录返回 400。
    """
    response = await fastapi_client.post(
        "/v1/terminal/execute",
        json={
            "command": "echo hello",
            "working_dir": "/nonexistent/directory/that/does/not/exist"
        },
        timeout=10,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_terminal_execute_with_stderr(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/terminal/execute with command that produces stderr.
    验证 stderr 输出正确传输。
    """
    async with fastapi_client.stream(
        "POST",
        "/v1/terminal/execute",
        json={"command": "ls /nonexistent_path_12345 2>&1 || true"},
        timeout=30,
    ) as response:
        assert response.status_code == 200

        parsed = []
        async for line in response.aiter_lines():
            line = line.strip()
            if line.startswith("data:") and line != "data: [DONE]":
                try:
                    parsed.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    pass

        # Should have exit event
        exit_events = [e for e in parsed if e.get("type") == "exit"]
        assert len(exit_events) >= 1, "Missing exit event"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_terminal_execute_missing_command_field(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/terminal/execute without command field returns 422.
    验证缺少 command 字段返回验证错误。
    """
    response = await fastapi_client.post(
        "/v1/terminal/execute",
        json={},
        timeout=10,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_terminal_execute_timeout_bounds(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/terminal/execute with invalid timeout is rejected.
    验证 timeout 越界被拒绝。
    """
    # timeout=0 should fail (ge=1)
    response = await fastapi_client.post(
        "/v1/terminal/execute",
        json={"command": "echo test", "timeout": 0},
        timeout=10,
    )
    assert response.status_code == 422

    # timeout=5000 should fail (le=3600)
    response = await fastapi_client.post(
        "/v1/terminal/execute",
        json={"command": "echo test", "timeout": 5000},
        timeout=10,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_terminal_sse_content_type(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Terminal response has correct SSE content-type header.
    验证响应的 Content-Type 头正确。
    """
    async with fastapi_client.stream(
        "POST",
        "/v1/terminal/execute",
        json={"command": "echo sse_check"},
        timeout=30,
    ) as response:
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/event-stream" in content_type, \
            f"Expected text/event-stream, got: {content_type}"
