"""
Sessions Blueprint
Session persistence and management endpoints
"""

import json
import os
import hashlib
import logging
from flask import Blueprint, request

from .shared import json_response

logger = logging.getLogger(__name__)

sessions_bp = Blueprint('sessions', __name__)

# Session storage directory
SESSIONS_DIR = os.path.expanduser("~/.springo/sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)


def get_session_path(session_id: str) -> str:
    """Get file path for session"""
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


@sessions_bp.route('/v1/sessions', methods=['GET'])
def list_sessions():
    """List all sessions"""
    try:
        sessions = []
        for filename in os.listdir(SESSIONS_DIR):
            if filename.endswith('.json'):
                session_id = filename[:-5]
                filepath = os.path.join(SESSIONS_DIR, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    sessions.append({
                        "id": session_id,
                        "name": data.get("name", "Untitled"),
                        "working_directory": data.get("working_directory", ""),
                        "message_count": len(data.get("messages", [])),
                        "updated_at": os.path.getmtime(filepath)
                    })
                except:
                    pass

        sessions.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        return json_response({"sessions": sessions})

    except Exception as e:
        logger.error(f"List sessions error: {e}")
        return json_response({"error": str(e)}, status=500)


@sessions_bp.route('/v1/sessions/<session_id>', methods=['GET'])
def get_session(session_id: str):
    """Get a specific session"""
    try:
        filepath = get_session_path(session_id)
        if not os.path.exists(filepath):
            return json_response({"error": "Session not found"}, status=404)

        with open(filepath, 'r') as f:
            data = json.load(f)

        return json_response(data)

    except Exception as e:
        logger.error(f"Get session error: {e}")
        return json_response({"error": str(e)}, status=500)


@sessions_bp.route('/v1/sessions/<session_id>', methods=['POST'])
def save_session(session_id: str):
    """Save/update a session"""
    try:
        data = request.get_json()
        filepath = get_session_path(session_id)

        with open(filepath, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return json_response({"success": True, "id": session_id})

    except Exception as e:
        logger.error(f"Save session error: {e}")
        return json_response({"error": str(e)}, status=500)


@sessions_bp.route('/v1/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id: str):
    """Delete a session"""
    try:
        filepath = get_session_path(session_id)
        if os.path.exists(filepath):
            os.remove(filepath)
            return json_response({"success": True})
        else:
            return json_response({"error": "Session not found"}, status=404)

    except Exception as e:
        logger.error(f"Delete session error: {e}")
        return json_response({"error": str(e)}, status=500)


@sessions_bp.route('/v1/sessions/hash', methods=['POST'])
def get_session_hash():
    """Generate session hash from working directory"""
    try:
        data = request.get_json()
        working_dir = data.get('working_directory', '')

        if working_dir:
            hash_input = working_dir.encode('utf-8')
            session_hash = hashlib.sha256(hash_input).hexdigest()[:16]
        else:
            session_hash = "default"

        return json_response({"hash": session_hash, "working_directory": working_dir})

    except Exception as e:
        logger.error(f"Session hash error: {e}")
        return json_response({"error": str(e)}, status=500)
