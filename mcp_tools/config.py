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

# Safety: Define allowed directories for READ operations
# More restrictive - only user home and common development paths
ALLOWED_READ_DIRECTORIES = [
    os.path.expanduser("~"),  # User home directory
    "/tmp",                    # Temp directory
    "/usr/local",              # Local installations
    "/opt",                    # Optional software
]

# Safety: Define allowed directories for WRITE operations (more restrictive)
ALLOWED_WRITE_DIRECTORIES = [
    os.path.expanduser("~"),  # User home only for writes
    "/tmp",                    # Temp directory allowed for writes
]

# Safety: Sensitive paths that should NEVER be read
BLOCKED_READ_PATHS = [
    # Credentials and secrets
    os.path.expanduser("~/.aws/credentials"),
    os.path.expanduser("~/.aws/config"),
    os.path.expanduser("~/.ssh"),
    os.path.expanduser("~/.gnupg"),
    os.path.expanduser("~/.netrc"),
    os.path.expanduser("~/.npmrc"),
    os.path.expanduser("~/.pypirc"),
    os.path.expanduser("~/.docker/config.json"),
    os.path.expanduser("~/.kube/config"),
    # System files
    "/etc/shadow",
    "/etc/passwd",
    "/etc/sudoers",
    "/etc/master.passwd",
    # Environment files with potential secrets
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "secrets.json",
    "config/secrets",
]

# Safety: Dangerous command patterns (using regex-like patterns)
BLOCKED_COMMAND_PATTERNS = [
    # Destructive file operations
    r"rm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+)*(-[a-zA-Z]*f[a-zA-Z]*\s+)*[/~]",  # rm -rf / or ~
    r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)*(-[a-zA-Z]*r[a-zA-Z]*\s+)*[/~]",  # rm -fr / or ~
    r"rm\s+--recursive",
    r"rm\s+--force",
    # Disk operations
    r"mkfs",
    r"dd\s+if=",
    r">\s*/dev/sd",
    r">\s*/dev/nvme",
    # Fork bomb
    r":\(\)\{.*\}",
    # Permission changes on root
    r"chmod\s+(-[a-zA-Z]*R[a-zA-Z]*\s+)*777\s+/",
    r"chown\s+(-[a-zA-Z]*R[a-zA-Z]*\s+).*\s+/",
    # System shutdown
    r"shutdown",
    r"reboot",
    r"init\s+[0-6]",
    r"systemctl\s+(halt|poweroff|reboot)",
    # History manipulation
    r"history\s+-c",
    r">\s*~/.bash_history",
    # Dangerous curl/wget piped to shell
    r"curl.*\|\s*(ba)?sh",
    r"wget.*\|\s*(ba)?sh",
    # Reverse shells
    r"bash\s+-i\s+>&",
    r"nc\s+-e",
    r"ncat\s+-e",
]

# Whitelisted safe commands (for safer execution)
SAFE_COMMAND_PREFIXES = [
    "ls", "pwd", "echo", "cat", "head", "tail", "grep", "find", "wc",
    "git", "npm", "yarn", "pnpm", "pip", "python", "python3", "node",
    "make", "cargo", "go", "rustc", "gcc", "g++", "clang",
    "cd", "mkdir", "touch", "cp", "mv", "open", "code",
    "brew", "apt", "yum", "dnf",
    "docker", "kubectl", "aws", "gcloud", "az",
    "curl", "wget", "ssh", "scp", "rsync",
    "tar", "zip", "unzip", "gzip", "gunzip",
    "diff", "sort", "uniq", "awk", "sed", "cut", "tr",
    "date", "whoami", "hostname", "uname", "env", "printenv",
    "which", "whereis", "type", "file", "stat",
    "ps", "top", "htop", "df", "du", "free",
    "ping", "traceroute", "dig", "nslookup", "host",
]

# Legacy compatibility - will be removed
BLOCKED_COMMANDS = [
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=", ":(){:|:&};:",
    "chmod -R 777 /", "chown -R", "> /dev/sda",
]
