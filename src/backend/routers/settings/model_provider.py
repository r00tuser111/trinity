"""Platform-wide model provider routes (LLM-PROVIDER-001).

Included before `generic` like every sibling: `/model-provider` and
`/model-catalog` are specific paths the `/{key}` catch-all would otherwise
swallow (Invariant #4). Policy lives in `services/llm_provider.py`.
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from dependencies import assert_admin, get_current_user
from models import ModelProviderTest, ModelProviderUpdate, User
from services import llm_provider
from services.platform_audit_service import AuditEventType, platform_audit_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Strong refs for fire-and-forget restarts (the event loop only holds a weak one).
_inflight: "set[asyncio.Task]" = set()


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


def _connect_waiting_agents() -> None:
    """Agents created with no credential pick the provider up (ent#582 path)."""
    try:
        from services.subscription_service import connect_agents_to_first_credential
        connect_agents_to_first_credential()
    except Exception as e:  # noqa: BLE001 — the provider is already saved
        logger.warning("could not connect waiting agents to the model provider: %s", e)


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
    from services.subscription_service import is_claude_auth_configured

    was_configured = await asyncio.to_thread(is_claude_auth_configured)
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
        if not was_configured:
            _connect_waiting_agents()
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
    """Restart stale running agents now, in the background."""
    assert_admin(current_user)
    names = await asyncio.to_thread(llm_provider.stale_claude_agents)
    if names:
        task = asyncio.create_task(llm_provider.restart_agents(names))
        _inflight.add(task)
        task.add_done_callback(_inflight.discard)
    await _audit(request, current_user, "apply", agents=len(names))
    return {"restarting": names, "count": len(names)}


@router.get("/model-catalog")
async def get_model_catalog(current_user: User = Depends(get_current_user)):
    """What every model picker offers: the provider's list, or null for Claude."""
    return await asyncio.to_thread(llm_provider.selectable_catalog)
