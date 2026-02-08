"""
User Interests Management
用户关注点管理 - 从聊天消息中提取并持久化
"""
import json
import os
import logging
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

INTERESTS_FILE = os.path.expanduser("~/.springo/interests.json")


def _load_interests() -> Dict[str, Any]:
    """Load interests from file."""
    try:
        if os.path.exists(INTERESTS_FILE):
            with open(INTERESTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load interests: {e}")
    return {"interests": [], "updated_at": None}


def _save_interests(data: Dict[str, Any]):
    """Save interests to file."""
    try:
        os.makedirs(os.path.dirname(INTERESTS_FILE), exist_ok=True)
        data["updated_at"] = datetime.now().isoformat()
        with open(INTERESTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save interests: {e}")


def get_interests() -> List[str]:
    """Get current user interests."""
    data = _load_interests()
    return data.get("interests", [])


def add_interests(new_interests: List[str]) -> List[str]:
    """Add new interests, deduplicating."""
    data = _load_interests()
    current = data.get("interests", [])

    # Normalize and deduplicate
    current_lower = {i.lower() for i in current}
    for interest in new_interests:
        interest = interest.strip()
        if interest and interest.lower() not in current_lower:
            current.append(interest)
            current_lower.add(interest.lower())

    # Keep max 20 interests
    data["interests"] = current[-20:]
    _save_interests(data)
    return data["interests"]


def remove_interest(interest: str) -> List[str]:
    """Remove an interest."""
    data = _load_interests()
    current = data.get("interests", [])
    data["interests"] = [i for i in current if i.lower() != interest.lower()]
    _save_interests(data)
    return data["interests"]


def set_interests(interests: List[str]) -> List[str]:
    """Replace all interests."""
    data = _load_interests()
    data["interests"] = [i.strip() for i in interests if i.strip()][-20:]
    _save_interests(data)
    return data["interests"]


# Interest detection patterns from chat messages
INTEREST_PATTERNS = [
    "我关注", "我想关注", "关注一下", "我对", "感兴趣",
    "i'm interested in", "i am interested in", "i follow",
    "i want to follow", "interested in", "keep me updated on",
    "track news about", "我想了解", "帮我关注",
]

def extract_interests_from_message(message: str) -> List[str]:
    """Extract interest topics from a user chat message.

    Detects patterns like:
    - "我关注AWS和AI" -> ["AWS", "AI"]
    - "I'm interested in Kubernetes" -> ["Kubernetes"]
    """
    msg_lower = message.lower()

    for pattern in INTEREST_PATTERNS:
        if pattern.lower() in msg_lower:
            # Extract what comes after the pattern
            idx = msg_lower.index(pattern.lower()) + len(pattern)
            rest = message[idx:].strip()

            # Remove common connectors
            for prefix in ["了", "的", "相关", "方面", "内容", "新闻", "动态", "：", ":", " in ", " about "]:
                if rest.lower().startswith(prefix.lower()):
                    rest = rest[len(prefix):].strip()

            if not rest:
                continue

            # Split by common delimiters
            import re
            topics = re.split(r'[,，、;；和与及and&\s]+', rest)
            topics = [t.strip().strip('。.!！?？') for t in topics if t.strip() and len(t.strip()) > 1]

            if topics:
                return topics

    return []
