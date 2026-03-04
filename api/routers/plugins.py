"""
Plugin management API endpoints.
"""
from fastapi import APIRouter, HTTPException
from typing import Any, Dict

router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.get("/list")
async def list_plugins() -> Dict[str, Any]:
    """List all loaded plugins."""
    from ..services.plugin_system import get_plugin_manager
    mgr = get_plugin_manager()
    plugins = mgr.list_plugins()
    return {"plugins": plugins, "count": len(plugins)}


@router.get("/path")
async def get_plugins_path() -> Dict[str, Any]:
    """Return the plugins directory path."""
    from ..services.plugin_system import get_plugin_manager
    mgr = get_plugin_manager()
    return {"path": str(mgr.plugins_dir)}


@router.get("/{plugin_name}")
async def get_plugin(plugin_name: str) -> Dict[str, Any]:
    """Get details of a specific plugin."""
    from ..services.plugin_system import get_plugin_manager
    mgr = get_plugin_manager()
    plugin = mgr.get_plugin(plugin_name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_name}")
    return plugin.to_dict()


@router.post("/reload")
async def reload_plugins() -> Dict[str, Any]:
    """Reload all plugins from disk."""
    from ..services.plugin_system import get_plugin_manager
    mgr = get_plugin_manager()
    count = mgr.reload()
    return {"status": "reloaded", "count": count}


@router.get("/hooks/list")
async def list_hooks() -> Dict[str, Any]:
    """List all registered hooks."""
    from ..services.plugin_system import get_hook_pipeline
    pipeline = get_hook_pipeline()
    hooks = pipeline.list_hooks()
    return {"hooks": hooks, "count": len(hooks)}


@router.get("/agents/list")
async def list_agent_templates() -> Dict[str, Any]:
    """List all available agent templates."""
    from ..services.plugin_system import get_agent_template_manager
    mgr = get_agent_template_manager()
    templates = mgr.list_templates()
    return {"templates": templates, "count": len(templates)}


@router.get("/agents/{template_name}")
async def get_agent_template(template_name: str) -> Dict[str, Any]:
    """Get details of an agent template."""
    from ..services.plugin_system import get_agent_template_manager
    mgr = get_agent_template_manager()
    tmpl = mgr.get_template(template_name)
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"Agent template not found: {template_name}")
    return tmpl.to_dict()
