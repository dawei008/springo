"""
Springo Team Store
File-based persistence for team state: tasks, messages, agent checkpoints.

Storage layout per team:
    ~/.springo/teams/{team_id}/
        team.json            -- Team metadata (overwritten on change)
        tasks.jsonl          -- Task board (append-only, last-wins dedup on load)
        messages.jsonl       -- Message bus log (append-only, rolling window)
        agents/{name}.json   -- Per-agent conversation checkpoint (overwritten)
"""
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from ..config import settings

logger = logging.getLogger(__name__)


class TeamStore:
    """Persistent file store for a single team's state."""

    def __init__(self, team_id: str):
        self.team_id = team_id
        self.team_dir = settings.team_storage_path / team_id
        self.team_dir.mkdir(parents=True, exist_ok=True)
        self._agents_dir = self.team_dir / "agents"
        self._agents_dir.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Team metadata
    # ------------------------------------------------------------------

    def save_team_meta(self, team_dict: Dict[str, Any]) -> None:
        """Write team.json with team metadata (sans conversation data)."""
        path = self.team_dir / "team.json"
        try:
            path.write_text(
                json.dumps(team_dict, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[TeamStore:{self.team_id}] Failed to save team meta: {e}")

    def load_team_meta(self) -> Optional[Dict[str, Any]]:
        """Read team.json, or None if missing/corrupt."""
        path = self.team_dir / "team.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[TeamStore:{self.team_id}] Failed to load team meta: {e}")
            return None

    # ------------------------------------------------------------------
    # Task board (append-only JSONL, dedup by task_id on load)
    # ------------------------------------------------------------------

    def save_task(self, task_dict: Dict[str, Any]) -> None:
        """Append one JSONL line to tasks.jsonl."""
        path = self.team_dir / "tasks.jsonl"
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(task_dict, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            logger.warning(f"[TeamStore:{self.team_id}] Failed to save task: {e}")

    def load_tasks(self) -> List[Dict[str, Any]]:
        """Read all task lines, deduplicate by task_id (last entry wins)."""
        path = self.team_dir / "tasks.jsonl"
        if not path.exists():
            return []
        seen: Dict[str, Dict[str, Any]] = {}
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    tid = entry.get("task_id", "")
                    if tid:
                        seen[tid] = entry
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.warning(f"[TeamStore:{self.team_id}] Failed to load tasks: {e}")
        return list(seen.values())

    # ------------------------------------------------------------------
    # Message history (append-only JSONL with compaction)
    # ------------------------------------------------------------------

    def save_message(self, msg_dict: Dict[str, Any]) -> None:
        """Append one JSONL line to messages.jsonl."""
        path = self.team_dir / "messages.jsonl"
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(msg_dict, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            logger.warning(f"[TeamStore:{self.team_id}] Failed to save message: {e}")

    def load_messages(self) -> List[Dict[str, Any]]:
        """Read all message lines as dicts."""
        path = self.team_dir / "messages.jsonl"
        if not path.exists():
            return []
        messages: List[Dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.warning(f"[TeamStore:{self.team_id}] Failed to load messages: {e}")
        return messages

    def compact_messages(self, max_lines: int = 500) -> None:
        """If messages.jsonl exceeds max_lines, rewrite with latest N lines."""
        path = self.team_dir / "messages.jsonl"
        if not path.exists():
            return
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            if len(lines) > max_lines:
                path.write_text(
                    "\n".join(lines[-max_lines:]) + "\n",
                    encoding="utf-8",
                )
                logger.info(
                    f"[TeamStore:{self.team_id}] Compacted messages: "
                    f"{len(lines)} -> {max_lines}"
                )
        except Exception as e:
            logger.warning(f"[TeamStore:{self.team_id}] Failed to compact messages: {e}")

    # ------------------------------------------------------------------
    # Agent checkpoints (overwrite per agent)
    # ------------------------------------------------------------------

    def save_agent_checkpoint(self, agent_name: str, data: Dict[str, Any]) -> None:
        """Write agents/{name}.json with conversation checkpoint."""
        safe_name = agent_name.replace("/", "_").replace("\\", "_")
        path = self._agents_dir / f"{safe_name}.json"
        try:
            data["checkpointed_at"] = datetime.now().isoformat()
            path.write_text(
                json.dumps(data, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(
                f"[TeamStore:{self.team_id}] Failed to save checkpoint for {agent_name}: {e}"
            )

    def load_agent_checkpoint(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Read agent checkpoint, or None if missing."""
        safe_name = agent_name.replace("/", "_").replace("\\", "_")
        path = self._agents_dir / f"{safe_name}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(
                f"[TeamStore:{self.team_id}] Failed to load checkpoint for {agent_name}: {e}"
            )
            return None

    def list_agent_checkpoints(self) -> List[str]:
        """Return list of agent names that have saved checkpoints."""
        try:
            return [p.stem for p in self._agents_dir.glob("*.json") if p.is_file()]
        except Exception:
            return []


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def list_persisted_teams() -> List[str]:
    """Scan the team storage directory and return team_ids that have a team.json."""
    base = settings.team_storage_path
    if not base.exists():
        return []
    team_ids: List[str] = []
    try:
        for entry in base.iterdir():
            if entry.is_dir() and (entry / "team.json").exists():
                team_ids.append(entry.name)
    except Exception as e:
        logger.warning(f"[TeamStore] Failed to scan teams directory: {e}")
    return team_ids


def next_team_number() -> int:
    """Return the next available team number by scanning existing teams.

    Reads team_number from each team.json, finds the max, and returns max+1.
    If no teams exist or none have numbers, starts at 1.
    """
    base = settings.team_storage_path
    if not base.exists():
        return 1
    max_num = 0
    try:
        for entry in base.iterdir():
            meta_path = entry / "team.json"
            if entry.is_dir() and meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    num = meta.get("team_number")
                    if isinstance(num, int) and num > max_num:
                        max_num = num
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"[TeamStore] Failed to scan team numbers: {e}")
    return max_num + 1
