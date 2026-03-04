"""
Springo Plugin System

Provides hooks, plugin packaging, and agent templates for extensibility.
"""
from .hook_pipeline import HookPipeline, HookContext, get_hook_pipeline
from .plugin_manager import PluginManager, get_plugin_manager
from .agent_templates import AgentTemplateManager, AgentTemplate, get_agent_template_manager

__all__ = [
    "HookPipeline", "HookContext", "get_hook_pipeline",
    "PluginManager", "get_plugin_manager",
    "AgentTemplateManager", "AgentTemplate", "get_agent_template_manager",
]
