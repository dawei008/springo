"""
Springo Agent Team Manager
多 Agent 团队协作服务 - 任务分解、并行执行、结果合成
"""
import json
import uuid
import logging
import asyncio
from typing import AsyncGenerator, Dict, Any, Optional, List
from datetime import datetime

from ..models.teams import (
    Team, TeamAgent, TaskBoardItem, AgentRole,
    TeamSpawnRequest, ROLE_CONFIGS,
)
from .bedrock import get_bedrock_service, BedrockService
from ..utils.streaming import SSEEventBuilder

logger = logging.getLogger(__name__)


class AgentTeamManager:
    """Agent 团队管理器 - 协调多个 Agent 并行工作"""

    def __init__(self, bedrock: BedrockService = None):
        self.bedrock = bedrock or get_bedrock_service()
        self._teams: Dict[str, Team] = {}

    def get_team(self, team_id: str) -> Optional[Team]:
        return self._teams.get(team_id)

    def spawn_team(self, request: TeamSpawnRequest) -> Team:
        """Create a new team based on the user request"""
        team = Team(
            user_request=request.user_request,
            shared_context=request.context or "",
        )

        # Always add an orchestrator
        orchestrator_role = ROLE_CONFIGS["orchestrator"].model_copy()
        orchestrator_role.model = request.model
        team.agents.append(TeamAgent(role=orchestrator_role))

        self._teams[team.team_id] = team
        logger.info(f"Team spawned: {team.team_id} for request: {request.user_request[:80]}")
        return team

    async def execute_team(
        self,
        team_id: str,
        max_parallel: int = 3
    ) -> AsyncGenerator[str, None]:
        """
        Execute the team workflow via SSE streaming:
        1. Orchestrator decomposes the task
        2. Spawn worker agents and execute in parallel
        3. Orchestrator synthesizes results
        """
        team = self._teams.get(team_id)
        if not team:
            yield SSEEventBuilder.team_error(team_id, "Team not found")
            yield SSEEventBuilder.done()
            return

        try:
            # === Phase 1: Emit team spawned ===
            agent_info = [
                {"agent_id": a.agent_id, "role": a.role.name, "purpose": a.role.purpose}
                for a in team.agents
            ]
            yield SSEEventBuilder.team_spawned(team.team_id, agent_info, team.user_request)

            # === Phase 2: Orchestrator decomposes the task ===
            team.status = "planning"
            yield SSEEventBuilder.team_planning(team.team_id)

            orchestrator = team.agents[0]
            orchestrator.status = "thinking"

            subtasks = await self._decompose_task(orchestrator, team.user_request, team.shared_context)

            if not subtasks:
                yield SSEEventBuilder.team_error(team.team_id, "Orchestrator failed to decompose task")
                yield SSEEventBuilder.done()
                return

            # Create task board
            for st in subtasks:
                task_item = TaskBoardItem(
                    title=st.get("title", "Untitled"),
                    description=st.get("description", ""),
                )
                team.task_board.append(task_item)

            # Spawn worker agents for each subtask
            for i, st in enumerate(subtasks):
                role_name = st.get("role", "explorer")
                role_config = ROLE_CONFIGS.get(role_name, ROLE_CONFIGS["explorer"]).model_copy()
                agent = TeamAgent(role=role_config, assigned_task=team.task_board[i].task_id)
                team.agents.append(agent)
                team.task_board[i].assigned_to = agent.agent_id

            orchestrator.status = "complete"

            # Emit task board
            task_board_data = [
                {
                    "task_id": t.task_id,
                    "title": t.title,
                    "description": t.description,
                    "assigned_to": t.assigned_to,
                    "role": next(
                        (a.role.name for a in team.agents if a.agent_id == t.assigned_to),
                        "unknown"
                    ),
                    "status": t.status,
                }
                for t in team.task_board
            ]
            yield SSEEventBuilder.team_task_board(team.team_id, task_board_data)

            # === Phase 3: Execute worker agents in parallel ===
            team.status = "executing"
            worker_agents = [a for a in team.agents if a.role.name != "orchestrator"]

            # Run agents in batches of max_parallel
            for batch_start in range(0, len(worker_agents), max_parallel):
                batch = worker_agents[batch_start:batch_start + max_parallel]

                # Emit start events for this batch
                for agent in batch:
                    task_item = next(
                        (t for t in team.task_board if t.assigned_to == agent.agent_id),
                        None
                    )
                    task_title = task_item.title if task_item else "Unknown"
                    yield SSEEventBuilder.team_agent_start(
                        team.team_id, agent.agent_id, agent.role.name, task_title
                    )

                # Execute batch in parallel
                tasks = []
                for agent in batch:
                    task_item = next(
                        (t for t in team.task_board if t.assigned_to == agent.agent_id),
                        None
                    )
                    tasks.append(self._execute_agent(
                        team, agent, task_item, team.user_request, team.shared_context
                    ))

                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Emit results for this batch
                for agent, result in zip(batch, results):
                    task_item = next(
                        (t for t in team.task_board if t.assigned_to == agent.agent_id),
                        None
                    )
                    task_title = task_item.title if task_item else "Unknown"

                    if isinstance(result, Exception):
                        agent.status = "error"
                        agent.findings = f"Error: {str(result)}"
                        if task_item:
                            task_item.status = "error"
                            task_item.findings = agent.findings
                        yield SSEEventBuilder.team_agent_error(
                            team.team_id, agent.agent_id, agent.role.name, str(result)
                        )
                    else:
                        agent.status = "complete"
                        agent.findings = result.get("findings", "")
                        agent.token_usage = result.get("tokens", {"input_tokens": 0, "output_tokens": 0})
                        if task_item:
                            task_item.status = "complete"
                            task_item.findings = agent.findings
                        yield SSEEventBuilder.team_agent_complete(
                            team.team_id, agent.agent_id, agent.role.name,
                            task_title, agent.findings, agent.token_usage
                        )

            # === Phase 4: Orchestrator synthesizes results ===
            team.status = "synthesizing"
            yield SSEEventBuilder.team_synthesizing(team.team_id)

            final_result = await self._synthesize_results(orchestrator, team)

            team.status = "complete"
            team.final_result = final_result
            team.completed_at = datetime.now().isoformat()

            # Calculate total tokens
            for agent in team.agents:
                team.total_tokens["input_tokens"] += agent.token_usage.get("input_tokens", 0)
                team.total_tokens["output_tokens"] += agent.token_usage.get("output_tokens", 0)

            yield SSEEventBuilder.team_complete(
                team.team_id, final_result, team.total_tokens
            )
            yield SSEEventBuilder.done()

        except Exception as e:
            logger.error(f"Team execution error: {e}", exc_info=True)
            team.status = "error"
            yield SSEEventBuilder.team_error(team.team_id, str(e))
            yield SSEEventBuilder.done()

    async def _decompose_task(
        self, orchestrator: TeamAgent, user_request: str, context: str
    ) -> List[Dict[str, Any]]:
        """Use orchestrator to decompose a request into subtasks"""
        messages = [
            {
                "role": "user",
                "content": (
                    f"Decompose the following user request into 2-4 specific subtasks.\n"
                    f"Each subtask should have a title, description, and the best role to handle it.\n"
                    f"Available roles: explorer, researcher, implementer, reviewer\n\n"
                    f"User request: {user_request}\n"
                    f"{'Additional context: ' + context if context else ''}\n\n"
                    f"Respond with ONLY a JSON array of subtasks, no other text:\n"
                    f'[{{"title": "...", "description": "...", "role": "explorer|researcher|implementer|reviewer"}}]'
                ),
            }
        ]

        model_id = self.bedrock.get_bedrock_model_id(orchestrator.role.model)
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "system": orchestrator.role.system_prompt,
            "messages": messages,
        }

        try:
            response = await self.bedrock.invoke_model(model_id, body)
            content = response.get("content", [])
            text = ""
            for block in content:
                if block.get("type") == "text":
                    text += block.get("text", "")

            orchestrator.token_usage = {
                "input_tokens": response.get("usage", {}).get("input_tokens", 0),
                "output_tokens": response.get("usage", {}).get("output_tokens", 0),
            }

            # Parse JSON from response - try to extract JSON array
            text = text.strip()
            if text.startswith("```"):
                # Strip markdown code fences
                lines = text.split("\n")
                text = "\n".join(
                    line for line in lines
                    if not line.strip().startswith("```")
                )
                text = text.strip()

            # Find JSON array in text
            start = text.find("[")
            end = text.rfind("]")
            if start >= 0 and end > start:
                text = text[start:end + 1]

            subtasks = json.loads(text)
            if not isinstance(subtasks, list):
                subtasks = [subtasks]

            logger.info(f"Orchestrator decomposed into {len(subtasks)} subtasks")
            return subtasks

        except Exception as e:
            logger.error(f"Task decomposition failed: {e}")
            return []

    async def _execute_agent(
        self,
        team: Team,
        agent: TeamAgent,
        task_item: Optional[TaskBoardItem],
        user_request: str,
        shared_context: str,
    ) -> Dict[str, Any]:
        """Execute a single agent's task"""
        agent.status = "thinking"
        agent.started_at = datetime.now().isoformat()

        if task_item:
            task_item.status = "in_progress"

        task_desc = task_item.description if task_item else user_request
        task_title = task_item.title if task_item else "General task"

        # Gather findings from other completed agents as context
        other_findings = []
        for other in team.agents:
            if other.agent_id != agent.agent_id and other.findings:
                other_findings.append(f"[{other.role.name}] {other.findings[:500]}")

        messages = [
            {
                "role": "user",
                "content": (
                    f"You are working as part of a team to address this request:\n"
                    f"Original request: {user_request}\n\n"
                    f"Your specific task: {task_title}\n"
                    f"Details: {task_desc}\n"
                    f"{'Shared context: ' + shared_context if shared_context else ''}\n"
                    f"{'Other agents findings: ' + chr(10).join(other_findings) if other_findings else ''}\n\n"
                    f"Provide your findings concisely. Focus on your assigned task."
                ),
            }
        ]

        model_id = self.bedrock.get_bedrock_model_id(agent.role.model)
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "system": agent.role.system_prompt,
            "messages": messages,
        }

        try:
            agent.status = "executing"
            response = await self.bedrock.invoke_model(model_id, body)
            content = response.get("content", [])
            text = ""
            for block in content:
                if block.get("type") == "text":
                    text += block.get("text", "")

            agent.completed_at = datetime.now().isoformat()
            tokens = {
                "input_tokens": response.get("usage", {}).get("input_tokens", 0),
                "output_tokens": response.get("usage", {}).get("output_tokens", 0),
            }

            return {"findings": text, "tokens": tokens}

        except Exception as e:
            agent.completed_at = datetime.now().isoformat()
            raise

    async def _synthesize_results(self, orchestrator: TeamAgent, team: Team) -> str:
        """Orchestrator synthesizes all agent findings into final result"""
        findings_text = ""
        for agent in team.agents:
            if agent.role.name != "orchestrator" and agent.findings:
                task_item = next(
                    (t for t in team.task_board if t.assigned_to == agent.agent_id),
                    None
                )
                task_title = task_item.title if task_item else "General"
                findings_text += f"\n### [{agent.role.name}] {task_title}\n{agent.findings}\n"

        messages = [
            {
                "role": "user",
                "content": (
                    f"You are the orchestrator. Synthesize the following agent findings into "
                    f"a clear, comprehensive response to the user's original request.\n\n"
                    f"Original request: {team.user_request}\n\n"
                    f"Agent findings:\n{findings_text}\n\n"
                    f"Provide a well-organized synthesis. Do not simply concatenate the findings. "
                    f"Create a coherent response that addresses the user's request completely."
                ),
            }
        ]

        model_id = self.bedrock.get_bedrock_model_id(orchestrator.role.model)
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 8192,
            "system": orchestrator.role.system_prompt,
            "messages": messages,
        }

        try:
            response = await self.bedrock.invoke_model(model_id, body)
            content = response.get("content", [])
            text = ""
            for block in content:
                if block.get("type") == "text":
                    text += block.get("text", "")

            # Update orchestrator token usage (add synthesis tokens)
            usage = response.get("usage", {})
            orchestrator.token_usage["input_tokens"] += usage.get("input_tokens", 0)
            orchestrator.token_usage["output_tokens"] += usage.get("output_tokens", 0)

            return text

        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            # Fallback: concatenate findings
            return f"[Synthesis failed: {e}]\n\nRaw findings:\n{findings_text}"


# Singleton
_team_manager: Optional[AgentTeamManager] = None


def get_team_manager() -> AgentTeamManager:
    global _team_manager
    if _team_manager is None:
        _team_manager = AgentTeamManager()
    return _team_manager
