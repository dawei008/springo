# Springo Configuration Directory (~/.springo/)

Springo's configuration and data are stored in `~/.springo/`. Key files and directories:

| Path | Purpose |
|------|---------|
| `SPRINGO.md` | This file - Springo project reference documentation |
| `config.json` | App settings: AWS credentials, region, model, AgentCore Memory config, S3 sync config |
| `mcp_servers.json` | External MCP server definitions (name, command, args, env, enabled) |
| `mcp_tools_cache.json` | Cached tool schemas from MCP servers (avoids re-discovery on startup) |
| `cache.json` | Electron frontend state: workspace folders, current working directory, UI preferences |
| `scheduled_tasks.json` | User-created scheduled/recurring tasks (cron, delay, one-time) |
| `sessions/` | Persisted chat sessions (each session is a JSONL file with messages and metadata) |
| `skills/` | Skill plugins directory. Full path: `~/.springo/skills/`. Each skill is a subfolder containing a `SKILL.md` file with YAML frontmatter (name, description) and instructions. Use `read_file ~/.springo/skills/<name>/SKILL.md` to inspect a skill. |
| `scripts/` | Helper scripts (e.g., start-playwright-cdp.sh) |
| `cache/` | Temporary cache data |
| `failed_uploads/` | Files that failed to upload to S3 (for retry) |

When users ask about configuration, settings, or stored data, refer to these paths.
