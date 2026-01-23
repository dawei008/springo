"""
Git Tools
Git repository operations
"""

import os
import subprocess
from typing import Any, Dict, List

from ..utilities.path_utils import resolve_path, is_path_allowed


def _run_git_command(args: List[str], cwd: str = None) -> Dict[str, Any]:
    """Helper to run git commands"""
    try:
        cwd = resolve_path(cwd)
        if not is_path_allowed(cwd):
            return {"error": f"Access denied: {cwd} is outside allowed directories"}

        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cwd
        )

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
            "success": result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {"error": "Git command timed out"}
    except Exception as e:
        return {"error": str(e)}


def git_status(path: str = None) -> Dict[str, Any]:
    """Get git repository status"""
    result = _run_git_command(["status", "--porcelain", "-b"], cwd=path)
    if "error" in result:
        return result

    if not result["success"]:
        return {"error": result["stderr"] or "Not a git repository"}

    lines = result["stdout"].strip().split("\n") if result["stdout"].strip() else []

    status = {
        "branch": None,
        "staged": [],
        "modified": [],
        "untracked": [],
        "deleted": []
    }

    for line in lines:
        if line.startswith("##"):
            status["branch"] = line[3:].split("...")[0] if "..." in line else line[3:]
        elif line.startswith("A "):
            status["staged"].append(line[3:])
        elif line.startswith("M "):
            status["staged"].append(line[3:])
        elif line.startswith(" M"):
            status["modified"].append(line[3:])
        elif line.startswith("??"):
            status["untracked"].append(line[3:])
        elif line.startswith(" D") or line.startswith("D "):
            status["deleted"].append(line[3:])

    return status


def git_log(path: str = None, max_count: int = 10, oneline: bool = False) -> Dict[str, Any]:
    """View commit history"""
    args = ["log", f"-{max_count}"]
    if oneline:
        args.append("--oneline")
    else:
        args.extend(["--pretty=format:%H|%an|%ae|%ad|%s", "--date=iso"])

    result = _run_git_command(args, cwd=path)
    if "error" in result:
        return result

    if not result["success"]:
        return {"error": result["stderr"] or "Failed to get git log"}

    if oneline:
        return {"commits": result["stdout"].strip().split("\n") if result["stdout"].strip() else []}

    commits = []
    for line in result["stdout"].strip().split("\n"):
        if line and "|" in line:
            parts = line.split("|", 4)
            if len(parts) >= 5:
                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "email": parts[2],
                    "date": parts[3],
                    "message": parts[4]
                })

    return {"commits": commits}


def git_diff(path: str = None, file: str = None, staged: bool = False) -> Dict[str, Any]:
    """Show changes"""
    args = ["diff"]
    if staged:
        args.append("--staged")
    if file:
        args.append("--")
        args.append(file)

    result = _run_git_command(args, cwd=path)
    if "error" in result:
        return result

    return {"diff": result["stdout"], "success": result["success"]}


def git_add(files: List[str], path: str = None) -> Dict[str, Any]:
    """Add files to staging area"""
    if not files:
        return {"error": "No files specified"}

    args = ["add"] + files
    result = _run_git_command(args, cwd=path)
    if "error" in result:
        return result

    if not result["success"]:
        return {"error": result["stderr"] or "Failed to add files"}

    return {"success": True, "files": files}


def git_commit(message: str, path: str = None) -> Dict[str, Any]:
    """Create a commit"""
    if not message:
        return {"error": "Commit message is required"}

    result = _run_git_command(["commit", "-m", message], cwd=path)
    if "error" in result:
        return result

    if not result["success"]:
        return {"error": result["stderr"] or "Failed to commit"}

    return {"success": True, "message": message, "output": result["stdout"]}


def git_branch(path: str = None, name: str = None, action: str = "list") -> Dict[str, Any]:
    """Manage branches"""
    if action == "list":
        result = _run_git_command(["branch", "-a"], cwd=path)
        if "error" in result:
            return result

        branches = []
        current = None
        for line in result["stdout"].strip().split("\n"):
            if line.strip():
                if line.startswith("*"):
                    current = line[2:].strip()
                    branches.append(current)
                else:
                    branches.append(line.strip())

        return {"branches": branches, "current": current}

    elif action == "create":
        if not name:
            return {"error": "Branch name is required"}
        result = _run_git_command(["branch", name], cwd=path)
        if "error" in result:
            return result
        return {"success": result["success"], "branch": name, "action": "created"}

    elif action == "delete":
        if not name:
            return {"error": "Branch name is required"}
        result = _run_git_command(["branch", "-d", name], cwd=path)
        if "error" in result:
            return result
        return {"success": result["success"], "branch": name, "action": "deleted"}

    return {"error": f"Unknown action: {action}"}


def git_checkout(target: str, path: str = None, create: bool = False) -> Dict[str, Any]:
    """Switch branches or restore files"""
    args = ["checkout"]
    if create:
        args.append("-b")
    args.append(target)

    result = _run_git_command(args, cwd=path)
    if "error" in result:
        return result

    if not result["success"]:
        return {"error": result["stderr"] or f"Failed to checkout {target}"}

    return {"success": True, "target": target, "created": create}


def git_pull(path: str = None, remote: str = "origin", branch: str = None) -> Dict[str, Any]:
    """Pull from remote"""
    args = ["pull", remote]
    if branch:
        args.append(branch)

    result = _run_git_command(args, cwd=path)
    if "error" in result:
        return result

    return {"success": result["success"], "output": result["stdout"], "errors": result["stderr"]}


def git_push(path: str = None, remote: str = "origin", branch: str = None, set_upstream: bool = False) -> Dict[str, Any]:
    """Push to remote"""
    args = ["push"]
    if set_upstream:
        args.append("-u")
    args.append(remote)
    if branch:
        args.append(branch)

    result = _run_git_command(args, cwd=path)
    if "error" in result:
        return result

    return {"success": result["success"], "output": result["stdout"], "errors": result["stderr"]}


def git_clone(url: str, path: str = None, branch: str = None) -> Dict[str, Any]:
    """Clone a repository"""
    args = ["clone"]
    if branch:
        args.extend(["-b", branch])
    args.append(url)
    if path:
        args.append(path)

    result = _run_git_command(args, cwd=os.getcwd())
    if "error" in result:
        return result

    return {"success": result["success"], "url": url, "output": result["stdout"], "errors": result["stderr"]}


def git(action: str, path: str = None, **kwargs) -> Dict[str, Any]:
    """
    Unified Git tool - combines all git operations into one tool.

    Actions: status, log, diff, add, commit, branch, checkout, pull, push, clone
    """
    action = action.lower()

    handlers = {
        "status": lambda: git_status(path=path),
        "log": lambda: git_log(
            path=path,
            max_count=kwargs.get("max_count", 10),
            oneline=kwargs.get("oneline", False)
        ),
        "diff": lambda: git_diff(
            path=path,
            file=kwargs.get("file"),
            staged=kwargs.get("staged", False)
        ),
        "add": lambda: git_add(
            path=path,
            files=kwargs.get("files", ["."])
        ),
        "commit": lambda: git_commit(
            path=path,
            message=kwargs.get("message", "")
        ),
        "branch": lambda: git_branch(
            path=path,
            name=kwargs.get("name"),
            action=kwargs.get("branch_action", "list")
        ),
        "checkout": lambda: git_checkout(
            path=path,
            target=kwargs.get("target", ""),
            create=kwargs.get("create", False)
        ),
        "pull": lambda: git_pull(
            path=path,
            remote=kwargs.get("remote", "origin"),
            branch=kwargs.get("branch")
        ),
        "push": lambda: git_push(
            path=path,
            remote=kwargs.get("remote", "origin"),
            branch=kwargs.get("branch"),
            set_upstream=kwargs.get("set_upstream", False)
        ),
        "clone": lambda: git_clone(
            url=kwargs.get("url", ""),
            path=path,
            branch=kwargs.get("branch")
        )
    }

    if action not in handlers:
        return {"error": f"Unknown git action: {action}. Valid actions: {', '.join(handlers.keys())}"}

    return handlers[action]()
