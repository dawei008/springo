"""
Plugin Manager for Springo

Loads Claude Code plugins from ~/.springo/plugins/.
Compatible with Anthropic's official plugin format (.claude-plugin/).

Directory layout:
    ~/.springo/plugins/{plugin_name}/
        .claude-plugin/
            plugin.json      # manifest (name, description, author)
        hooks/
            hooks.json       # shell command hooks
        skills/              # SKILL.md directories
        commands/            # *.md command files → registered as skills
        agents/              # *.md agent files → registered as agent templates
        .mcp.json            # MCP server config
"""
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .hook_pipeline import HookContext, get_hook_pipeline  # noqa: F401

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class PluginManifest:
    """Parsed .claude-plugin/plugin.json manifest."""

    def __init__(self, raw: Dict[str, Any]):
        self.name: str = raw["name"]
        self.version: str = raw.get("version", "1.0.0")
        self.description: str = raw.get("description", "")
        self.enabled: bool = raw.get("enabled", True)

        # Normalize author — Claude Code uses {"name": ..., "email": ...}
        author = raw.get("author", "")
        if isinstance(author, dict):
            self.author: str = author.get("name", "")
        else:
            self.author = str(author)


class Plugin:
    """A loaded plugin with its manifest and resolved hook functions."""

    def __init__(self, manifest: PluginManifest, path: str):
        self.manifest = manifest
        self.path = path
        self.hook_functions: List[Dict[str, Any]] = []  # [{hook_point, function, priority}]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.manifest.name,
            "version": self.manifest.version,
            "description": self.manifest.description,
            "author": self.manifest.author,
            "enabled": self.manifest.enabled,
            "path": self.path,
            "hooks": [
                {"hook_point": h["hook_point"], "priority": h.get("priority", 50)}
                for h in self.hook_functions
            ],
        }


# ---------------------------------------------------------------------------
# Plugin Manager
# ---------------------------------------------------------------------------

class PluginManager:
    """Loads, registers, and manages Claude Code plugins."""

    # Hook name mapping: Claude Code PascalCase → Springo snake_case
    _HOOK_MAP: Dict[str, str] = {
        "PreToolUse": "pre_tool_use",
        "PostToolUse": "post_tool_use",
        "Stop": "stop",
        "UserPromptSubmit": "user_prompt_submit",
        "SessionStart": "session_start",
    }

    def __init__(self, plugins_dir: str = None):
        if plugins_dir is None:
            plugins_dir = os.path.expanduser("~/.springo/plugins")
        self.plugins_dir = Path(plugins_dir)
        self.plugins: Dict[str, Plugin] = {}
        self._loaded = False

    # -- lifecycle --

    def load_plugins(self) -> int:
        """Scan plugins directory and load all valid plugins. Returns count."""
        self.plugins = {}

        if not self.plugins_dir.exists():
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created plugins directory: {self.plugins_dir}")
            self._loaded = True
            return 0

        for plugin_dir in sorted(self.plugins_dir.iterdir()):
            if not plugin_dir.is_dir():
                continue
            manifest_file = plugin_dir / ".claude-plugin" / "plugin.json"
            if not manifest_file.exists():
                continue
            try:
                plugin = self._load_plugin(plugin_dir, manifest_file)
                if plugin and plugin.manifest.enabled:
                    self.plugins[plugin.manifest.name] = plugin
                    logger.info(
                        f"Loaded plugin: {plugin.manifest.name} v{plugin.manifest.version} "
                        f"({len(plugin.hook_functions)} hooks)"
                    )
            except Exception as e:
                logger.error(f"Failed to load plugin from {plugin_dir.name}: {e}")

        self._loaded = True
        logger.info(f"Plugin system: {len(self.plugins)} plugin(s) loaded")
        return len(self.plugins)

    def reload(self) -> int:
        """Force-reload all plugins."""
        pipeline = get_hook_pipeline()
        for name in self.plugins:
            pipeline.unregister(name)
        self._loaded = False
        return self.load_plugins()

    # -- loading internals --

    def _load_plugin(self, plugin_dir: Path, manifest_file: Path) -> Optional[Plugin]:
        with open(manifest_file, "r", encoding="utf-8") as f:
            raw = json.load(f)

        manifest = PluginManifest(raw)
        plugin = Plugin(manifest=manifest, path=str(plugin_dir))
        pipeline = get_hook_pipeline()

        # 1. Parse hooks/hooks.json → subprocess hooks
        for hook_def in self._parse_hooks_json(plugin_dir):
            func = self._create_subprocess_hook(
                hook_def["command"], plugin_dir, hook_def.get("timeout", 30)
            )
            hook_point = hook_def["hook_point"]
            priority = hook_def.get("priority", 50)
            pipeline.register(hook_point, func, plugin_name=manifest.name, priority=priority)
            plugin.hook_functions.append({
                "hook_point": hook_point,
                "function": func,
                "priority": priority,
            })

        # 2. Auto-discover skills/ directories
        self._register_skills(manifest, plugin_dir)

        # 3. Register commands/*.md as skills
        self._register_commands(manifest, plugin_dir)

        # 4. Register agents/*.md as agent templates
        self._register_agents(manifest, plugin_dir)

        # 5. Parse .mcp.json
        self._register_mcp_servers(manifest, plugin_dir)

        return plugin

    # -- hooks --

    def _parse_hooks_json(self, plugin_dir: Path) -> List[Dict[str, Any]]:
        """Parse hooks/hooks.json → list of hook definitions.

        Returns: [{hook_point, command, timeout}]
        """
        hooks_file = plugin_dir / "hooks" / "hooks.json"
        if not hooks_file.exists():
            return []

        try:
            with open(hooks_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            logger.error(f"Failed to parse hooks.json in {plugin_dir.name}: {e}")
            return []

        results: List[Dict[str, Any]] = []

        # Format: {"hooks": {"PreToolUse": [{"command": "...", "timeout": 30}], ...}}
        hooks_section = raw.get("hooks", raw)
        for event_name, hook_list in hooks_section.items():
            snake = self._HOOK_MAP.get(event_name)
            if not snake:
                logger.warning(f"Unknown hook event: {event_name}")
                continue
            if not isinstance(hook_list, list):
                hook_list = [hook_list]
            for entry in hook_list:
                if isinstance(entry, dict) and "command" in entry:
                    results.append({
                        "hook_point": snake,
                        "command": entry["command"],
                        "timeout": entry.get("timeout", 30),
                    })

        return results

    def _create_subprocess_hook(
        self, command: str, plugin_dir: Path, timeout: int = 30
    ) -> Callable:
        """Create a subprocess wrapper for a shell command hook.

        stdin/stdout JSON protocol:
          stdin:  {"hook_event_name": "PreToolUse", "tool_name": ..., "tool_input": ...}
          stdout: {"systemMessage": "...", "hookSpecificOutput": {"permissionDecision": "deny"}}
        """
        _reverse_map = {v: k for k, v in self._HOOK_MAP.items()}

        def hook_fn(ctx: HookContext) -> None:
            pascal_name = _reverse_map.get(ctx.hook_point, ctx.hook_point)
            stdin_data = self._build_hook_input(ctx, pascal_name)

            cmd = command.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_dir))
            env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(plugin_dir)}

            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    input=json.dumps(stdin_data),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                    cwd=str(plugin_dir),
                )
                if result.returncode != 0 and result.stderr.strip():
                    logger.warning(
                        f"Subprocess hook exited {result.returncode}: {result.stderr[:200]}"
                    )
                if result.stdout.strip():
                    try:
                        output = json.loads(result.stdout)
                        self._apply_hook_output(ctx, output)
                    except json.JSONDecodeError:
                        logger.debug(f"Non-JSON stdout from hook: {result.stdout[:200]}")
            except subprocess.TimeoutExpired:
                logger.error(f"Subprocess hook timed out after {timeout}s: {cmd[:80]}")
            except Exception as e:
                logger.error(f"Subprocess hook failed: {e}")

        hook_fn.__name__ = f"subprocess_hook_{plugin_dir.name}"
        return hook_fn

    @staticmethod
    def _build_hook_input(ctx: HookContext, hook_event_name: str) -> Dict[str, Any]:
        """Build stdin JSON for subprocess hooks."""
        payload: Dict[str, Any] = {"hook_event_name": hook_event_name}

        if ctx.hook_point in ("pre_tool_use", "post_tool_use"):
            payload["tool_name"] = ctx.data.get("tool_name", "")
            payload["tool_input"] = ctx.data.get("tool_input", {})
            if ctx.hook_point == "post_tool_use":
                payload["tool_result"] = ctx.data.get("tool_result", "")
        elif ctx.hook_point == "user_prompt_submit":
            payload["user_message"] = ctx.data.get("user_message", "")
        elif ctx.hook_point == "stop":
            payload["stop_reason"] = ctx.data.get("stop_reason", "")
            payload["text"] = ctx.data.get("text", "")

        if ctx.session_id:
            payload["session_id"] = ctx.session_id

        return payload

    @staticmethod
    def _apply_hook_output(ctx: HookContext, output: Dict[str, Any]) -> None:
        """Apply subprocess hook stdout JSON to HookContext."""
        sys_msg = output.get("systemMessage")
        if sys_msg:
            ctx.metadata["system_message"] = sys_msg

        specific = output.get("hookSpecificOutput", {})
        if isinstance(specific, dict):
            decision = specific.get("permissionDecision", "")
            if decision == "deny":
                ctx.stop_pipeline = True
                ctx.metadata["deny_reason"] = specific.get("reason", "Denied by plugin hook")
            elif decision == "allow":
                ctx.metadata["permission_granted"] = True

            modified_input = specific.get("toolInput")
            if modified_input is not None and isinstance(modified_input, dict):
                ctx.data["tool_input"] = modified_input

    # -- resource registration --

    def _register_skills(self, manifest: PluginManifest, plugin_dir: Path) -> None:
        """Symlink plugin skills/ subdirectories into ~/.springo/skills/."""
        skills_src = plugin_dir / "skills"
        if not skills_src.is_dir():
            return

        skills_dir = Path(os.path.expanduser("~/.springo/skills"))
        skills_dir.mkdir(parents=True, exist_ok=True)

        for d in sorted(skills_src.iterdir()):
            if not d.is_dir() or not (d / "SKILL.md").exists():
                continue

            dst = skills_dir / f"{manifest.name}_{d.name}"
            try:
                if dst.is_symlink():
                    dst.unlink()
                elif dst.exists():
                    continue
                dst.symlink_to(d.resolve(), target_is_directory=True)
                logger.info(f"Registered skill: {dst.name} -> {d}")
            except OSError:
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(d, dst)
                logger.info(f"Registered skill (copied): {dst.name}")

    def _register_commands(self, manifest: PluginManifest, plugin_dir: Path) -> None:
        """Convert commands/*.md into synthetic SKILL.md entries."""
        commands_dir = plugin_dir / "commands"
        if not commands_dir.is_dir():
            return

        skills_dir = Path(os.path.expanduser("~/.springo/skills"))
        skills_dir.mkdir(parents=True, exist_ok=True)

        for md_file in sorted(commands_dir.glob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8")
                frontmatter, body = self._parse_markdown_frontmatter(content)

                cmd_name = md_file.stem
                description = frontmatter.get("description", f"Command: {cmd_name}")
                argument_hint = frontmatter.get("argument-hint", "")
                allowed_tools = frontmatter.get("allowed-tools", [])

                skill_lines = [f"# {cmd_name}", "", f"**Description:** {description}"]
                if argument_hint:
                    skill_lines.append(f"**Argument hint:** {argument_hint}")
                if allowed_tools:
                    tools_str = ", ".join(allowed_tools) if isinstance(allowed_tools, list) else str(allowed_tools)
                    skill_lines.append(f"**Allowed tools:** {tools_str}")
                skill_lines.extend(["", "## Instructions", "", body.strip()])

                skill_dir = skills_dir / f"{manifest.name}_{cmd_name}"
                skill_dir.mkdir(parents=True, exist_ok=True)
                (skill_dir / "SKILL.md").write_text("\n".join(skill_lines), encoding="utf-8")
                logger.info(f"Registered command as skill: {skill_dir.name}")
            except Exception as e:
                logger.error(f"Failed to register command {md_file.name}: {e}")

    def _register_agents(self, manifest: PluginManifest, plugin_dir: Path) -> None:
        """Convert agents/*.md into agent template JSON files."""
        agents_md_dir = plugin_dir / "agents"
        if not agents_md_dir.is_dir():
            return

        agents_dir = Path(os.path.expanduser("~/.springo/agents"))
        agents_dir.mkdir(parents=True, exist_ok=True)

        for md_file in sorted(agents_md_dir.glob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8")
                frontmatter, body = self._parse_markdown_frontmatter(content)

                agent_name = frontmatter.get("name", md_file.stem)
                template = {
                    "name": agent_name,
                    "role": agent_name,
                    "description": frontmatter.get("description", ""),
                    "model": frontmatter.get("model", ""),
                    "system_prompt": body.strip(),
                    "tools": frontmatter.get("tools", []),
                    "metadata": {"source_plugin": manifest.name},
                }
                if "color" in frontmatter:
                    template["metadata"]["color"] = frontmatter["color"]

                dst = agents_dir / f"{agent_name}.json"
                with open(dst, "w", encoding="utf-8") as f:
                    json.dump(template, f, indent=2)
                logger.info(f"Registered agent template: {agent_name} (from {md_file.name})")
            except Exception as e:
                logger.error(f"Failed to register agent {md_file.name}: {e}")

    def _register_mcp_servers(self, manifest: PluginManifest, plugin_dir: Path) -> None:
        """Merge .mcp.json servers into ~/.springo/mcp_servers.json."""
        mcp_json_file = plugin_dir / ".mcp.json"
        if not mcp_json_file.exists():
            return

        try:
            with open(mcp_json_file, "r", encoding="utf-8") as f:
                mcp_config = json.load(f)
        except Exception as e:
            logger.error(f"Failed to parse .mcp.json in {plugin_dir.name}: {e}")
            return

        servers: List[Dict[str, Any]] = []
        for srv_name, srv_def in mcp_config.items():
            if not isinstance(srv_def, dict):
                continue
            srv_entry = {"name": srv_name}
            for k, v in srv_def.items():
                if isinstance(v, str):
                    v = v.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_dir))
                elif isinstance(v, list):
                    v = [
                        item.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_dir))
                        if isinstance(item, str) else item
                        for item in v
                    ]
                srv_entry[k] = v
            servers.append(srv_entry)

        if not servers:
            return

        config_path = Path(os.path.expanduser("~/.springo/mcp_servers.json"))
        config_path.parent.mkdir(parents=True, exist_ok=True)

        if config_path.exists():
            with open(config_path, "r") as f:
                config = json.load(f)
        else:
            config = {"servers": []}

        existing = {s["name"] for s in config["servers"]}
        added = 0
        for srv in servers:
            if srv["name"] not in existing:
                config["servers"].append(srv)
                added += 1

        if added:
            tmp_path = config_path.with_suffix(".tmp")
            with open(tmp_path, "w") as f:
                json.dump(config, f, indent=2)
            tmp_path.replace(config_path)
            logger.info(f"Registered {added} MCP server(s) from plugin '{manifest.name}'")

    # -- utils --

    @staticmethod
    def _parse_markdown_frontmatter(content: str) -> tuple:
        """Parse YAML-style frontmatter (--- delimited) from markdown.

        Returns (frontmatter_dict, body_str).
        """
        frontmatter: Dict[str, Any] = {}
        body = content

        stripped = content.strip()
        if stripped.startswith("---"):
            end_idx = stripped.find("---", 3)
            if end_idx > 0:
                fm_text = stripped[3:end_idx].strip()
                body = stripped[end_idx + 3:].strip()

                for line in fm_text.split("\n"):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if ":" in line:
                        key, _, val = line.partition(":")
                        key = key.strip()
                        val = val.strip()
                        if val.startswith("[") and val.endswith("]"):
                            items = [
                                item.strip().strip("'\"")
                                for item in val[1:-1].split(",")
                                if item.strip()
                            ]
                            frontmatter[key] = items
                        elif (val.startswith('"') and val.endswith('"')) or \
                             (val.startswith("'") and val.endswith("'")):
                            frontmatter[key] = val[1:-1]
                        else:
                            frontmatter[key] = val

        return frontmatter, body

    # -- query --

    def list_plugins(self) -> List[Dict[str, Any]]:
        if not self._loaded:
            self.load_plugins()
        return [p.to_dict() for p in self.plugins.values()]

    def get_plugin(self, name: str) -> Optional[Plugin]:
        if not self._loaded:
            self.load_plugins()
        return self.plugins.get(name)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    global _manager
    if _manager is None:
        _manager = PluginManager()
    return _manager
