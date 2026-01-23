"""
API Blueprints
Flask Blueprint organization for API routes
"""

from flask import Flask

from .messages import messages_bp
from .context import context_bp
from .sessions import sessions_bp
from .tools import tools_bp
from .skills import skills_bp
from .mcp import mcp_bp
from .system import system_bp


def register_blueprints(app: Flask):
    """Register all API blueprints with the Flask app"""
    app.register_blueprint(messages_bp)
    app.register_blueprint(context_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(tools_bp)
    app.register_blueprint(skills_bp)
    app.register_blueprint(mcp_bp)
    app.register_blueprint(system_bp)


__all__ = [
    'register_blueprints',
    'messages_bp',
    'context_bp',
    'sessions_bp',
    'tools_bp',
    'skills_bp',
    'mcp_bp',
    'system_bp',
]
