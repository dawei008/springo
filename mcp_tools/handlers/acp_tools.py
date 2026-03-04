"""
ACP Tool Handlers
Exposes ACP agents to Springo's LLM as callable tools.
"""

import asyncio
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _run_async(coro, timeout: float = 660):
    """Run an async coroutine from a sync context (ThreadPoolExecutor).

    Args:
        timeout: Max seconds to wait. Should exceed the ACP prompt timeout (600s)
                 to avoid cutting off in-progress ACP calls.
    """
    try:
        asyncio.get_running_loop()
        # Already in an async context — schedule in a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=timeout)
    except RuntimeError:
        # No running loop — safe to use asyncio.run
        return asyncio.run(coro)


def acp_prompt(agent: str, prompt: str, cwd: str = "/tmp", timeout: float = 300) -> Dict[str, Any]:
    """Delegate a task to an ACP agent and return the result.

    Args:
        agent: Name of the ACP agent (e.g., "kiro", "gemini")
        prompt: The task/prompt to send to the agent
        cwd: Working directory for the agent session
        timeout: Max seconds to wait for response
    """
    try:
        from api.services.acp_client import get_acp_client_manager
        manager = get_acp_client_manager()

        async def _do_prompt():
            return await manager.prompt_agent(agent, prompt, cwd=cwd, timeout=timeout)

        result = _run_async(_do_prompt())

        if not result:
            return {"error": "No response from agent"}

        if "error" in result:
            return {"error": result["error"]}

        return {
            "agent": agent,
            "text": result.get("text", ""),
            "stop_reason": result.get("stop_reason", "unknown"),
        }
    except Exception as e:
        logger.error(f"acp_prompt failed: {e}")
        return {"error": f"ACP prompt failed: {e}"}


def acp_list_agents() -> Dict[str, Any]:
    """List all configured ACP agents and their status."""
    try:
        from api.services.acp_client import get_acp_client_manager
        manager = get_acp_client_manager()
        agents = manager.get_all_agents()
        return {
            "agents": agents,
            "total": len(agents),
            "running": sum(1 for a in agents if a.get("running")),
        }
    except Exception as e:
        logger.error(f"acp_list_agents failed: {e}")
        return {"error": f"Failed to list ACP agents: {e}"}


def acp_new_session(agent: str, cwd: str = "/tmp") -> Dict[str, Any]:
    """Pre-warm a session on an ACP agent (optional, for faster subsequent prompts).

    Args:
        agent: Name of the ACP agent
        cwd: Working directory for the session
    """
    try:
        from api.services.acp_client import get_acp_client_manager
        manager = get_acp_client_manager()

        async def _do_session():
            if not await manager.ensure_agent_started(agent):
                return {"error": f"Failed to start agent: {agent}"}
            agent_conn = manager.agents[agent]
            session_id = await agent_conn.session_new(cwd=cwd)
            if session_id:
                return {"agent": agent, "session_id": session_id}
            return {"error": "Failed to create session"}

        result = _run_async(_do_session())
        return result
    except Exception as e:
        logger.error(f"acp_new_session failed: {e}")
        return {"error": f"ACP new session failed: {e}"}
