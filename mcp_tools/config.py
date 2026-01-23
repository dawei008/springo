"""
MCP Tools Configuration
Global settings, security constants, and working directory management
"""

import os

# Working directory configuration (set by user from UI)
_working_dir = ""

def set_working_dir(path: str):
    """Set the current working directory for tool operations"""
    global _working_dir
    _working_dir = os.path.abspath(os.path.expanduser(path)) if path else ""

def get_working_dir() -> str:
    """Get the current working directory"""
    return _working_dir

# Safety: Define allowed directories for READ operations (broader access for skills, system files)
ALLOWED_READ_DIRECTORIES = [
    "/",  # Allow reading from anywhere (for skills, system files, etc.)
]

# Safety: Define allowed directories for WRITE operations (more restrictive)
# Writing is restricted to user home; working_dir further restricts output location
ALLOWED_WRITE_DIRECTORIES = [
    os.path.expanduser("~"),  # User home only for writes
    "/tmp",  # Temp directory allowed for writes
]

# Safety: Commands that are blocked
BLOCKED_COMMANDS = [
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=", ":(){:|:&};:",
    "chmod -R 777 /", "chown -R", "> /dev/sda",
]
