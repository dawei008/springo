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


class SSHConfigHost(BaseModel):
    """Parsed SSH config host entry"""
    name: str = Field(..., description="Host alias from SSH config")
    hostname: Optional[str] = Field(default=None, description="HostName value")
    user: Optional[str] = Field(default=None, description="User value")
    port: Optional[int] = Field(default=None, description="Port value")
    identity_file: Optional[str] = Field(default=None, description="IdentityFile path")


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


class NLCommandParseRequest(BaseModel):
    """Natural language command parse request"""
    input: str = Field(..., description="Natural language input to parse")
    context: Optional[str] = Field(default=None, description="Additional context (e.g., current directory, OS)")


# ============ NL Command Parser ============

# Simple heuristics to detect if input is natural language vs actual command
def _is_natural_language(text: str) -> bool:
    """
    Detect if input is natural language (Chinese/English description) 
    vs an actual shell command.
    """
    text = text.strip()
    if not text:
        return False
    
    # Common shell command patterns - if starts with these, it's likely a command
    command_prefixes = [
        'ls', 'cd', 'pwd', 'cat', 'echo', 'grep', 'find', 'mkdir', 'rm', 'cp', 'mv',
        'chmod', 'chown', 'sudo', 'apt', 'yum', 'pip', 'npm', 'git', 'docker', 'kubectl',
        'curl', 'wget', 'ssh', 'scp', 'tar', 'zip', 'unzip', 'ps', 'kill', 'top', 'htop',
        'df', 'du', 'free', 'whoami', 'who', 'date', 'cal', 'man', 'which', 'whereis',
        'head', 'tail', 'sort', 'uniq', 'wc', 'awk', 'sed', 'cut', 'tr', 'diff',
        'touch', 'ln', 'file', 'stat', 'env', 'export', 'source', 'alias', 'history',
        'python', 'python3', 'node', 'java', 'go', 'cargo', 'make', 'cmake',
        './', '/', '~/', '$', '|', '>', '<', '&&', '||',
    ]
    
    # Check if starts with a known command
    first_word = text.split()[0].lower() if text.split() else ''
    for prefix in command_prefixes:
        if first_word == prefix or text.startswith(prefix):
            return False
    
    # Contains Chinese characters -> natural language
    if any('\u4e00' <= char <= '\u9fff' for char in text):
        return True
    
    # Contains common natural language phrases
    nl_indicators = [
        'please', 'show me', 'list', 'what', 'how', 'display', 'get', 'find',
        'check', 'run', 'execute', 'do', 'help', 'tell me', 'i want', 'can you',
        'repeat', 'again', 'same', 'last', 'previous',
    ]
    text_lower = text.lower()
    for indicator in nl_indicators:
        if indicator in text_lower:
            return True
    
    # If very short and looks like a command (no spaces or single word with flags)
    if len(text.split()) <= 2 and not any('\u4e00' <= c <= '\u9fff' for c in text):
        return False
    
    # Default: if it has multiple words and no obvious command structure, treat as NL
    return len(text.split()) > 2


NL_PARSE_SYSTEM_PROMPT = """You are a shell command parser. Your job is to convert natural language descriptions into actual shell commands.

RULES:
1. Output ONLY the shell command, nothing else
2. Do not include explanations, markdown, or quotes
3. If the input is already a valid command, return it as-is
4. For ambiguous requests, choose the most common/safe interpretation
5. Support both Chinese and English inputs

EXAMPLES:
- "list all files" -> ls -la
- "show current directory" -> pwd
- "check disk space" -> df -h
- "show running processes" -> ps aux
- "repeat whoami" -> whoami
- "run whoami again" -> whoami
- "execute ls -la once more" -> ls -la
- "查看当前目录" -> pwd
- "列出所有文件" -> ls -la
- "显示磁盘空间" -> df -h
- "重复执行whoami" -> whoami
- "再执行一次ls" -> ls
- "查看系统内存" -> free -h
- "显示当前用户" -> whoami
- "查看网络连接" -> netstat -tuln
- "显示环境变量" -> env
- "查看进程" -> ps aux
- "检查端口占用" -> ss -tuln

Output the command only, no explanation."""


async def parse_nl_to_command(nl_input: str, context: str = None) -> dict:
    """Use Bedrock to parse natural language to shell command."""
    from ..services.bedrock import get_bedrock_service
    
    bedrock = get_bedrock_service()
    
    user_content = nl_input
    if context:
        user_content = f"Context: {context}\n\nInput: {nl_input}"
    
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 200,
        "temperature": 0,
        "system": NL_PARSE_SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": user_content}
        ]
    }
    
    try:
        # Use a fast model for parsing
        model_id = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
        response = await bedrock.invoke_model(model_id, body)
        
        # Extract command from response
        content = response.get("content", [])
        if content and len(content) > 0:
            command = content[0].get("text", "").strip()
            # Clean up any markdown or quotes
            command = command.strip('`').strip('"').strip("'")
            if command.startswith('```'):
                command = command.split('\n')[1] if '\n' in command else command[3:]
            command = command.strip('`').strip()
            return {
                "success": True,
                "command": command,
                "original_input": nl_input,
                "is_natural_language": True
            }
        
        return {
            "success": False,
            "error": "Failed to parse command",
            "original_input": nl_input
        }
        
    except Exception as e:
        logger.error(f"NL parse error: {e}")
        return {
            "success": False,
            "error": str(e),
            "original_input": nl_input
        }


# ============ Endpoints ============

@router.post("/terminal/parse")
async def terminal_parse_nl(body: NLCommandParseRequest):
    """
    Parse natural language input to shell command.
    
    If input is already a valid command, returns it as-is.
    If input is natural language, uses LLM to parse it.
    
    Returns:
        {
            "success": bool,
            "command": str,  # The parsed shell command
            "original_input": str,
            "is_natural_language": bool,  # Whether input was detected as NL
            "error": str  # Only if success=False
        }
    """
    input_text = body.input.strip()
    
    if not input_text:
        return {
            "success": False,
            "error": "Empty input",
            "original_input": input_text
        }
    
    # Check if it's natural language or already a command
    if _is_natural_language(input_text):
        # Parse with LLM
        result = await parse_nl_to_command(input_text, body.context)
        return result
    else:
        # Already a command, return as-is
        return {
            "success": True,
            "command": input_text,
            "original_input": input_text,
            "is_natural_language": False
        }


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

def _parse_ssh_config() -> list:
    """Parse ~/.ssh/config and return host entries."""
    config_path = os.path.expanduser("~/.ssh/config")
    if not os.path.exists(config_path):
        return []

    hosts = []
    current_host = None

    try:
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # Split on first whitespace
                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue

                key = parts[0].lower()
                value = parts[1].strip()

                if key == 'host':
                    # Skip wildcard entries
                    if '*' in value or '?' in value:
                        current_host = None
                        continue
                    current_host = {
                        'name': value,
                        'hostname': None,
                        'user': None,
                        'port': None,
                        'identity_file': None,
                    }
                    hosts.append(current_host)
                elif current_host is not None:
                    if key == 'hostname':
                        current_host['hostname'] = value
                    elif key == 'user':
                        current_host['user'] = value
                    elif key == 'port':
                        try:
                            current_host['port'] = int(value)
                        except ValueError:
                            pass
                    elif key == 'identityfile':
                        current_host['identity_file'] = value
    except Exception as e:
        logger.warning(f"Failed to parse SSH config: {e}")

    return hosts


@router.get("/terminal/ssh/config")
async def ssh_get_config():
    """Read and parse ~/.ssh/config, returning available host entries."""
    hosts = _parse_ssh_config()
    return {
        "hosts": [
            SSHConfigHost(
                name=h['name'],
                hostname=h.get('hostname'),
                user=h.get('user'),
                port=h.get('port'),
                identity_file=h.get('identity_file'),
            ).model_dump()
            for h in hosts
        ]
    }


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
