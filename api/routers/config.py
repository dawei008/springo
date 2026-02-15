"""
Config Router for FastAPI
配置管理端点（完整版）
包含：工作目录、AWS 凭证、S3、Memory 配置
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import os
import time
import logging

from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# 全局工作目录存储
_working_dir: str = os.getcwd()


def _sync_working_dir(path: str):
    """Sync working directory to session_state and mcp_tools modules"""
    try:
        from ..services.session_state import set_working_dir as _set_session_wd
        _set_session_wd(path)
    except Exception as e:
        logger.debug(f"Failed to sync working_dir to session_state: {e}")
    try:
        from mcp_tools.config import set_working_dir as _set_mcp_wd
        _set_mcp_wd(path)
    except Exception as e:
        logger.debug(f"Failed to sync working_dir to mcp_tools: {e}")


# Sync initial working_dir on module load
_sync_working_dir(_working_dir)


# ============ Models ============

class WorkingDirRequest(BaseModel):
    working_dir: str


class WorkingDirResponse(BaseModel):
    success: bool = True
    working_dir: str
    exists: bool = True  # whether the requested path exists on disk


class WarmupResponse(BaseModel):
    status: str
    skills_count: int = 0
    mcp_status: Optional[Dict[str, Any]] = None
    bedrock_ready: bool = False
    elapsed_ms: float = 0


class AwsConfigRequest(BaseModel):
    auth_method: Optional[str] = None
    region: Optional[str] = None
    profile: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    session_token: Optional[str] = None
    sso_start_url: Optional[str] = None
    sso_account_id: Optional[str] = None
    sso_role_name: Optional[str] = None


class S3ConfigRequest(BaseModel):
    s3_bucket: Optional[str] = None
    s3_region: Optional[str] = None
    s3_enabled: Optional[bool] = None


class MemoryConfigRequest(BaseModel):
    memory_id: Optional[str] = None
    memory_region: Optional[str] = None
    memory_enabled: Optional[bool] = None


class CreateMemoryRequest(BaseModel):
    region: str = Field(default="us-west-2")
    name_prefix: str = Field(default="springo_memory")


class CreateS3BucketRequest(BaseModel):
    region: str = Field(default="us-east-1")
    bucket_prefix: str = Field(default="springo")


class CreateMemoryAndS3Request(BaseModel):
    """Combined Memory + S3 creation request"""
    memory_region: str = Field(default="us-west-2")
    memory_name_prefix: str = Field(default="springo_memory")
    s3_region: str = Field(default="us-east-1")
    s3_bucket_prefix: str = Field(default="springo")
    create_s3: bool = Field(default=True)


# ============ Working Directory ============

@router.get("/config/working-dir", response_model=WorkingDirResponse)
async def get_working_dir():
    """获取当前工作目录"""
    return WorkingDirResponse(working_dir=_working_dir)


@router.post("/config/working-dir", response_model=WorkingDirResponse)
async def set_working_dir(request: WorkingDirRequest):
    """设置工作目录

    If the requested path exists, switch to it.
    If not, keep the current working directory and return exists=False
    so the frontend can fall back to a default folder.
    """
    global _working_dir
    requested = request.working_dir
    path_exists = bool(requested and os.path.isdir(requested))

    if path_exists:
        _working_dir = requested
    # Don't auto-create missing directories — let the frontend decide

    # Sync to session_state and mcp_tools so tools use the correct working dir
    _sync_working_dir(_working_dir)
    return WorkingDirResponse(working_dir=_working_dir, exists=path_exists)


@router.post("/config/check-paths")
async def check_paths(paths: List[str]) -> Dict[str, bool]:
    """Check which paths exist on disk. Used to prune stale workspace folders."""
    return {p: os.path.isdir(p) for p in paths}


# ============ Warmup ============

@router.post("/warmup", response_model=WarmupResponse)
async def warmup():
    """预热端点 - 初始化连接和缓存"""
    start = time.time()
    skills_count = 0
    mcp_status = None
    bedrock_ready = False

    # 预热技能
    try:
        from .skills import _load_skills
        skills = _load_skills()
        skills_count = len(skills)
    except Exception as e:
        logger.warning(f"Skill warmup error: {e}")

    # 预热 MCP
    try:
        from ..services.mcp_client import get_external_mcp_manager
        manager = get_external_mcp_manager()
        health = manager.health_check_all()
        mcp_status = health
    except Exception as e:
        logger.warning(f"MCP warmup error: {e}")

    # 预热 Bedrock
    try:
        from ..services.bedrock import get_bedrock_service
        get_bedrock_service()
        bedrock_ready = True
    except Exception as e:
        logger.warning(f"Bedrock warmup error: {e}")

    elapsed_ms = (time.time() - start) * 1000

    return WarmupResponse(
        status="ok",
        skills_count=skills_count,
        mcp_status=mcp_status,
        bedrock_ready=bedrock_ready,
        elapsed_ms=round(elapsed_ms, 1),
    )


# ============ AWS Config ============

@router.get("/config/aws")
async def get_aws_config() -> Dict[str, Any]:
    """获取 AWS 凭证配置"""
    try:
        from ..services.auth_manager import get_aws_config
        return get_aws_config()
    except Exception as e:
        logger.error(f"Get AWS config error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/aws")
async def set_aws_config(request: AwsConfigRequest) -> Dict[str, Any]:
    """设置 AWS 凭证配置"""
    try:
        from ..services.auth_manager import set_aws_config
        return set_aws_config(
            auth_method=request.auth_method,
            region=request.region,
            profile=request.profile,
            access_key_id=request.access_key_id,
            secret_access_key=request.secret_access_key,
            session_token=request.session_token,
            sso_start_url=request.sso_start_url,
            sso_account_id=request.sso_account_id,
            sso_role_name=request.sso_role_name,
        )
    except Exception as e:
        logger.error(f"Set AWS config error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/aws/test")
async def test_aws_connection() -> Dict[str, Any]:
    """测试 AWS 连接"""
    try:
        from ..services.auth_manager import test_aws_connection
        return await test_aws_connection()
    except Exception as e:
        logger.error(f"AWS test error: {e}")
        return {"success": False, "error": str(e)}


@router.get("/config/aws/profiles")
async def list_aws_profiles() -> Dict[str, Any]:
    """列出 AWS profiles"""
    try:
        from ..services.auth_manager import get_aws_profiles
        profiles = get_aws_profiles()
        return {"profiles": profiles, "total": len(profiles)}
    except Exception as e:
        logger.error(f"List profiles error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ S3 Config ============

@router.get("/config/s3")
async def get_s3_config() -> Dict[str, Any]:
    """获取 S3 配置"""
    try:
        from ..services.s3_sync import get_s3_config
        return get_s3_config()
    except Exception as e:
        logger.error(f"Get S3 config error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/s3")
async def set_s3_config(request: S3ConfigRequest) -> Dict[str, Any]:
    """设置 S3 配置"""
    try:
        from ..services.s3_sync import load_s3_config, save_s3_config
        config = load_s3_config()
        if request.s3_bucket is not None:
            config["s3_bucket"] = request.s3_bucket
        if request.s3_region is not None:
            config["s3_region"] = request.s3_region
        if request.s3_enabled is not None:
            config["s3_enabled"] = request.s3_enabled
        save_s3_config(config)
        return config
    except Exception as e:
        logger.error(f"Set S3 config error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/s3/create")
async def create_s3_bucket(request: CreateS3BucketRequest) -> Dict[str, Any]:
    """创建 S3 存储桶"""
    try:
        from ..services.s3_sync import create_s3_bucket
        return create_s3_bucket(request.region, request.bucket_prefix)
    except Exception as e:
        logger.error(f"Create S3 bucket error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ Memory Config ============

@router.get("/config/memory")
async def get_memory_config() -> Dict[str, Any]:
    """获取 Memory 配置"""
    try:
        from ..services.memory_sync import get_memory_config
        return get_memory_config()
    except Exception as e:
        logger.error(f"Get memory config error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/memory")
async def set_memory_config(request: MemoryConfigRequest) -> Dict[str, Any]:
    """设置 Memory 配置（启用时自动发现 LTM 策略）"""
    try:
        from ..services.memory_sync import load_memory_config, save_memory_config, auto_setup_memory_strategies
        config = load_memory_config()
        if request.memory_id is not None:
            # Only update memory_id if the new value is non-empty,
            # to prevent accidental clearing from partial UI updates
            if request.memory_id or not config.get("memory_id"):
                config["memory_id"] = request.memory_id
        if request.memory_region is not None:
            config["memory_region"] = request.memory_region
        if request.memory_enabled is not None:
            config["memory_enabled"] = request.memory_enabled
        save_memory_config(config)

        # Auto-discover LTM strategies when enabling with a valid memory_id
        if config.get("memory_enabled") and config.get("memory_id"):
            try:
                strategies_result = auto_setup_memory_strategies(
                    config["memory_id"],
                    config.get("memory_region", "us-west-2"),
                )
                config["ltm_setup"] = strategies_result

                # Persist LTM strategies to full config
                if strategies_result.get("strategies"):
                    try:
                        import json as json_module
                        CONFIG_DIR = os.path.expanduser("~/.springo")
                        CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
                        full_config = {}
                        if os.path.exists(CONFIG_FILE):
                            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                                full_config = json_module.load(f)
                        if 'memory' not in full_config:
                            full_config['memory'] = {}
                        full_config['memory']['ltm'] = {
                            'enabled': True,
                            'strategies': strategies_result['strategies'],
                            'sync_interval': full_config.get('memory', {}).get('ltm', {}).get('sync_interval', 900),
                        }
                        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                            json_module.dump(full_config, f, indent=2, ensure_ascii=False)
                    except Exception as ltm_err:
                        logger.warning(f"Failed to persist LTM config: {ltm_err}")
            except Exception as e:
                logger.warning(f"Auto LTM strategy setup skipped: {e}")

        return config
    except Exception as e:
        logger.error(f"Set memory config error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/memory/create")
async def create_memory(request: CreateMemoryRequest) -> Dict[str, Any]:
    """创建/配置 Memory"""
    try:
        from ..services.memory_sync import create_memory
        return create_memory(request.region, request.name_prefix)
    except Exception as e:
        logger.error(f"Create memory error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/memory/test")
async def test_memory_connection() -> Dict[str, Any]:
    """测试 Memory 连接"""
    try:
        from ..services.memory_sync import load_memory_config
        config = load_memory_config()
        memory_id = config.get("memory_id", "")
        if not memory_id:
            return {"success": False, "error": "Memory ID not configured"}

        import boto3
        client = boto3.client('bedrock-agentcore', region_name=config.get("memory_region", "us-west-2"))
        # Use list_actors to verify connection - only requires memoryId
        client.list_actors(memoryId=memory_id, maxResults=1)
        return {"success": True, "memory_id": memory_id, "region": config.get("memory_region")}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/config/memory/strategies/refresh")
async def refresh_memory_strategies() -> Dict[str, Any]:
    """刷新 Memory LTM 策略（actual API discovery）"""
    try:
        from ..services.memory_sync import load_memory_config, auto_setup_memory_strategies
        config = load_memory_config()
        memory_id = config.get("memory_id", "")
        if not memory_id:
            return {"success": False, "error": "Memory ID not configured", "strategies": []}

        region = config.get("memory_region", "us-west-2")
        result = auto_setup_memory_strategies(memory_id, region)
        return result
    except Exception as e:
        logger.error(f"Refresh strategies error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ S3 Status & Sync ============

@router.get("/s3/status")
async def get_s3_status() -> Dict[str, Any]:
    """获取 S3 同步状态"""
    try:
        from ..services.s3_sync import get_s3_manager
        manager = get_s3_manager()
        if manager:
            return {"enabled": True, **manager.get_stats()}
        return {"enabled": False, "error": "S3 sync not initialized"}
    except Exception as e:
        return {"enabled": False, "error": str(e)}


@router.post("/s3/sync/{session_id}")
async def sync_session_to_s3(session_id: str) -> Dict[str, Any]:
    """同步会话文件到 S3"""
    try:
        from ..services.s3_sync import get_s3_manager, init_s3_sync
        manager = get_s3_manager()
        if not manager:
            init_s3_sync()
            manager = get_s3_manager()
        if not manager:
            return {"success": False, "error": "S3 sync not available"}
        uploaded = manager.sync_session_files(session_id)
        return {"success": True, "uploaded": len(uploaded), "files": uploaded}
    except Exception as e:
        logger.error(f"S3 sync error: {e}")
        return {"success": False, "error": str(e)}


# ============ Combined Memory + S3 Setup ============

@router.post("/config/setup-memory-s3")
async def setup_memory_and_s3(request: CreateMemoryAndS3Request) -> Dict[str, Any]:
    """Combined Memory + S3 creation

    Creates/configures both Memory and S3 bucket in a single call,
    then auto-discovers LTM strategies.
    """
    results = {"memory": None, "s3": None, "strategies": None}

    # Step 1: Setup Memory
    try:
        from ..services.memory_sync import create_memory, auto_setup_memory_strategies
        memory_result = create_memory(request.memory_region, request.memory_name_prefix)
        results["memory"] = memory_result

        # Auto-discover strategies if memory setup succeeded
        if memory_result.get("success") and memory_result.get("memory_id"):
            try:
                strategies = auto_setup_memory_strategies(
                    memory_result["memory_id"], request.memory_region
                )
                results["strategies"] = strategies
            except Exception as e:
                results["strategies"] = {"success": False, "error": str(e)}
    except Exception as e:
        results["memory"] = {"success": False, "error": str(e)}

    # Step 2: Setup S3 (optional)
    if request.create_s3:
        try:
            from ..services.s3_sync import create_s3_bucket
            s3_result = create_s3_bucket(request.s3_region, request.s3_bucket_prefix)
            results["s3"] = s3_result
        except Exception as e:
            results["s3"] = {"success": False, "error": str(e)}

    results["success"] = (
        bool(results.get("memory", {}).get("success"))
        and (not request.create_s3 or bool(results.get("s3", {}).get("success")))
    )
    return results


def get_current_working_dir() -> str:
    """获取当前工作目录（供其他模块使用）"""
    return _working_dir


# ============ Feishu Bot Config ============

class FeishuConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    app_id: Optional[str] = None
    app_secret: Optional[str] = None


@router.get("/config/feishu")
async def get_feishu_config() -> Dict[str, Any]:
    """Get Feishu bot configuration (secrets masked)."""
    import json as json_module

    result: Dict[str, Any] = {
        "enabled": False,
        "app_id": "",
        "app_secret_masked": "",
        "running": False,
    }
    try:
        cfg_file = os.path.expanduser("~/.springo/config.json")
        if os.path.exists(cfg_file):
            with open(cfg_file, 'r', encoding='utf-8') as f:
                cfg = json_module.load(f)
            feishu = cfg.get("integrations", {}).get("feishu", {})
            result["enabled"] = feishu.get("enabled", False)
            result["app_id"] = feishu.get("app_id", "")
            secret = feishu.get("app_secret", "")
            result["app_secret_masked"] = (
                f"{secret[:4]}...{secret[-4:]}" if len(secret) > 8 else ("***" if secret else "")
            )

        # Check if feishu bot thread is running
        try:
            from ..services.feishu_bot import _feishu_thread
            result["running"] = _feishu_thread is not None and _feishu_thread.is_alive()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Get Feishu config error: {e}")
    return result


@router.post("/config/feishu")
async def set_feishu_config(request: FeishuConfigRequest) -> Dict[str, Any]:
    """Save Feishu bot configuration to ~/.springo/config.json."""
    import json as json_module

    CONFIG_DIR = os.path.expanduser("~/.springo")
    CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
    os.makedirs(CONFIG_DIR, exist_ok=True)

    try:
        config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json_module.load(f)

        if "integrations" not in config:
            config["integrations"] = {}
        if "feishu" not in config["integrations"]:
            config["integrations"]["feishu"] = {}

        feishu = config["integrations"]["feishu"]
        if request.enabled is not None:
            feishu["enabled"] = request.enabled
        if request.app_id is not None:
            feishu["app_id"] = request.app_id
        if request.app_secret is not None:
            feishu["app_secret"] = request.app_secret

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json_module.dump(config, f, indent=2, ensure_ascii=False)

        # Hot-reload: restart Feishu bot with new config
        restarted = False
        try:
            from ..services.feishu_bot import restart_feishu_bot
            restarted = await restart_feishu_bot()
        except Exception as e:
            logger.warning(f"Feishu bot restart failed: {e}")

        return {"success": True, "running": restarted}
    except Exception as e:
        logger.error(f"Set Feishu config error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/feishu/test")
async def test_feishu_connection() -> Dict[str, Any]:
    """Test Feishu bot credentials by calling the tenant_access_token API."""
    import json as json_module
    import httpx

    # Read stored config
    app_id = ""
    app_secret = ""
    try:
        cfg_file = os.path.expanduser("~/.springo/config.json")
        if os.path.exists(cfg_file):
            with open(cfg_file, 'r', encoding='utf-8') as f:
                cfg = json_module.load(f)
            feishu = cfg.get("integrations", {}).get("feishu", {})
            app_id = feishu.get("app_id", "")
            app_secret = feishu.get("app_secret", "")
    except Exception:
        pass

    if not app_id or not app_secret:
        return {"success": False, "error": "App ID and App Secret are required"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": app_id, "app_secret": app_secret},
            )
            data = resp.json()
            if data.get("code") == 0:
                return {
                    "success": True,
                    "message": "Feishu credentials valid. Tenant access token obtained.",
                }
            else:
                return {
                    "success": False,
                    "error": f"Feishu API error {data.get('code')}: {data.get('msg', 'Unknown error')}",
                }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============ Vendor API Keys ============

class VendorKeyRequest(BaseModel):
    vendor: str  # e.g., "deepseek"
    api_key: str
    base_url: Optional[str] = None


@router.get("/config/vendor-keys")
async def get_vendor_keys() -> Dict[str, Any]:
    """Get configured vendor API keys (masked)."""
    import json as json_module

    CONFIG_DIR = os.path.expanduser("~/.springo")
    CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

    result: Dict[str, Any] = {"vendor_keys": {}}
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json_module.load(f)
            vendor_keys = config.get("vendor_keys", {})
            for vendor, info in vendor_keys.items():
                key = info.get("api_key", "")
                result["vendor_keys"][vendor] = {
                    "configured": bool(key),
                    "api_key_masked": f"{key[:6]}...{key[-4:]}" if len(key) > 10 else ("***" if key else ""),
                    "base_url": info.get("base_url", ""),
                }
    except Exception as e:
        logger.error(f"Get vendor keys error: {e}")
    return result


@router.post("/config/vendor-keys")
async def set_vendor_key(request: VendorKeyRequest) -> Dict[str, Any]:
    """Save a vendor API key to ~/.springo/config.json."""
    import json as json_module

    CONFIG_DIR = os.path.expanduser("~/.springo")
    CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
    os.makedirs(CONFIG_DIR, exist_ok=True)

    try:
        config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json_module.load(f)

        if "vendor_keys" not in config:
            config["vendor_keys"] = {}

        entry: Dict[str, str] = {"api_key": request.api_key}
        if request.base_url:
            entry["base_url"] = request.base_url
        config["vendor_keys"][request.vendor] = entry

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json_module.dump(config, f, indent=2, ensure_ascii=False)

        # Reinitialize vendor services when keys change
        if request.api_key:
            try:
                from ..services.vendor_router import get_vendor_router
                from ..services.bedrock import get_bedrock_service
                router_svc = get_vendor_router()
                if request.vendor == "deepseek":
                    from ..services.deepseek import init_deepseek_service
                    base_url = request.base_url or "https://api.deepseek.com"
                    ds = init_deepseek_service(request.api_key, base_url)
                    router_svc.deepseek = ds
                    logger.info("DeepSeek service reinitialized with new API key")
                elif request.vendor == "minimax":
                    from ..services.minimax import init_minimax_service
                    base_url = request.base_url or "https://api.minimax.chat/v1"
                    mm = init_minimax_service(request.api_key, base_url)
                    router_svc.minimax = mm
                    logger.info("MiniMax service reinitialized with new API key")
            except Exception as e:
                logger.warning(f"Failed to reinitialize {request.vendor} service: {e}")

        return {"success": True, "vendor": request.vendor}
    except Exception as e:
        logger.error(f"Set vendor key error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/vendor-keys/test")
async def test_vendor_key(request: VendorKeyRequest) -> Dict[str, Any]:
    """Test a vendor API key by making a lightweight API call."""
    # Vendor-specific defaults
    _vendor_defaults = {
        "deepseek": "https://api.deepseek.com",
        "minimax": "https://api.minimax.chat/v1",
    }

    if request.vendor not in _vendor_defaults:
        return {"success": False, "error": f"Unsupported vendor: {request.vendor}"}

    import httpx
    import json as json_module

    api_key = request.api_key
    default_base = _vendor_defaults[request.vendor]
    base_url = (request.base_url or default_base).rstrip("/")

    # If api_key is a placeholder, read from stored config
    if not api_key or api_key == "use-stored":
        try:
            cfg_file = os.path.expanduser("~/.springo/config.json")
            if os.path.exists(cfg_file):
                with open(cfg_file, 'r') as f:
                    cfg = json_module.load(f)
                v_cfg = cfg.get("vendor_keys", {}).get(request.vendor, {})
                api_key = v_cfg.get("api_key", "")
                stored_base = v_cfg.get("base_url", "")
                if stored_base and base_url == default_base:
                    base_url = stored_base
        except Exception:
            pass

    if not api_key:
        return {"success": False, "vendor": request.vendor, "error": "No API key configured"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # MiniMax doesn't have a /models endpoint; use a minimal chat call
            if request.vendor == "minimax":
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": "MiniMax-M2.5", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
                )
                if resp.status_code == 200:
                    return {
                        "success": True,
                        "vendor": request.vendor,
                        "message": "Connected. MiniMax API key is valid.",
                    }
                else:
                    err_text = resp.text[:200]
                    # Auth errors are clear failures
                    return {
                        "success": False,
                        "vendor": request.vendor,
                        "error": f"HTTP {resp.status_code}: {err_text}",
                    }
            else:
                resp = await client.get(
                    f"{base_url}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    model_ids = [m.get("id", "") for m in data.get("data", [])]
                    return {
                        "success": True,
                        "vendor": request.vendor,
                        "models": model_ids[:5],
                        "message": f"Connected. {len(model_ids)} model(s) available.",
                    }
                else:
                    return {
                        "success": False,
                        "vendor": request.vendor,
                        "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                    }
    except Exception as e:
        return {"success": False, "vendor": request.vendor, "error": str(e)}
