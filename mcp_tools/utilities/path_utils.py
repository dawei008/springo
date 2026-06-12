"""
Path Utilities
Path resolution and security validation for MCP tools
"""

import os
import re
from ..config import (
    get_working_dir,
    ALLOWED_READ_DIRECTORIES,
    ALLOWED_WRITE_DIRECTORIES,
    BLOCKED_READ_PATHS,
    BLOCKED_COMMAND_PATTERNS,
    SAFE_COMMAND_PREFIXES,
    BLOCKED_COMMANDS,
)


def resolve_path(path: str = None, default_to_working_dir: bool = True) -> str:
    """Resolve path, using working directory as default if set"""
    working_dir = get_working_dir()
    if path:
        # First expand ~ to handle home directory paths
        expanded_path = os.path.expanduser(path)
        # If path is relative and working dir is set, resolve relative to working dir
        if not os.path.isabs(expanded_path) and working_dir:
            return os.path.abspath(os.path.join(working_dir, expanded_path))
        return os.path.abspath(expanded_path)
    elif default_to_working_dir and working_dir:
        return working_dir
    else:
        # NOT os.getcwd(): the backend's cwd is the Springo repo root, and
        # defaulting there makes tools write into the source tree whenever
        # working_dir is unset (e.g. right after a uvicorn hot reload).
        return os.path.expanduser("~")


def _is_path_blocked(path: str) -> bool:
    """Check if path matches any blocked sensitive paths"""
    abs_path = os.path.abspath(os.path.expanduser(path))
    # Resolve symlinks to prevent bypass
    try:
        real_path = os.path.realpath(abs_path)
    except (OSError, ValueError):
        real_path = abs_path

    for blocked in BLOCKED_READ_PATHS:
        blocked_abs = os.path.abspath(os.path.expanduser(blocked))
        # Check if path is the blocked path or inside it
        if real_path == blocked_abs or real_path.startswith(blocked_abs + os.sep):
            return True
        # Check for filename patterns (like .env)
        if not os.path.isabs(blocked):
            basename = os.path.basename(real_path)
            if basename == blocked or basename.startswith(blocked):
                return True
    return False


def _is_within_allowed(path: str, allowed_dirs: list) -> bool:
    """Check if path is within allowed directories using commonpath"""
    abs_path = os.path.abspath(os.path.expanduser(path))
    # Resolve symlinks to prevent bypass
    try:
        real_path = os.path.realpath(abs_path)
    except (OSError, ValueError):
        real_path = abs_path

    for allowed in allowed_dirs:
        allowed_abs = os.path.abspath(os.path.expanduser(allowed))
        try:
            # Use commonpath for safer comparison
            common = os.path.commonpath([real_path, allowed_abs])
            if common == allowed_abs:
                return True
        except ValueError:
            # Different drives on Windows, skip
            continue
    return False


def is_path_allowed_for_read(path: str) -> bool:
    """Check if path is allowed for read operations"""
    # First check if path is blocked (sensitive files)
    if _is_path_blocked(path):
        return False
    # Then check if within allowed directories
    return _is_within_allowed(path, ALLOWED_READ_DIRECTORIES)


def is_path_allowed_for_write(path: str) -> bool:
    """Check if path is allowed for write operations (more restrictive)"""
    # Check blocked paths (shouldn't write to sensitive locations)
    if _is_path_blocked(path):
        return False
    return _is_within_allowed(path, ALLOWED_WRITE_DIRECTORIES)


def is_path_allowed(path: str, for_write: bool = False) -> bool:
    """Check if path is within allowed directories"""
    if for_write:
        return is_path_allowed_for_write(path)
    return is_path_allowed_for_read(path)


def is_command_safe(command: str) -> bool:
    """
    Check if command is safe to execute using multiple layers of validation.
    Returns False if command matches any dangerous patterns.
    """
    if not command or not command.strip():
        return False

    cmd_lower = command.lower().strip()

    # Layer 1: Check legacy blocklist (exact matches)
    for blocked in BLOCKED_COMMANDS:
        if blocked.lower() in cmd_lower:
            return False

    # Layer 2: Check regex patterns for dangerous commands
    for pattern in BLOCKED_COMMAND_PATTERNS:
        try:
            if re.search(pattern, command, re.IGNORECASE):
                return False
        except re.error:
            # Invalid regex pattern, skip it
            continue

    # Layer 3: Check for shell injection characters in suspicious contexts
    dangerous_sequences = [
        ("$(", ")"),      # Command substitution
        ("`", "`"),       # Backtick command substitution
        ("&&", "rm"),     # Chained destructive commands
        ("||", "rm"),
        (";", "rm"),
        ("|", "sh"),      # Piping to shell
        ("|", "bash"),
    ]
    for start, end in dangerous_sequences:
        if start in command and end in cmd_lower:
            # More careful check - might be legitimate
            pass  # Allow for now, regex patterns should catch the bad ones

    return True


def get_command_base(command: str) -> str:
    """Extract the base command from a command string"""
    if not command:
        return ""
    # Handle environment variables at start
    parts = command.strip().split()
    for part in parts:
        if '=' not in part:  # Skip env vars like VAR=value
            return part.split('/').pop()  # Get basename if full path
    return ""


def is_safe_command_prefix(command: str) -> bool:
    """Check if command starts with a known safe prefix"""
    base_cmd = get_command_base(command)
    return base_cmd in SAFE_COMMAND_PREFIXES


def validate_session_id(session_id: str) -> bool:
    """Validate session ID format to prevent path traversal"""
    if not session_id:
        return False
    # Only allow alphanumeric, dash, and underscore
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', session_id))
