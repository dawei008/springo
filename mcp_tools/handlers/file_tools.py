"""
File Operation Tools
Read, write, search, and manage files
"""

import os
import base64
import mimetypes
import subprocess
import shlex
import threading
import time
import shutil
import re
import glob as glob_module
import logging
from typing import Any, Dict, List

from ..config import get_working_dir
from ..utilities.path_utils import (
    resolve_path,
    is_path_allowed,
    is_path_allowed_for_write,
    is_command_safe,
    is_safe_command_prefix,
)

logger = logging.getLogger(__name__)

# Background task tracking
_background_tasks = {}
_task_counter = 0


def read_file(path: str, encoding: str = "utf-8") -> Dict[str, Any]:
    """Read file contents"""
    try:
        abs_path = resolve_path(path, default_to_working_dir=False)

        if not is_path_allowed(abs_path):
            return {"error": f"Access denied: {path} is outside allowed directories"}

        if not os.path.exists(abs_path):
            return {"error": f"File not found: {path}"}

        if not os.path.isfile(abs_path):
            return {"error": f"Not a file: {path}"}

        size = os.path.getsize(abs_path)
        if size > 1024 * 1024:
            return {"error": f"File too large ({size} bytes). Maximum is 1MB."}

        try:
            with open(abs_path, 'r', encoding=encoding) as f:
                content = f.read()
            return {
                "content": content,
                "path": abs_path,
                "size": size,
                "encoding": encoding
            }
        except UnicodeDecodeError:
            with open(abs_path, 'rb') as f:
                content = base64.b64encode(f.read()).decode('ascii')
            return {
                "content": content,
                "path": abs_path,
                "size": size,
                "encoding": "base64",
                "is_binary": True
            }
    except Exception as e:
        return {"error": str(e)}


def write_file(path: str, content: str, encoding: str = "utf-8") -> Dict[str, Any]:
    """Write content to file"""
    try:
        abs_path = resolve_path(path, default_to_working_dir=False)

        if not is_path_allowed_for_write(abs_path):
            return {"error": f"Access denied: {path} is outside allowed write directories"}

        parent = os.path.dirname(abs_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent)

        with open(abs_path, 'w', encoding=encoding) as f:
            f.write(content)

        return {
            "success": True,
            "path": abs_path,
            "size": len(content.encode(encoding))
        }
    except Exception as e:
        return {"error": str(e)}


def list_directory(path: str = None, show_hidden: bool = False) -> Dict[str, Any]:
    """List directory contents"""
    try:
        abs_path = resolve_path(path)

        if not is_path_allowed(abs_path):
            return {"error": f"Access denied: {path} is outside allowed directories"}

        if not os.path.exists(abs_path):
            return {"error": f"Directory not found: {path}"}

        if not os.path.isdir(abs_path):
            return {"error": f"Not a directory: {path}"}

        entries = []
        for name in os.listdir(abs_path):
            if not show_hidden and name.startswith('.'):
                continue

            entry_path = os.path.join(abs_path, name)
            entry = {
                "name": name,
                "type": "directory" if os.path.isdir(entry_path) else "file"
            }

            try:
                stat = os.stat(entry_path)
                entry["size"] = stat.st_size
                entry["modified"] = stat.st_mtime
            except OSError as e:
                logger.debug(f"Could not stat {entry_path}: {e}")

            entries.append(entry)

        entries.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))

        return {
            "path": abs_path,
            "entries": entries,
            "count": len(entries)
        }
    except Exception as e:
        return {"error": str(e)}


def search_files(path: str = None, pattern: str = "*") -> Dict[str, Any]:
    """Search for files matching pattern"""
    try:
        abs_path = resolve_path(path)

        if not is_path_allowed(abs_path):
            return {"error": f"Access denied: {path} is outside allowed directories"}

        if not os.path.exists(abs_path):
            return {"error": f"Directory not found: {path}"}

        search_pattern = os.path.join(abs_path, pattern)
        matches = glob_module.glob(search_pattern, recursive=True)

        if len(matches) > 100:
            matches = matches[:100]
            truncated = True
        else:
            truncated = False

        results = []
        for match in matches:
            rel_path = os.path.relpath(match, abs_path)
            results.append({
                "path": match,
                "relative_path": rel_path,
                "type": "directory" if os.path.isdir(match) else "file"
            })

        return {
            "matches": results,
            "count": len(results),
            "truncated": truncated
        }
    except Exception as e:
        return {"error": str(e)}


def get_file_info(path: str) -> Dict[str, Any]:
    """Get file/directory information"""
    try:
        abs_path = os.path.abspath(os.path.expanduser(path))

        if not is_path_allowed(abs_path):
            return {"error": f"Access denied: {path} is outside allowed directories"}

        if not os.path.exists(abs_path):
            return {"error": f"Path not found: {path}"}

        stat = os.stat(abs_path)

        info = {
            "path": abs_path,
            "name": os.path.basename(abs_path),
            "type": "directory" if os.path.isdir(abs_path) else "file",
            "size": stat.st_size,
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "accessed": stat.st_atime,
            "permissions": oct(stat.st_mode)[-3:]
        }

        if os.path.isfile(abs_path):
            mime_type, _ = mimetypes.guess_type(abs_path)
            info["mime_type"] = mime_type

        return info
    except Exception as e:
        return {"error": str(e)}


def create_directory(path: str) -> Dict[str, Any]:
    """Create directory"""
    try:
        abs_path = os.path.abspath(os.path.expanduser(path))

        if not is_path_allowed_for_write(abs_path):
            return {"error": f"Access denied: {path} is outside allowed write directories"}

        os.makedirs(abs_path, exist_ok=True)

        return {
            "success": True,
            "path": abs_path
        }
    except Exception as e:
        return {"error": str(e)}


def move_file(source: str, destination: str) -> Dict[str, Any]:
    """Move/rename file or directory"""
    try:
        src_path = os.path.abspath(os.path.expanduser(source))
        dst_path = os.path.abspath(os.path.expanduser(destination))

        if not is_path_allowed_for_write(src_path):
            return {"error": f"Access denied: {source} is outside allowed write directories"}
        if not is_path_allowed_for_write(dst_path):
            return {"error": f"Access denied: {destination} is outside allowed write directories"}

        if not os.path.exists(src_path):
            return {"error": f"Source not found: {source}"}

        shutil.move(src_path, dst_path)

        return {
            "success": True,
            "source": src_path,
            "destination": dst_path
        }
    except Exception as e:
        return {"error": str(e)}


def delete_file(path: str) -> Dict[str, Any]:
    """Delete file or empty directory"""
    try:
        abs_path = os.path.abspath(os.path.expanduser(path))

        if not is_path_allowed_for_write(abs_path):
            return {"error": f"Access denied: {path} is outside allowed write directories"}

        if not os.path.exists(abs_path):
            return {"error": f"Path not found: {path}"}

        if os.path.isdir(abs_path):
            os.rmdir(abs_path)
        else:
            os.remove(abs_path)

        return {
            "success": True,
            "path": abs_path
        }
    except OSError as e:
        if "not empty" in str(e).lower() or e.errno == 66:
            return {"error": "Directory is not empty. Use execute_command with 'rm -r' for non-empty directories."}
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


def _should_use_shell(command: str) -> bool:
    """Determine if command requires shell execution"""
    shell_features = ['|', '&&', '||', ';', '>', '<', '*', '?', '$', '`', '"', "'", '\\']
    return any(feat in command for feat in shell_features)


def execute_command(command: str, working_directory: str = None, timeout: int = 60,
                   run_in_background: bool = False, description: str = None) -> Dict[str, Any]:
    """Execute shell command with improved security"""
    global _task_counter

    try:
        if not command or not command.strip():
            return {"error": "Empty command"}

        if not is_command_safe(command):
            return {"error": "Command blocked for safety reasons"}

        cwd = resolve_path(working_directory)
        if not is_path_allowed(cwd):
            return {"error": f"Access denied: {cwd} is outside allowed directories"}
        if not os.path.isdir(cwd):
            return {"error": f"Working directory not found: {cwd}"}

        # Determine execution mode
        use_shell = _should_use_shell(command)
        if use_shell:
            cmd_args = command
        else:
            # Use shlex for safer argument parsing when no shell features needed
            try:
                cmd_args = shlex.split(command)
            except ValueError as e:
                logger.warning(f"shlex.split failed, falling back to shell: {e}")
                cmd_args = command
                use_shell = True

        if run_in_background:
            _task_counter += 1
            task_id = f"task_{_task_counter}"

            output_file = f"/tmp/claude_task_{task_id}.output"

            process = subprocess.Popen(
                cmd_args,
                shell=use_shell,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=cwd
            )

            _background_tasks[task_id] = {
                "process": process,
                "command": command,
                "description": description or command[:50],
                "started_at": time.time(),
                "output_file": output_file,
                "status": "running"
            }

            def capture_output():
                output = []
                try:
                    for line in process.stdout:
                        output.append(line)
                    process.wait()
                except Exception as e:
                    logger.debug(f"Background task output capture error: {e}")
                finally:
                    try:
                        with open(output_file, 'w') as f:
                            f.write(''.join(output))
                    except IOError as e:
                        logger.error(f"Failed to write output file: {e}")
                    _background_tasks[task_id]["status"] = "completed"
                    _background_tasks[task_id]["return_code"] = process.returncode

            thread = threading.Thread(target=capture_output, daemon=True)
            thread.start()

            return {
                "success": True,
                "task_id": task_id,
                "status": "running",
                "output_file": output_file,
                "message": f"Command started in background. Use get_task_status('{task_id}') to check progress."
            }
        else:
            result = subprocess.run(
                cmd_args,
                shell=use_shell,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd
            )

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
                "command": command,
                "working_directory": cwd or os.getcwd()
            }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout} seconds"}
    except Exception as e:
        logger.error(f"Command execution error: {e}")
        return {"error": str(e)}


def get_task_status(task_id: str) -> Dict[str, Any]:
    """Get the status and output of a background task"""
    if task_id not in _background_tasks:
        return {"error": f"Unknown task: {task_id}"}

    task = _background_tasks[task_id]

    result = {
        "task_id": task_id,
        "command": task["command"],
        "description": task["description"],
        "status": task["status"],
        "started_at": task["started_at"]
    }

    if task["status"] == "completed":
        result["return_code"] = task.get("return_code")
        try:
            with open(task["output_file"], 'r') as f:
                output = f.read()
            result["output"] = output[:50000] if len(output) > 50000 else output
            if len(output) > 50000:
                result["truncated"] = True
        except (IOError, OSError) as e:
            logger.debug(f"Could not read output file: {e}")
            result["output"] = "(output file not found)"
    else:
        result["output_file"] = task["output_file"]
        result["message"] = "Task still running. Check output_file for partial output."

    return result


def list_background_tasks() -> Dict[str, Any]:
    """List all background tasks"""
    tasks = []
    for task_id, task in _background_tasks.items():
        tasks.append({
            "task_id": task_id,
            "command": task["command"][:50],
            "description": task["description"],
            "status": task["status"],
            "started_at": task["started_at"]
        })

    return {
        "tasks": tasks,
        "count": len(tasks)
    }


def glob_files(pattern: str, path: str = None, limit: int = 100) -> Dict[str, Any]:
    """Fast file pattern matching using glob"""
    base_path = path or get_working_dir() or os.getcwd()

    if not is_path_allowed(base_path, for_write=False):
        return {"error": f"Access denied: {base_path}"}

    try:
        if os.path.isabs(pattern):
            full_pattern = pattern
        else:
            full_pattern = os.path.join(base_path, pattern)

        matches = glob_module.glob(full_pattern, recursive=True)

        matches_with_time = []
        for m in matches:
            try:
                mtime = os.path.getmtime(m)
                matches_with_time.append((m, mtime))
            except OSError:
                matches_with_time.append((m, 0))

        matches_with_time.sort(key=lambda x: x[1], reverse=True)

        limited_matches = [m[0] for m in matches_with_time[:limit]]

        relative_matches = []
        for m in limited_matches:
            try:
                rel = os.path.relpath(m, base_path)
                relative_matches.append(rel)
            except ValueError:
                relative_matches.append(m)

        return {
            "success": True,
            "pattern": pattern,
            "base_path": base_path,
            "files": relative_matches,
            "count": len(relative_matches),
            "total_matches": len(matches),
            "truncated": len(matches) > limit
        }
    except Exception as e:
        return {"error": f"Glob failed: {str(e)}"}


def grep_search(pattern: str, path: str = None, glob_pattern: str = None,
                output_mode: str = "files_with_matches", context_lines: int = 2,
                ignore_case: bool = False, limit: int = 50) -> Dict[str, Any]:
    """Search for content in files using regex"""
    base_path = path or get_working_dir() or os.getcwd()

    if not is_path_allowed(base_path, for_write=False):
        return {"error": f"Access denied: {base_path}"}

    try:
        flags = re.IGNORECASE if ignore_case else 0
        regex = re.compile(pattern, flags)

        if os.path.isfile(base_path):
            files_to_search = [base_path]
        else:
            if glob_pattern:
                full_glob = os.path.join(base_path, glob_pattern)
                files_to_search = glob_module.glob(full_glob, recursive=True)
            else:
                files_to_search = []
                for root, dirs, files in os.walk(base_path):
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    for f in files:
                        if not f.endswith(('.pyc', '.so', '.dll', '.exe', '.bin', '.zip', '.tar', '.gz', '.jpg', '.png', '.gif', '.pdf')):
                            files_to_search.append(os.path.join(root, f))

        results = []
        files_with_matches = []
        total_matches = 0

        for file_path in files_to_search:
            if len(results) >= limit and output_mode != "count":
                break

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()

                file_matches = []
                for line_num, line in enumerate(lines, 1):
                    if regex.search(line):
                        file_matches.append({
                            "line_number": line_num,
                            "content": line.rstrip()
                        })

                if file_matches:
                    rel_path = os.path.relpath(file_path, base_path)
                    files_with_matches.append(rel_path)
                    total_matches += len(file_matches)

                    if output_mode == "content":
                        for match in file_matches[:limit]:
                            ln = match["line_number"]
                            start = max(0, ln - context_lines - 1)
                            end = min(len(lines), ln + context_lines)
                            context = []
                            for i in range(start, end):
                                prefix = ">" if i == ln - 1 else " "
                                context.append(f"{prefix}{i+1}: {lines[i].rstrip()}")

                            results.append({
                                "file": rel_path,
                                "line": ln,
                                "match": match["content"],
                                "context": "\n".join(context)
                            })

                            if len(results) >= limit:
                                break
                    elif output_mode == "count":
                        results.append({
                            "file": rel_path,
                            "count": len(file_matches)
                        })

            except Exception:
                continue

        if output_mode == "files_with_matches":
            return {
                "success": True,
                "pattern": pattern,
                "files": files_with_matches[:limit],
                "count": len(files_with_matches),
                "total_matches": total_matches
            }
        else:
            return {
                "success": True,
                "pattern": pattern,
                "results": results,
                "files_searched": len(files_to_search),
                "files_with_matches": len(files_with_matches),
                "total_matches": total_matches,
                "truncated": total_matches > limit
            }

    except re.error as e:
        return {"error": f"Invalid regex pattern: {str(e)}"}
    except Exception as e:
        return {"error": f"Grep failed: {str(e)}"}


def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> Dict[str, Any]:
    """Edit a file by replacing a specific string"""
    if not os.path.isabs(path):
        full_path = os.path.join(get_working_dir() or os.getcwd(), path)
    else:
        full_path = path

    if not is_path_allowed(full_path, for_write=True):
        return {"error": f"Write access denied: {full_path}"}

    if not os.path.exists(full_path):
        return {"error": f"File not found: {path}"}

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()

        occurrences = content.count(old_string)

        if occurrences == 0:
            return {
                "error": f"String not found in file",
                "old_string_preview": old_string[:100] + "..." if len(old_string) > 100 else old_string
            }

        if occurrences > 1 and not replace_all:
            return {
                "error": f"String found {occurrences} times. Use replace_all=True to replace all, or provide a more unique string.",
                "occurrences": occurrences
            }

        if replace_all:
            new_content = content.replace(old_string, new_string)
            replaced_count = occurrences
        else:
            new_content = content.replace(old_string, new_string, 1)
            replaced_count = 1

        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return {
            "success": True,
            "path": path,
            "replacements": replaced_count,
            "message": f"Replaced {replaced_count} occurrence(s)"
        }

    except Exception as e:
        return {"error": f"Edit failed: {str(e)}"}


def read_files(paths: List[str], encoding: str = "utf-8") -> Dict[str, Any]:
    """Read multiple files at once"""
    results = {}
    errors = {}

    for path in paths:
        if not os.path.isabs(path):
            full_path = os.path.join(get_working_dir() or os.getcwd(), path)
        else:
            full_path = path

        if not is_path_allowed(full_path, for_write=False):
            errors[path] = "Access denied"
            continue

        if not os.path.exists(full_path):
            errors[path] = "File not found"
            continue

        try:
            with open(full_path, 'r', encoding=encoding, errors='replace') as f:
                content = f.read()

            if len(content) > 100000:
                content = content[:100000] + "\n... (truncated, file too large)"

            results[path] = {
                "content": content,
                "size": os.path.getsize(full_path),
                "lines": content.count('\n') + 1
            }
        except Exception as e:
            errors[path] = str(e)

    return {
        "success": len(results) > 0,
        "files": results,
        "errors": errors if errors else None,
        "read_count": len(results),
        "error_count": len(errors)
    }
