from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context, require_roles
from app.core.config import get_settings
from app.db.session import get_db
from app.models import AlgorithmDefinition
from app.schemas.algorithm_definition import (
    AlgorithmAIGenerateRequest,
    AlgorithmAIGenerateResponse,
    AlgorithmDefinitionCreate,
    AlgorithmDefinitionResponse,
    AlgorithmDefinitionUpdate,
)
from app.schemas.analysis import AlgorithmParam
from app.services.analysis import ALGORITHMS
from app.services.system_settings import get_setting_value

router = APIRouter(prefix="/algorithms", tags=["algorithms"])
EDIT_ROLES = {"tenant_admin", "tenant_engineer"}
settings = get_settings()


def _resolve_ai_config(db: Session) -> dict:
    config = get_setting_value(db, "ai_config", {}) or {}
    provider = (config.get("provider") or "openai").lower()
    base_url = config.get("base_url")
    if not base_url:
        base_url = {
            "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "kimi": "https://api.moonshot.cn/v1",
        }.get(provider)
    return {
        "provider": provider,
        "enabled": config.get("enabled", True),
        "api_key": config.get("api_key") or settings.openai_api_key,
        "base_url": base_url,
        "model": config.get("model") or settings.openai_model,
        "temperature": config.get("temperature"),
        "max_output_tokens": config.get("max_output_tokens"),
        "timeout_seconds": config.get("timeout_seconds"),
    }


def _require_tenant(ctx: AuthContext):
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")
    return ctx.tenant


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "algo"


def _extract_params(config: dict) -> list[AlgorithmParam]:
    raw_params = config.get("params") or []
    params: list[AlgorithmParam] = []
    for raw in raw_params:
        try:
            params.append(AlgorithmParam(**raw))
        except Exception:
            continue
    return params


@router.post("/ai-generate", response_model=AlgorithmAIGenerateResponse, summary="Generate python algorithm via AI")
def ai_generate_algorithm(
    payload: AlgorithmAIGenerateRequest,
    ctx: AuthContext = Depends(require_roles(*EDIT_ROLES)),
    db: Session = Depends(get_db),
) -> AlgorithmAIGenerateResponse:
    _require_tenant(ctx)
    ai_config = _resolve_ai_config(db)
    if not ai_config.get("enabled", True):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI feature is disabled.")
    if not ai_config.get("api_key"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI API key is not configured.")

    requirement = payload.requirement.strip()
    field_hint = f"Target field: {payload.field}\n" if payload.field else ""
    prompt = (
        "You are a senior data scientist. Generate a Python function for WellVision algorithms.\n"
        "Rules:\n"
        "1) Output JSON only with keys: code, params.\n"
        "2) code must define def run(points, params): and return {'result_series': [...], 'metrics': {...}}.\n"
        "3) points is a list of {ts, value}. result_series should be list of {ts, value}.\n"
        "4) params is a list of param definitions: key, label, default, min, max, step.\n"
        "Requirement:\n"
        f"{requirement}\n"
        f"{field_hint}"
    )

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=ai_config["api_key"],
            base_url=ai_config.get("base_url") or None,
            timeout=ai_config.get("timeout_seconds") or None,
        )
        request_kwargs = {
            "model": ai_config["model"],
            "input": prompt,
            "max_output_tokens": int(ai_config.get("max_output_tokens") or 800),
        }
        if ai_config.get("temperature") is not None:
            request_kwargs["temperature"] = ai_config.get("temperature")
        resp = client.responses.create(**request_kwargs)
        raw = resp.output_text or "{}"
    except Exception as exc:  # pragma: no cover - network dependent
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI generate failed: {exc}") from exc

    import json

    try:
        data = json.loads(raw)
    except Exception:
        data = {}

    code = data.get("code") if isinstance(data, dict) else None
    params = data.get("params") if isinstance(data, dict) else None
    if not code:
        code = (
            "def run(points, params):\n"
            "    return {'result_series': points, 'metrics': {'count': len(points)}}"
        )
    params_list = []
    if isinstance(params, list):
        for item in params:
            if isinstance(item, dict) and item.get("key"):
                params_list.append(item)

    return AlgorithmAIGenerateResponse(code=code, params=_extract_params({"params": params_list}))

@router.get("", response_model=list[AlgorithmDefinitionResponse], summary="List custom algorithms")
def list_algorithms(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[AlgorithmDefinitionResponse]:
    tenant = _require_tenant(ctx)
    stmt = (
        select(AlgorithmDefinition)
        .where(AlgorithmDefinition.tenant_id == tenant.id)
        .order_by(AlgorithmDefinition.updated_at.desc())
    )
    rows = db.execute(stmt).scalars().all()
    return [
        AlgorithmDefinitionResponse(
            id=row.id,
            tenant_id=row.tenant_id,
            created_by_user_id=row.created_by_user_id,
            key=row.key,
            name=row.name,
            kind=row.kind,  # type: ignore[arg-type]
            description=row.description,
            config=row.config or {},
            enabled=row.enabled,
            params=_extract_params(row.config or {}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get("/{algorithm_id}", response_model=AlgorithmDefinitionResponse, summary="Get custom algorithm")
def get_algorithm(
    algorithm_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AlgorithmDefinitionResponse:
    tenant = _require_tenant(ctx)
    row = db.get(AlgorithmDefinition, algorithm_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Algorithm not found.")
    return AlgorithmDefinitionResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        created_by_user_id=row.created_by_user_id,
        key=row.key,
        name=row.name,
        kind=row.kind,  # type: ignore[arg-type]
        description=row.description,
        config=row.config or {},
        enabled=row.enabled,
        params=_extract_params(row.config or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=AlgorithmDefinitionResponse, summary="Create custom algorithm")
def create_algorithm(
    payload: AlgorithmDefinitionCreate,
    ctx: AuthContext = Depends(require_roles(*EDIT_ROLES)),
    db: Session = Depends(get_db),
) -> AlgorithmDefinitionResponse:
    tenant = _require_tenant(ctx)
    key = payload.key or _slugify(payload.name)
    if key in ALGORITHMS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Key conflicts with builtin algorithm.")

    existing = db.execute(
        select(AlgorithmDefinition).where(
            AlgorithmDefinition.tenant_id == tenant.id,
            AlgorithmDefinition.key == key,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Algorithm key already exists.")

    row = AlgorithmDefinition(
        tenant_id=tenant.id,
        created_by_user_id=ctx.user.id,
        key=key,
        name=payload.name.strip(),
        kind=payload.kind,
        description=payload.description,
        config=payload.config or {},
        enabled=payload.enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return AlgorithmDefinitionResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        created_by_user_id=row.created_by_user_id,
        key=row.key,
        name=row.name,
        kind=row.kind,  # type: ignore[arg-type]
        description=row.description,
        config=row.config or {},
        enabled=row.enabled,
        params=_extract_params(row.config or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.patch(
    "/{algorithm_id}",
    response_model=AlgorithmDefinitionResponse,
    summary="Update custom algorithm",
)
def update_algorithm(
    algorithm_id: uuid.UUID,
    payload: AlgorithmDefinitionUpdate,
    ctx: AuthContext = Depends(require_roles(*EDIT_ROLES)),
    db: Session = Depends(get_db),
) -> AlgorithmDefinitionResponse:
    tenant = _require_tenant(ctx)
    row = db.get(AlgorithmDefinition, algorithm_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Algorithm not found.")

    if payload.key and payload.key != row.key:
        if payload.key in ALGORITHMS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Key conflicts with builtin algorithm.")
        existing = db.execute(
            select(AlgorithmDefinition).where(
                AlgorithmDefinition.tenant_id == tenant.id,
                AlgorithmDefinition.key == payload.key,
                AlgorithmDefinition.id != algorithm_id,
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Algorithm key already exists.")
        row.key = payload.key

    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.kind is not None:
        row.kind = payload.kind
    if payload.description is not None:
        row.description = payload.description
    if payload.config is not None:
        row.config = payload.config
    if payload.enabled is not None:
        row.enabled = payload.enabled

    db.commit()
    db.refresh(row)
    return AlgorithmDefinitionResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        created_by_user_id=row.created_by_user_id,
        key=row.key,
        name=row.name,
        kind=row.kind,  # type: ignore[arg-type]
        description=row.description,
        config=row.config or {},
        enabled=row.enabled,
        params=_extract_params(row.config or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete("/{algorithm_id}", status_code=status.HTTP_200_OK, summary="Delete custom algorithm")
def delete_algorithm(
    algorithm_id: uuid.UUID,
    ctx: AuthContext = Depends(require_roles(*EDIT_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    tenant = _require_tenant(ctx)
    row = db.get(AlgorithmDefinition, algorithm_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Algorithm not found.")
    db.delete(row)
    db.commit()
    return {"status": "deleted"}
