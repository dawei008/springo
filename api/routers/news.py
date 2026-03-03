"""
News Router for FastAPI
新闻搜索端点 (News Agent 集成)
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from ..services.model_registry import MODEL_REGISTRY
import logging
import asyncio
import json
import os
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ Request/Response Models ============

class NewsSearchRequest(BaseModel):
    """新闻搜索请求"""
    query: str = Field(..., description="Search query")
    count: int = Field(default=10, description="Number of results", ge=1, le=50)
    freshness: str = Field(default="pw", description="Freshness filter: pd, pw, pm, py")
    language: str = Field(default="en", description="Language code")


class NewsArticle(BaseModel):
    """新闻文章"""
    title: str
    url: str
    description: str = ""
    published: Optional[str] = None
    source: Optional[str] = None


class NewsSearchResponse(BaseModel):
    """新闻搜索响应"""
    success: bool
    query: str
    articles: List[NewsArticle]
    total: int
    error: Optional[str] = None


# ============ News Cache ============

_news_cache: Dict[str, Any] = {
    'news': [],
    'topics': [],
    'timestamp': None,
    'task_id': None,
    'status': 'idle'  # idle, running, completed, error
}
_news_lock = asyncio.Lock()


NEWS_TASK_PROMPT = """You are a news curator assistant. Your task is to fetch PERSONALIZED news based on user's memory.

## Step 1: Get User Preferences from Memory (REQUIRED)

Use execute_command to retrieve user preferences directly (no skill activation needed):

```bash
python ~/.springo/skills/memory/scripts/memory.py get USER_PREFERENCE --limit 10
```

You can also search for user interests:
```bash
python ~/.springo/skills/memory/scripts/memory.py search '用户兴趣' --top-k 5
```

## Step 2: Extract Topics from Memory (IMPORTANT!)

The memory returns JSON with "categories" field containing user interests.
Example memory format:
```json
{
  "content": "{\\"preference\\":\\"...\\",\\"categories\\":[\\"AWS\\",\\"software development\\",\\"AI\\"]}",
  ...
}
```

**Extract topics from the "categories" arrays across all memory records.**

Common category patterns to look for:
- Technology: AWS, cloud computing, Kubernetes, DevOps
- AI/ML: machine learning, LLM, agents, AI development
- Programming: Python, JavaScript, system architecture
- Specific products: Bedrock, AgentCore, Anthropic, OpenAI

**PRIORITIZE memory-based topics over defaults!**
Only use default topics if memory is empty or has no clear categories.

## Step 3: Search for News

Search for news based on extracted topics (3-4 topics).

Use `web-search__brave_news_search` tool with:
- query: topic keyword (in Chinese if user prefers Chinese based on memory context)
- count: 5
- freshness: "pd"

## Step 4: Return Structured Results

Return ONLY a JSON object:

```json
{
    "language": "zh" or "en",
    "topics": ["topic1", "topic2", "topic3"],
    "news": [
        {
            "title": "新闻标题",
            "description": "简介",
            "url": "https://...",
            "source": "来源",
            "publishedAt": "时间",
            "topic": "相关主题"
        }
    ]
}
```

Return 8-12 news items.

Default topics ONLY if memory is empty:
- OpenAI/ChatGPT
- Anthropic/Claude
- AWS/云计算
- AI Agent

CRITICAL: Your FINAL response must be ONLY the JSON object, no other text.
5. All strings must be properly quoted"""


async def _execute_news_agent_task(model: str = None, custom_topics: str = None):
    """Execute the news fetch task using internal API."""
    import httpx

    try:
        prompt = NEWS_TASK_PROMPT
        if custom_topics:
            prompt += f"\n\n## IMPORTANT: User-Specified Topics\nThe user has explicitly requested news about: {custom_topics}\nThese topics have HIGHEST PRIORITY. Always include them in your search queries, in addition to any topics from memory."
            logger.info(f"News agent with custom topics: {custom_topics}")

        # Add user interests from saved preferences
        from ..services.interests import get_interests
        user_interests = get_interests()
        if user_interests:
            interest_str = ", ".join(user_interests)
            prompt += f"\n\n## User's Saved Interests (IMPORTANT)\nThe user has explicitly saved these interests: {interest_str}\nThese should be included as search topics alongside any topics from memory."
            logger.info(f"News agent with saved interests: {interest_str}")

        logger.info(f"News agent starting via internal API (model={model})...")

        request_body = {
            "max_tokens": 8192,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "stream": False
        }
        if model:
            request_body["model"] = model

        async with httpx.AsyncClient(timeout=600.0) as client:  # News agent may take long (memory + search)
            response = await client.post(
                "http://127.0.0.1:8081/v1/messages-auto",
                json=request_body,
                headers={
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                }
            )

        if response.status_code != 200:
            logger.error(f"News agent API error: {response.status_code} - {response.text[:500]}")
            return None

        result = response.json()

        # Extract text content
        raw_news_text = ""
        content = result.get('content', [])
        for block in content:
            if block.get('type') == 'text':
                raw_news_text = block.get('text', '')
                break

        if not raw_news_text:
            logger.warning("News agent returned no text content")
            return None

        logger.info(f"News agent Phase 1 complete, raw response length: {len(raw_news_text)}")

        # Phase 2: Use Structured Output to format the result
        return _format_news_with_structured_output(raw_news_text)

    except Exception as e:
        logger.error(f"News agent task error: {e}")
        return None


NEWS_OUTPUT_SCHEMA = {
    "name": "format_news_output",
    "description": "Format news search results into structured JSON",
    "input_schema": {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "enum": ["zh", "en"],
                "description": "Language of the news content"
            },
            "topics": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of topics searched"
            },
            "news": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "News title"},
                        "description": {"type": "string", "description": "Brief description"},
                        "url": {"type": "string", "description": "Article URL"},
                        "source": {"type": "string", "description": "News source"},
                        "publishedAt": {"type": "string", "description": "Publication time"},
                        "topic": {"type": "string", "description": "Related topic"}
                    },
                    "required": ["title", "url", "topic"]
                },
                "description": "List of news items"
            }
        },
        "required": ["language", "topics", "news"]
    }
}


def _format_news_with_structured_output(raw_text: str) -> Optional[Dict]:
    """Use Bedrock Structured Output to format news into JSON (Phase 2)."""
    try:
        import boto3
        from ..services.model_registry import get_model_info, get_bedrock_id

        bedrock_client = boto3.client('bedrock-runtime', region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-west-2'))

        # Look up model from registry
        from ..config import settings
        news_format_model = settings.news_format_model_id
        model_id = get_bedrock_id(news_format_model)
        news_info = get_model_info(news_format_model)
        news_api_format = news_info["api_format"] if news_info else "anthropic"

        request_body: Dict[str, Any] = {
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": f"""Extract and format the news items from the following text into structured JSON.

Raw news data:
{raw_text}

Use the format_news_output tool to return the structured result. Include all news items found."""
                }
            ],
            "tools": [NEWS_OUTPUT_SCHEMA],
            "tool_choice": {"type": "tool", "name": "format_news_output"}
        }
        if news_api_format == "anthropic":
            request_body["anthropic_version"] = "bedrock-2023-05-31"

        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=json.dumps(request_body),
            contentType="application/json",
            accept="application/json"
        )

        result = json.loads(response['body'].read())
        content = result.get('content', [])
        logger.info(f"Structured output response: stop_reason={result.get('stop_reason')}, blocks={len(content)}")

        for block in content:
            if block.get('type') == 'tool_use' and block.get('name') == 'format_news_output':
                news_data = block.get('input', {})
                if isinstance(news_data, str):
                    news_data = json.loads(news_data)
                news_items = news_data.get('news', [])
                for item in news_items:
                    if isinstance(item, dict) and 'id' not in item:
                        item['id'] = f"news_{uuid.uuid4().hex[:8]}"
                logger.info(f"Structured output: {len(news_items)} news items")
                return news_data

        logger.warning("No structured output found in response")
        return _parse_news_response(raw_text)

    except Exception as e:
        logger.error(f"Structured output formatting failed: {e}")
        return _parse_news_response(raw_text)


def _parse_news_response(text: str) -> Optional[Dict]:
    """Parse the news JSON response from Claude with robust fallbacks."""
    import re

    try:
        logger.info(f"News response to parse (first 300 chars): {text[:300]}...")

        # Look for JSON block in markdown code fence
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
            logger.info(f"Found JSON in code fence, length: {len(text)}")
        else:
            # Find outermost braces by counting depth
            json_start = text.find('{')
            if json_start != -1:
                depth = 0
                json_end = -1
                for i, c in enumerate(text[json_start:], json_start):
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            json_end = i
                            break
                if json_end != -1:
                    text = text[json_start:json_end + 1]
                    logger.info(f"Extracted JSON from {json_start} to {json_end}, length: {len(text)}")

        result = json.loads(text.strip())

        if 'news' in result and isinstance(result['news'], list):
            for item in result['news']:
                if 'id' not in item:
                    item['id'] = f"news_{uuid.uuid4().hex[:8]}"
            return result
        return None

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse news response as JSON: {e}")
        error_pos = getattr(e, 'pos', 0)
        if error_pos > 0:
            start = max(0, error_pos - 50)
            end = min(len(text), error_pos + 50)
            logger.warning(f"JSON error context: ...{text[start:end]}...")

        # Try to fix common JSON issues
        try:
            fixed_text = text
            fixed_text = re.sub(r',\s*([}\]])', r'\1', fixed_text)
            fixed_text = re.sub(r'//.*$', '', fixed_text, flags=re.MULTILINE)
            fixed_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', fixed_text)

            result = json.loads(fixed_text.strip())
            if 'news' in result and isinstance(result['news'], list):
                for item in result['news']:
                    if 'id' not in item:
                        item['id'] = f"news_{uuid.uuid4().hex[:8]}"
                logger.info(f"Successfully parsed fixed JSON with {len(result['news'])} items")
                return result
        except Exception as fix_error:
            logger.warning(f"JSON fix attempt also failed: {fix_error}")

        # Last resort: regex extraction of individual news items
        try:
            news_pattern = r'\{\s*"title"\s*:\s*"[^"]+"\s*,\s*"description"\s*:\s*"[^"]*"\s*,\s*"url"\s*:\s*"[^"]+"\s*,\s*"source"\s*:\s*"[^"]*"\s*,\s*"publishedAt"\s*:\s*"[^"]*"\s*,\s*"topic"\s*:\s*"[^"]*"\s*\}'
            matches = re.findall(news_pattern, text, re.DOTALL)
            if matches:
                news_items = []
                for m in matches:
                    try:
                        item = json.loads(m)
                        item['id'] = f"news_{uuid.uuid4().hex[:8]}"
                        news_items.append(item)
                    except Exception:
                        pass
                if news_items:
                    logger.info(f"Extracted {len(news_items)} news items via regex")
                    return {"news": news_items, "topics": [], "language": "zh"}
        except Exception as regex_error:
            logger.warning(f"Regex extraction also failed: {regex_error}")

        return None


async def _start_news_fetch_task(model: str = None, custom_topics: str = None) -> str:
    """Start background task to fetch news using Claude."""
    global _news_cache

    async with _news_lock:
        _news_cache['status'] = 'running'

    task_id = f"news_{uuid.uuid4().hex[:8]}"
    _news_cache['task_id'] = task_id

    async def run_task():
        global _news_cache
        try:
            result = await _execute_news_agent_task(model=model, custom_topics=custom_topics)

            async with _news_lock:
                if result:
                    news_items = result.get('news', [])
                    if isinstance(news_items, str):
                        try:
                            news_items = json.loads(news_items)
                        except Exception:
                            news_items = []
                    if not isinstance(news_items, list):
                        news_items = []

                    _news_cache['news'] = news_items
                    _news_cache['topics'] = result.get('topics', [])
                    _news_cache['timestamp'] = datetime.now()
                    _news_cache['status'] = 'completed'
                    logger.info(f"News fetch completed: {len(_news_cache['news'])} items")
                else:
                    _news_cache['status'] = 'error'
                    logger.warning("News fetch returned no results")

        except Exception as e:
            logger.error(f"News fetch task error: {e}")
            async with _news_lock:
                _news_cache['status'] = 'error'

    # Run in background
    asyncio.create_task(run_task())
    return task_id


# ============ Endpoints ============

@router.post("/news/search", response_model=NewsSearchResponse)
async def search_news(request: NewsSearchRequest):
    """搜索新闻"""
    try:
        try:
            from ..services.tool_manager import get_tool_manager

            tool_manager = await get_tool_manager()
            result = await tool_manager.execute_tool(
                "web-search__brave_news_search",
                {
                    "query": request.query,
                    "count": request.count,
                    "freshness": request.freshness,
                    "search_lang": request.language
                }
            )

            if "error" not in result:
                articles = []
                content = result.get("content", [])
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        try:
                            article_data = json.loads(item.get("text", "{}"))
                            articles.append(NewsArticle(
                                title=article_data.get("title", ""),
                                url=article_data.get("url", ""),
                                description=article_data.get("description", "")
                            ))
                        except Exception:
                            pass

                return NewsSearchResponse(
                    success=True,
                    query=request.query,
                    articles=articles,
                    total=len(articles)
                )
        except Exception as e:
            logger.warning(f"MCP news search failed: {e}")

        return NewsSearchResponse(
            success=False,
            query=request.query,
            articles=[],
            total=0,
            error="News search service not available"
        )

    except Exception as e:
        logger.error(f"News search error: {e}")
        return NewsSearchResponse(
            success=False,
            query=request.query,
            articles=[],
            total=0,
            error=str(e)
        )


@router.get("/news/search")
async def search_news_get(
    query: str = Query(..., description="Search query"),
    count: int = Query(10, description="Number of results", ge=1, le=50),
    freshness: str = Query("pw", description="Freshness filter")
):
    """搜索新闻 (GET 版本)"""
    request = NewsSearchRequest(query=query, count=count, freshness=freshness)
    return await search_news(request)


@router.get("/news/fetch")
async def fetch_news(
    force: Optional[str] = Query(None, description="Force refresh"),
    model: Optional[str] = Query(None, description="Model to use for news agent"),
    topics: Optional[str] = Query(None, description="Custom topics from user"),
    count: int = Query(10, description="Number of articles to fetch", ge=1, le=50)
) -> Dict[str, Any]:
    """
    获取个性化新闻

    Frontend expects: {success, status, news, topics, timestamp, cached}
    Uses Claude Agent to read LTM and search for personalized news.
    """
    global _news_cache

    # Validate model against registry if provided
    if model and model not in MODEL_REGISTRY:
        valid_models = sorted(MODEL_REGISTRY.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model: {model}. Valid models: {valid_models}"
        )

    force_refresh = force and force.lower() == 'true'

    async with _news_lock:
        # If a task is already running, return loading status
        if _news_cache['status'] == 'running':
            return {
                "success": True,
                "news": _news_cache.get('news', []),
                "topics": _news_cache.get('topics', []),
                "status": "loading",
                "message": "News is being fetched..."
            }

        # Check cached results (5 minutes)
        if not force_refresh and _news_cache['timestamp']:
            age = (datetime.now() - _news_cache['timestamp']).total_seconds()
            if age < 300 and _news_cache['news']:
                logger.info(f"Returning cached news ({len(_news_cache['news'])} items, {age:.0f}s old)")
                return {
                    "success": True,
                    "news": _news_cache['news'],
                    "topics": _news_cache['topics'],
                    "timestamp": _news_cache['timestamp'].isoformat(),
                    "cached": True
                }

    # Start background task
    try:
        task_id = await _start_news_fetch_task(model=model, custom_topics=topics)
        return {
            "success": True,
            "news": _news_cache.get('news', []),
            "topics": _news_cache.get('topics', []),
            "status": "loading",
            "task_id": task_id,
            "message": "Fetching personalized news..."
        }
    except Exception as e:
        logger.error(f"Failed to start news fetch task: {e}")
        return {
            "success": False,
            "error": str(e),
            "news": [],
            "topics": []
        }


# ============ Interest Endpoints ============

@router.get("/news/interests")
async def get_interests_endpoint():
    """Get user interests."""
    from ..services.interests import get_interests
    interests = get_interests()
    return {"success": True, "interests": interests}


@router.post("/news/interests")
async def add_interests_endpoint(body: dict):
    """Add user interests."""
    from ..services.interests import add_interests
    new_interests = body.get("interests", [])
    if not new_interests:
        raise HTTPException(status_code=400, detail="No interests provided")
    interests = add_interests(new_interests)
    return {"success": True, "interests": interests}


@router.delete("/news/interests/{interest}")
async def remove_interest_endpoint(interest: str):
    """Remove a user interest."""
    from ..services.interests import remove_interest
    interests = remove_interest(interest)
    return {"success": True, "interests": interests}
