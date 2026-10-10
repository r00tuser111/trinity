"""Platform-wide model provider routes (LLM-PROVIDER-001).

Included before `generic` like every sibling: `/model-provider` and
`/model-catalog` are specific paths the `/{key}` catch-all would otherwise
swallow (Invariant #4). Policy lives in `services/llm_provider.py`.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from dependencies import assert_admin, get_current_user
from models import ModelProviderTest, ModelProviderUpdate, User
from services import llm_provider
from services.platform_audit_service import AuditEventType, platform_audit_service

router = APIRouter()


async def _audit(request: Request, user: User, action: str, **details) -> None:
    # The key is never logged — only what changed.
    await platform_audit_service.log(
        event_type=AuditEventType.CONFIGURATION,
        event_action="settings_change",
        source="api",
        actor_user=user,
        actor_ip=request.client.host if request.client else None,
        endpoint=str(request.url.path),
        request_id=getattr(request.state, "request_id", None),
        details={"setting": "model_provider", "action": action, **details},
    )


@router.get("/model-provider")
async def get_model_provider(current_user: User = Depends(get_current_user)):
    assert_admin(current_user)
    return await asyncio.to_thread(llm_provider.provider_status)


@router.put("/model-provider")
async def update_model_provider(
    body: ModelProviderUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    assert_admin(current_user)
    if body.mode == llm_provider.MODE_ANTHROPIC:
        await asyncio.to_thread(llm_provider.use_anthropic)
        await _audit(request, current_user, "use_anthropic")
    else:
        try:
            await asyncio.to_thread(
                lambda: llm_provider.save_provider(
                    base_url=body.base_url or "",
                    models=[m.model_dump() for m in body.models],
                    default_model=body.default_model,
                    fast_model=body.fast_model,
                    api_key=body.api_key,
                )
            )
        except llm_provider.ProviderConfigError as e:
            raise HTTPException(status_code=400, detail=str(e))
        await _audit(
            request, current_user, "use_custom",
            base_url=body.base_url, models=[m.id for m in body.models],
            key_changed=bool((body.api_key or "").strip()),
        )
    return await asyncio.to_thread(llm_provider.provider_status)


@router.delete("/model-provider")
async def delete_model_provider(request: Request, current_user: User = Depends(get_current_user)):
    assert_admin(current_user)
    await asyncio.to_thread(llm_provider.clear_provider)
    await _audit(request, current_user, "delete")
    return await asyncio.to_thread(llm_provider.provider_status)


@router.post("/model-provider/test")
async def test_model_provider(body: ModelProviderTest, current_user: User = Depends(get_current_user)):
    assert_admin(current_user)
    api_key = (body.api_key or "").strip()
    if not api_key:
        api_key = await asyncio.to_thread(llm_provider.stored_key_for, body.base_url)
    return await llm_provider.check_provider(body.base_url, api_key, body.model)


@router.get("/model-provider/pending")
async def pending_model_provider_agents(current_user: User = Depends(get_current_user)):
    """Running agents whose container still carries the previous provider env."""
    assert_admin(current_user)
    names = await asyncio.to_thread(llm_provider.stale_claude_agents)
    return {"agents": names, "count": len(names)}


@router.post("/model-provider/apply")
async def apply_model_provider(request: Request, current_user: User = Depends(get_current_user)):
    """Restart stale running agents and wait until each one is healthy.

    One restart, not a second one racing the save path. An agent that does not
    accept health checks is reported in ``not_ready`` rather than counted as
    switched.
    """
    assert_admin(current_user)
    names = await asyncio.to_thread(llm_provider.stale_claude_agents)
    result = {"restarted": [], "not_ready": [], "skipped": []}
    if names:
        result = await llm_provider.restart_agents(names)
    restarted = result.get("restarted") or []
    await _audit(
        request, current_user, "apply",
        agents=len(names), restarted=len(restarted),
        not_ready=len(result.get("not_ready") or []),
    )
    return {
        # `restarting` kept so an older client still reads a list of names.
        "restarting": restarted,
        "restarted": restarted,
        "not_ready": result.get("not_ready") or [],
        "skipped": result.get("skipped") or [],
        "count": len(restarted),
    }


@router.get("/model-catalog")
async def get_model_catalog(current_user: User = Depends(get_current_user)):
    """What every model picker offers: the provider's list, or null for Claude."""
    return await asyncio.to_thread(llm_provider.selectable_catalog)
