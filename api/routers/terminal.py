"""
Terminal Router for FastAPI
终端命令执行端点 - 支持 SSE 实时流式输出
"""
import asyncio
import asyncssh
import os
import signal
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import settings
from ..utils.streaming import create_sse_response, format_sse_event

logger = logging.getLogger(__name__)

router = APIRouter()

# Track running processes for kill support
_running_processes: Dict[int, asyncio.subprocess.Process] = {}

# Track SSH connections
_ssh_connections: Dict[str, asyncssh.SSHClientConnection] = {}
_ssh_connection_info: Dict[str, Dict[str, Any]] = {}

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


class SSHConnectRequest(BaseModel):
    """SSH connection request"""
    host: str = Field(..., description="Remote host")
    port: int = Field(default=22, ge=1, le=65535, description="SSH port")
    username: str = Field(..., description="SSH username")
    password: Optional[str] = Field(default=None, description="SSH password")
    key_path: Optional[str] = Field(default=None, description="Path to SSH private key")
    key_passphrase: Optional[str] = Field(default=None, description="Key passphrase")
    name: Optional[str] = Field(default=None, description="Connection name/label")


class SSHExecuteRequest(BaseModel):
    """SSH command execution request"""
    connection_id: str = Field(..., description="SSH connection ID")
    command: str = Field(..., description="Command to execute")
    timeout: int = Field(default=300, ge=1, le=3600, description="Timeout in seconds")


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


# ============ SSH Endpoints ============

@router.post("/terminal/ssh/connect")
async def ssh_connect(body: SSHConnectRequest):
    """Establish an SSH connection to a remote host."""
    connection_id = f"ssh_{uuid.uuid4().hex[:8]}"

    try:
        connect_kwargs = {
            'host': body.host,
            'port': body.port,
            'username': body.username,
            'known_hosts': None,  # Skip host key verification for now
        }

        if body.key_path:
            key_path = os.path.expanduser(body.key_path)
            if not os.path.exists(key_path):
                raise HTTPException(status_code=400, detail=f"Key file not found: {body.key_path}")
            connect_kwargs['client_keys'] = [key_path]
            if body.key_passphrase:
                connect_kwargs['passphrase'] = body.key_passphrase
        elif body.password:
            connect_kwargs['password'] = body.password
        else:
            # Try default key paths
            default_keys = ['~/.ssh/id_rsa', '~/.ssh/id_ed25519']
            client_keys = [os.path.expanduser(k) for k in default_keys if os.path.exists(os.path.expanduser(k))]
            if client_keys:
                connect_kwargs['client_keys'] = client_keys

        conn = await asyncssh.connect(**connect_kwargs)

        _ssh_connections[connection_id] = conn
        _ssh_connection_info[connection_id] = {
            'host': body.host,
            'port': body.port,
            'username': body.username,
            'name': body.name or f"{body.username}@{body.host}",
            'connected_at': datetime.now().isoformat(),
        }

        return {
            "success": True,
            "connection_id": connection_id,
            "name": _ssh_connection_info[connection_id]['name'],
            "message": f"Connected to {body.username}@{body.host}:{body.port}"
        }
    except asyncssh.DisconnectError as e:
        raise HTTPException(status_code=400, detail=f"SSH connection failed: {e}")
    except asyncssh.PermissionDenied:
        raise HTTPException(status_code=401, detail="SSH authentication failed: permission denied")
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"Connection error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SSH error: {str(e)}")


@router.post("/terminal/ssh/execute")
async def ssh_execute(body: SSHExecuteRequest, request: Request):
    """Execute a command over SSH with SSE streaming output."""
    conn = _ssh_connections.get(body.connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"SSH connection {body.connection_id} not found")

    if not _is_command_safe(body.command):
        raise HTTPException(status_code=400, detail="Command blocked for safety reasons")

    info = _ssh_connection_info.get(body.connection_id, {})

    async def stream_ssh_command() -> AsyncGenerator[str, None]:
        try:
            yield format_sse_event('start', {
                'type': 'start',
                'connection_id': body.connection_id,
                'host': info.get('host', ''),
                'command': body.command,
            })

            result = await asyncio.wait_for(
                conn.run(body.command),
                timeout=body.timeout
            )

            if result.stdout:
                for line in result.stdout.splitlines(True):
                    yield format_sse_event('output', {
                        'type': 'stdout',
                        'data': line,
                    })

            if result.stderr:
                for line in result.stderr.splitlines(True):
                    yield format_sse_event('output', {
                        'type': 'stderr',
                        'data': line,
                    })

            exit_code = result.exit_status or 0
            yield format_sse_event('exit', {
                'type': 'exit',
                'exit_code': exit_code,
            })

        except asyncio.TimeoutError:
            yield format_sse_event('error', {
                'type': 'error',
                'message': f'SSH command timed out after {body.timeout}s',
            })
        except asyncssh.ChannelOpenError as e:
            yield format_sse_event('error', {
                'type': 'error',
                'message': f'SSH channel error: {e}',
            })
        except Exception as e:
            logger.error(f"SSH execution error: {e}")
            yield format_sse_event('error', {
                'type': 'error',
                'message': str(e),
            })

        yield "data: [DONE]\n\n"

    return create_sse_response(stream_ssh_command(), request)


@router.get("/terminal/ssh/connections")
async def ssh_list_connections():
    """List active SSH connections."""
    connections = []
    for conn_id, info in _ssh_connection_info.items():
        conn = _ssh_connections.get(conn_id)
        connections.append({
            "connection_id": conn_id,
            "name": info.get('name', ''),
            "host": info.get('host', ''),
            "port": info.get('port', 22),
            "username": info.get('username', ''),
            "connected": conn is not None,
        })
    return {"connections": connections}


@router.post("/terminal/ssh/disconnect/{connection_id}")
async def ssh_disconnect(connection_id: str):
    """Disconnect an SSH connection."""
    conn = _ssh_connections.pop(connection_id, None)
    _ssh_connection_info.pop(connection_id, None)

    if not conn:
        raise HTTPException(status_code=404, detail=f"SSH connection {connection_id} not found")

    try:
        conn.close()
    except:
        pass

    return {"success": True, "message": f"Disconnected {connection_id}"}
