"""
Images Router for FastAPI
图片处理端点 - Flask 兼容版

图片存储位置: ~/.springo/sessions/{session_id}/images/{image_id}.{ext}
"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import logging
import base64
import json
import os
import uuid

from ..services.session_store import get_session_store

logger = logging.getLogger(__name__)

router = APIRouter()

# Media type mappings (aligned with Flask)
MEDIA_TYPE_TO_EXT = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/gif': 'gif',
    'image/webp': 'webp'
}
EXT_TO_MEDIA_TYPE = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'gif': 'image/gif',
    'webp': 'image/webp'
}


# ============ Request/Response Models ============

class ImageUploadRequest(BaseModel):
    """图片上传请求 (base64 JSON, Flask 兼容)"""
    session_id: str = Field(..., description="Session ID")
    image_data: str = Field(..., description="Base64 encoded image data")
    media_type: str = Field(default="image/png", description="Image media type")
    filename: str = Field(default="", description="Original filename")


class ImageGenerateRequest(BaseModel):
    """图片生成请求"""
    prompt: str = Field(..., description="Image generation prompt")
    model: str = Field(default="stability.stable-diffusion-xl-v1", description="Model ID")
    width: int = Field(default=1024, description="Image width")
    height: int = Field(default=1024, description="Image height")
    steps: int = Field(default=50, description="Generation steps")


class ImageSearchRequest(BaseModel):
    """图片搜索请求"""
    query: str = Field(..., description="Search query")
    count: int = Field(default=10, description="Number of results", ge=1, le=50)


class ImageSearchResponse(BaseModel):
    """图片搜索响应"""
    success: bool
    query: str
    images: List[Dict[str, Any]]
    total: int
    error: Optional[str] = None


# ============ Endpoints ============

# NOTE: GET /images/search must be declared BEFORE GET /images/{session_id}/{image_filename}
# to avoid "search" being matched as a session_id path parameter.

@router.get("/images/search")
async def search_images_get(
    query: str = Query(..., description="Search query"),
    count: int = Query(10, description="Number of results", ge=1, le=50)
):
    """搜索图片 (GET 版本)"""
    req = ImageSearchRequest(query=query, count=count)
    return await search_images(req)


@router.post("/images/upload")
async def upload_image(request: Request):
    """
    上传图片并存储为文件 (Flask 兼容)

    接受 JSON body: {session_id, image_data (base64), media_type, filename}
    存储位置: ~/.springo/sessions/{session_id}/images/{image_id}.{ext}
    """
    try:
        data = await request.json()
        session_id = data.get('session_id')
        image_data = data.get('image_data')  # base64 encoded
        media_type = data.get('media_type', 'image/png')
        filename = data.get('filename', '')

        if not session_id or not image_data:
            return JSONResponse(
                status_code=400,
                content={"error": "session_id and image_data required"}
            )

        # Determine file extension from media type
        ext = MEDIA_TYPE_TO_EXT.get(media_type, 'png')

        # Generate unique image ID
        image_id = f"img_{uuid.uuid4().hex[:12]}"

        # Create images directory for this session
        store = get_session_store()
        session_dir = store.get_session_dir(session_id)
        images_dir = os.path.join(session_dir, "images")
        os.makedirs(images_dir, exist_ok=True)

        # Save image file
        image_path = os.path.join(images_dir, f"{image_id}.{ext}")
        with open(image_path, 'wb') as f:
            f.write(base64.b64decode(image_data))

        file_size = os.path.getsize(image_path)
        logger.info(f"Image saved: {image_id}.{ext} ({file_size:,} bytes) for session {session_id}")

        return {
            "image_id": image_id,
            "filename": f"{image_id}.{ext}",
            "media_type": media_type,
            "size": file_size,
            "relative_path": f"images/{image_id}.{ext}"
        }

    except Exception as e:
        logger.error(f"Image upload error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@router.get("/images/{session_id}/{image_filename}")
async def get_session_image(
    session_id: str,
    image_filename: str,
    format: Optional[str] = Query(None, description="Response format: 'base64' for JSON, else binary")
):
    """
    获取存储的图片文件 (Flask 兼容)

    支持两种响应格式：
    - ?format=base64 → JSON {image_id, media_type, data}
    - 默认 → 二进制图片（正确 Content-Type）
    """
    try:
        store = get_session_store()
        session_dir = store.get_session_dir(session_id)
        image_path = os.path.join(session_dir, "images", image_filename)

        if not os.path.exists(image_path):
            return JSONResponse(
                status_code=404,
                content={"error": "Image not found"}
            )

        # Determine media type from extension
        ext = image_filename.rsplit('.', 1)[-1].lower() if '.' in image_filename else 'png'
        media_type = EXT_TO_MEDIA_TYPE.get(ext, 'image/png')

        if format == 'base64':
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            return {
                "image_id": image_filename.rsplit('.', 1)[0],
                "media_type": media_type,
                "data": image_data
            }
        else:
            with open(image_path, 'rb') as f:
                image_data = f.read()
            return Response(content=image_data, media_type=media_type)

    except Exception as e:
        logger.error(f"Get image error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@router.post("/images/generate")
async def generate_image(request: ImageGenerateRequest):
    """
    生成图片 (Bedrock Stable Diffusion)
    """
    try:
        import boto3

        client = boto3.client('bedrock-runtime', region_name='us-west-2')

        body = {
            "text_prompts": [{"text": request.prompt}],
            "cfg_scale": 7,
            "steps": request.steps,
            "width": request.width,
            "height": request.height,
        }

        response = client.invoke_model(
            modelId=request.model,
            body=json.dumps(body),
            contentType='application/json'
        )

        result = json.loads(response['body'].read())

        if 'artifacts' in result and len(result['artifacts']) > 0:
            image_base64 = result['artifacts'][0]['base64']
            image_id = str(uuid.uuid4())
            return {
                "success": True,
                "image_id": image_id,
                "image_base64": image_base64
            }
        else:
            return {"success": False, "error": "No image generated"}

    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/images/search", response_model=ImageSearchResponse)
async def search_images(request: ImageSearchRequest):
    """
    搜索图片 (Brave Image Search)
    """
    try:
        try:
            from ..services.mcp_manager import get_mcp_manager

            mcp_manager = await get_mcp_manager()
            result = await mcp_manager.execute_tool(
                "web-search__brave_image_search",
                {
                    "query": request.query,
                    "count": request.count
                }
            )

            if "error" not in result:
                images = []
                content = result.get("content", [])
                for item in content:
                    if isinstance(item, dict):
                        images.append(item)

                return ImageSearchResponse(
                    success=True,
                    query=request.query,
                    images=images,
                    total=len(images)
                )
        except Exception as e:
            logger.warning(f"MCP image search failed: {e}")

        return ImageSearchResponse(
            success=False,
            query=request.query,
            images=[],
            total=0,
            error="Image search service not available"
        )

    except Exception as e:
        logger.error(f"Image search error: {e}")
        return ImageSearchResponse(
            success=False,
            query=request.query,
            images=[],
            total=0,
            error=str(e)
        )


