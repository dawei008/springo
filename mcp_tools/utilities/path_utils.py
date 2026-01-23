"""
Path Utilities
Path resolution and security validation for MCP tools
"""

import os
from ..config import (
    get_working_dir,
    ALLOWED_READ_DIRECTORIES,
    ALLOWED_WRITE_DIRECTORIES,
    BLOCKED_COMMANDS,
)


def resolve_path(path: str = None, default_to_working_dir: bool = True) -> str:
    """Resolve path, using working directory as default if set"""
    working_dir = get_working_dir()
    if path:
        # If path is relative and working dir is set, resolve relative to working dir
        if not os.path.isabs(path) and working_dir:
            return os.path.abspath(os.path.join(working_dir, path))
        return os.path.abspath(os.path.expanduser(path))
    elif default_to_working_dir and working_dir:
        return working_dir
    else:
        return os.getcwd()


def is_path_allowed_for_read(path: str) -> bool:
    """Check if path is allowed for read operations (broader access)"""
    abs_path = os.path.abspath(os.path.expanduser(path))
    for allowed in ALLOWED_READ_DIRECTORIES:
        if abs_path.startswith(os.path.abspath(allowed)):
            return True
    return False


def is_path_allowed_for_write(path: str) -> bool:
    """Check if path is allowed for write operations (more restrictive)"""
    abs_path = os.path.abspath(os.path.expanduser(path))
    for allowed in ALLOWED_WRITE_DIRECTORIES:
        if abs_path.startswith(os.path.abspath(allowed)):
            return True
    return False


def is_path_allowed(path: str, for_write: bool = False) -> bool:
    """Check if path is within allowed directories"""
    if for_write:
        return is_path_allowed_for_write(path)
    return is_path_allowed_for_read(path)


def is_command_safe(command: str) -> bool:
    """Check if command is safe to execute"""
    cmd_lower = command.lower().strip()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return False
    return True
