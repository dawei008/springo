"""
Terminal Router for FastAPI
终端命令执行端点 - 支持 SSE 实时流式输出
"""
import asyncio
import os
import signal
import logging
from typing import Optional, Dict, Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import settings
from ..utils.streaming import create_sse_response, format_sse_event

logger = logging.getLogger(__name__)

router = APIRouter()

# Track running processes for kill support
_running_processes: Dict[int, asyncio.subprocess.Process] = {}

# Dangerous command patterns (reuse from mcp_tools security)
BLOCKED_COMMAND_PATTERNS_SIMPLE = [
    "rm -rf /", "rm -rf /*", "rm -fr /", "rm -fr /*",
    "mkfs", "dd if=", ":(){:|:&};:",
    "chmod -R 777 /", "> /dev/sda", "> /dev/nvme",
    "shutdown", "reboot", "init 0", "init 6",
    "systemctl halt", "systemctl poweroff", "systemctl reboot",
]


def _is_command_safe(command: str) -> bool:
    """Check if command is safe to execute."""
    if not command or not command.strip():
        return False
    cmd_lower = command.lower().strip()
    for blocked in BLOCKED_COMMAND_PATTERNS_SIMPLE:
        if blocked in cmd_lower:
            return False
    return True


# ============ Request Models ============

class TerminalExecuteRequest(BaseModel):
    """Terminal command execution request"""
    command: str = Field(..., description="Command to execute")
    working_dir: Optional[str] = Field(default=None, description="Working directory")
    timeout: int = Field(default=300, ge=1, le=3600, description="Timeout in seconds")
    run_in_background: bool = Field(default=False, description="Run in background")


# ============ Endpoints ============

@router.post("/terminal/execute")
async def terminal_execute(
    body: TerminalExecuteRequest,
    request: Request,
):
    """
    Execute a terminal command with SSE streaming output.

    Returns real-time stdout/stderr as SSE events:
    - event: output  -> {type: "stdout"|"stderr", data: "..."}
    - event: exit    -> {exit_code: N, pid: N}
    - event: error   -> {message: "..."}
    """
    command = body.command
    working_dir = body.working_dir
    timeout = body.timeout

    # Security check
    if not _is_command_safe(command):
        raise HTTPException(status_code=400, detail="Command blocked for safety reasons")

    # Resolve working directory
    if working_dir:
        working_dir = os.path.abspath(os.path.expanduser(working_dir))
    else:
        # Use session working dir or home
        from ..services.session_state import get_working_dir
        working_dir = get_working_dir() or os.path.expanduser("~")

    if not os.path.isdir(working_dir):
        raise HTTPException(status_code=400, detail=f"Working directory not found: {working_dir}")

    async def stream_command() -> AsyncGenerator[str, None]:
        process = None
        try:
            # Start subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
                limit=1024 * 1024,  # 1MB buffer
            )

            pid = process.pid
            _running_processes[pid] = process

            # Send start event
            yield format_sse_event('start', {
                'type': 'start',
                'pid': pid,
                'command': command,
                'working_dir': working_dir,
            })

            async def read_stream(stream, stream_type):
                """Read from a stream and yield SSE events."""
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    text = line.decode('utf-8', errors='replace')
                    yield format_sse_event('output', {
                        'type': stream_type,
                        'data': text,
                    })

            # Read stdout and stderr concurrently
            stdout_lines = []
            stderr_lines = []

            async def collect_stdout():
                async for event in read_stream(process.stdout, 'stdout'):
                    stdout_lines.append(event)

            async def collect_stderr():
                async for event in read_stream(process.stderr, 'stderr'):
                    stderr_lines.append(event)

            # Run both collectors with timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(collect_stdout(), collect_stderr()),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                # Kill the process on timeout
                try:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass
                yield format_sse_event('error', {
                    'type': 'error',
                    'message': f'Command timed out after {timeout}s',
                })

            # Yield collected output in order (stdout first, then stderr)
            for event in stdout_lines:
                yield event
            for event in stderr_lines:
                yield event

            # Wait for process to finish
            exit_code = process.returncode
            if exit_code is None:
                try:
                    exit_code = await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    exit_code = -1

            # Send exit event
            yield format_sse_event('exit', {
                'type': 'exit',
                'exit_code': exit_code,
                'pid': pid,
            })

        except Exception as e:
            logger.error(f"Terminal execution error: {e}")
            yield format_sse_event('error', {
                'type': 'error',
                'message': str(e),
            })
        finally:
            # Cleanup
            if process and process.pid in _running_processes:
                del _running_processes[process.pid]

        # Done
        yield "data: [DONE]\n\n"

    return create_sse_response(stream_command(), request)


@router.post("/terminal/kill/{pid}")
async def terminal_kill(pid: int):
    """
    Kill a running terminal process by PID.
    """
    process = _running_processes.get(pid)
    if not process:
        raise HTTPException(status_code=404, detail=f"Process {pid} not found or already exited")

    try:
        process.send_signal(signal.SIGTERM)
        # Give it a moment to terminate gracefully
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

        return {
            "success": True,
            "pid": pid,
            "message": f"Process {pid} terminated"
        }
    except ProcessLookupError:
        # Already exited
        if pid in _running_processes:
            del _running_processes[pid]
        return {
            "success": True,
            "pid": pid,
            "message": f"Process {pid} already exited"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
