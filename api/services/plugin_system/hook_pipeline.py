"""
Hook Pipeline for Springo Plugin System

Sync/blocking middleware chain for lifecycle hooks.
Hooks can observe, modify, or block the data flowing through the pipeline.

Hook Points:
  - pre_message:          Before sending messages to model
  - post_message:         After model response
  - pre_tool_use:         Before tool execution (can block/substitute)
  - post_tool_use:        After tool execution (can modify result)
  - stop:                 When model returns end_turn (observational)
  - user_prompt_submit:   Before user prompt is processed
  - session_start:        On first message in a session
"""
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Valid hook points
HOOK_POINTS = {
    "pre_message", "post_message", "pre_tool_use", "post_tool_use",
    "stop", "user_prompt_submit", "session_start",
}


@dataclass
class HookContext:
    """Context passed through hook pipeline.

    Hooks modify ``data`` in-place. Set ``stop_pipeline = True``
    to prevent subsequent hooks from running.
    """
    hook_point: str
    data: Dict[str, Any]
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    stop_pipeline: bool = False
    stopped_by: Optional[str] = None


@dataclass
class _RegisteredHook:
    """Internal: a registered hook function with metadata."""
    hook_point: str
    function: Callable[[HookContext], Optional[HookContext]]
    plugin_name: str
    priority: int  # lower = earlier


class HookPipeline:
    """Manages hook execution as a prioritized middleware chain."""

    def __init__(self):
        self._hooks: Dict[str, List[_RegisteredHook]] = {hp: [] for hp in HOOK_POINTS}
        self._lock = threading.RLock()

    # -- registration --

    def register(
        self,
        hook_point: str,
        function: Callable,
        plugin_name: str = "",
        priority: int = 50,
    ) -> None:
        if hook_point not in HOOK_POINTS:
            logger.error(f"Invalid hook point: {hook_point} (valid: {HOOK_POINTS})")
            return

        entry = _RegisteredHook(
            hook_point=hook_point,
            function=function,
            plugin_name=plugin_name,
            priority=priority,
        )
        with self._lock:
            self._hooks[hook_point].append(entry)
            self._hooks[hook_point].sort(key=lambda h: h.priority)
        logger.info(f"Registered hook: {hook_point} from '{plugin_name}' (priority={priority})")

    def unregister(self, plugin_name: str, hook_point: str = None) -> int:
        """Remove all hooks for *plugin_name*. If *hook_point* given, only that point."""
        removed = 0
        points = [hook_point] if hook_point else list(HOOK_POINTS)
        with self._lock:
            for hp in points:
                before = len(self._hooks[hp])
                self._hooks[hp] = [h for h in self._hooks[hp] if h.plugin_name != plugin_name]
                removed += before - len(self._hooks[hp])
        if removed:
            logger.info(f"Unregistered {removed} hook(s) for plugin '{plugin_name}'")
        return removed

    # -- execution --

    def execute(self, hook_point: str, context: HookContext) -> HookContext:
        """Run all hooks for *hook_point* in priority order.

        Returns the (potentially modified) context.
        If a hook sets ``context.stop_pipeline = True``, later hooks are skipped.
        """
        # Snapshot hook list under lock, then execute without holding lock
        with self._lock:
            hooks = list(self._hooks.get(hook_point, []))
        if not hooks:
            return context

        for hook in hooks:
            try:
                result = hook.function(context)
                # If hook returns a HookContext, use it
                if isinstance(result, HookContext):
                    context = result
            except Exception as e:
                logger.error(
                    f"Hook {hook_point} from '{hook.plugin_name}' raised: {e}",
                    exc_info=True,
                )
                continue  # Skip broken hooks, don't crash the app

            if context.stop_pipeline:
                context.stopped_by = hook.plugin_name
                logger.info(f"Pipeline stopped by '{hook.plugin_name}' at {hook_point}")
                break

        return context

    # -- introspection --

    def list_hooks(self, hook_point: str = None) -> List[Dict[str, Any]]:
        """List registered hooks (for debugging / API)."""
        result = []
        points = [hook_point] if hook_point else list(HOOK_POINTS)
        for hp in points:
            for h in self._hooks.get(hp, []):
                result.append({
                    "hook_point": hp,
                    "plugin": h.plugin_name,
                    "priority": h.priority,
                    "function": h.function.__name__,
                })
        return result

    def clear(self):
        """Remove all hooks."""
        for hp in HOOK_POINTS:
            self._hooks[hp] = []


# -- singleton --

_pipeline: Optional[HookPipeline] = None


def get_hook_pipeline() -> HookPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = HookPipeline()
    return _pipeline
