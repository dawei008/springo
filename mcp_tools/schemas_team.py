"""
Team Communication Tool Schemas
JSON schemas for collaborative team tools (send_message, task_create, etc.)
Only injected into tool list when an agent is in team context.
"""

TEAM_TOOL_DEFINITIONS = [
    {
        "name": "ask_user",
        "description": (
            "Ask the user a question when you need clarification or input.\n\n"
            "For the team lead: sends the question directly to the user via the UI.\n"
            "For workers: routes the question through the team lead, who relays it "
            "to the user and forwards the answer back.\n\n"
            "After calling ask_user, wait for the reply before proceeding."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user",
                },
                "options": {
                    "type": "array",
                    "description": "Optional list of choices to present",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "Option label"},
                            "description": {"type": "string", "description": "Option description"},
                        },
                        "required": ["label"],
                    },
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "send_message",
        "description": (
            "Send a message to a specific teammate or broadcast to the entire team.\n\n"
            "Message types:\n"
            "- 'message': Send a direct message to a specific recipient\n"
            "- 'broadcast': Send to all teammates (use sparingly)\n"
            "- 'shutdown_request': Request a teammate to shut down gracefully\n"
            "- 'shutdown_response': Respond to a shutdown request (approve or reject)\n"
            "- 'plan_approval_response': Approve or reject a worker's plan\n\n"
            "For shutdown_response: set approve=true to accept shutdown, false to reject.\n"
            "For plan_approval_response: set approve=true to approve the plan, false to reject "
            "(include feedback in content).\n\n"
            "Always include a short summary (5-10 words) for UI preview."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["message", "broadcast", "shutdown_request", "shutdown_response", "plan_approval_response"],
                    "description": (
                        "Message type:\n"
                        "- 'message': Direct message to a specific recipient\n"
                        "- 'broadcast': Send to all teammates (use sparingly)\n"
                        "- 'shutdown_request': Request a teammate to shut down\n"
                        "- 'shutdown_response': Respond to a shutdown request (set approve=true/false)\n"
                        "- 'plan_approval_response': Approve or reject a worker's plan (set approve=true/false)"
                    ),
                },
                "recipient": {
                    "type": "string",
                    "description": "Agent name of the recipient (required for 'message', 'shutdown_request', 'plan_approval_response')",
                },
                "content": {
                    "type": "string",
                    "description": "The message content",
                },
                "summary": {
                    "type": "string",
                    "description": "A 5-10 word summary shown as preview in the UI",
                },
                "approve": {
                    "type": "boolean",
                    "description": "Whether to approve the request (required for 'shutdown_response' and 'plan_approval_response')",
                },
                "request_id": {
                    "type": "string",
                    "description": "The request ID to respond to (required for 'shutdown_response')",
                },
            },
            "required": ["type", "content"],
        },
    },
    {
        "name": "task_create",
        "description": (
            "Create a new task on the shared team task board.\n\n"
            "Tasks help coordinate work between agents. Each task has:\n"
            "- subject: A brief actionable title (imperative form)\n"
            "- description: Detailed description of what needs to be done\n"
            "- active_form: Present continuous form shown while task is in progress (e.g., 'Running tests')\n\n"
            "New tasks start with status 'pending'. Use task_update to set owner and change status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Brief task title in imperative form (e.g., 'Fix authentication bug')",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of what needs to be done",
                },
                "active_form": {
                    "type": "string",
                    "description": "Present continuous form shown in spinner (e.g., 'Fixing authentication bug')",
                },
            },
            "required": ["subject", "description"],
        },
    },
    {
        "name": "task_update",
        "description": (
            "Update an existing task on the shared team task board.\n\n"
            "Common operations:\n"
            "- Mark task in_progress: set status='in_progress'\n"
            "- Mark task completed: set status='completed' (auto-resolves dependencies)\n"
            "- Assign task: set owner to agent name\n"
            "- Set dependencies: use add_blocked_by to specify prerequisite tasks\n\n"
            "When a task is completed, any tasks it blocks that become fully unblocked "
            "will be automatically notified."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the task to update",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "error"],
                    "description": "New task status",
                },
                "subject": {
                    "type": "string",
                    "description": "Updated task title",
                },
                "description": {
                    "type": "string",
                    "description": "Updated task description",
                },
                "active_form": {
                    "type": "string",
                    "description": "Updated present continuous form",
                },
                "owner": {
                    "type": "string",
                    "description": "Agent name to assign the task to",
                },
                "add_blocks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs that cannot start until this one completes",
                },
                "add_blocked_by": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs that must complete before this one can start",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "task_list",
        "description": (
            "List all tasks on the shared team task board.\n\n"
            "Returns a summary of each task including id, subject, status, owner, and blockedBy.\n"
            "Use this to see what tasks are available, check progress, or find unblocked work."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "task_get",
        "description": (
            "Get full details of a specific task from the shared team task board.\n\n"
            "Returns the complete task including description, dependencies, and status.\n"
            "Use this before starting work on a task to understand full requirements."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the task to retrieve",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "spawn_worker",
        "description": (
            "Spawn a new worker agent to work on one or more tasks.\n\n"
            "Each worker runs autonomously with full tool access (file read/write, "
            "command execution, web search, etc.). Workers report back via "
            "send_message when they complete their tasks.\n\n"
            "Provide a worker name and the task ID(s) to assign. The worker will "
            "be created, assigned the tasks, and begin working immediately.\n\n"
            "Tips:\n"
            "- Use descriptive names like 'researcher', 'implementer', 'reviewer'\n"
            "- Each worker can handle one or more related tasks\n"
            "- Workers work in parallel — spawn multiple for independent tasks"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name for the worker agent (e.g., 'researcher', 'implementer-1')",
                },
                "task_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs to assign to this worker",
                },
                "plan_mode": {
                    "type": "boolean",
                    "description": (
                        "If true, the worker must create and submit an implementation plan "
                        "via exit_plan_mode before executing. The team lead reviews and "
                        "approves the plan before the worker proceeds. Default: false."
                    ),
                },
            },
            "required": ["name", "task_ids"],
        },
    },
    {
        "name": "exit_plan_mode",
        "description": (
            "Submit your implementation plan for team lead approval.\n\n"
            "When spawned in plan mode, you must:\n"
            "1. Analyze the task requirements\n"
            "2. Create a detailed implementation plan\n"
            "3. Call this tool with the plan\n"
            "4. Wait for the team lead's approval before implementing\n\n"
            "The team lead will review your plan and either approve it "
            "(allowing you to proceed) or reject it with feedback."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plan": {
                    "type": "string",
                    "description": "The detailed implementation plan to submit for approval",
                },
            },
            "required": ["plan"],
        },
    },
    {
        "name": "team_info",
        "description": (
            "Get information about the current team, including all members and their status.\n\n"
            "Returns team ID, status, user request, and a list of all team members "
            "with their name, agent_id, role, status, and purpose."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]
