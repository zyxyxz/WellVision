from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.models import Project
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.audit import write_audit_log

router = APIRouter(prefix="/projects", tags=["projects"])


def _require_tenant(ctx: AuthContext):
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")
    return ctx.tenant


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "project"


@router.get("", response_model=list[ProjectResponse], summary="List projects")
def list_projects(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[ProjectResponse]:
    tenant = _require_tenant(ctx)
    rows = (
        db.execute(select(Project).where(Project.tenant_id == tenant.id).order_by(Project.created_at.desc()))
        .scalars()
        .all()
    )
    return [
        ProjectResponse(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            code=row.code,
            description=row.description,
            background=row.background,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post("", response_model=ProjectResponse, summary="Create project")
def create_project(
    payload: ProjectCreate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    tenant = _require_tenant(ctx)
    code = (payload.code or _slugify(payload.name)).strip()
    existing = db.execute(
        select(Project).where(Project.tenant_id == tenant.id, Project.code == code)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project code already exists.")

    row = Project(
        tenant_id=tenant.id,
        name=payload.name.strip(),
        code=code,
        description=(payload.description or "").strip() or None,
        background=(payload.background or "").strip() or None,
        status=(payload.status or "active").strip(),
    )
    db.add(row)
    db.flush()
    write_audit_log(
        db,
        actor=ctx.user,
        action="project.create",
        tenant_id=tenant.id,
        details={"project_id": str(row.id), "name": row.name},
    )
    db.commit()
    db.refresh(row)
    return ProjectResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        code=row.code,
        description=row.description,
        background=row.background,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/{project_id}", response_model=ProjectResponse, summary="Get project")
def get_project(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    tenant = _require_tenant(ctx)
    row = db.get(Project, project_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return ProjectResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        code=row.code,
        description=row.description,
        background=row.background,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.patch("/{project_id}", response_model=ProjectResponse, summary="Update project")
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    tenant = _require_tenant(ctx)
    row = db.get(Project, project_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    if payload.code and payload.code != row.code:
        existing = db.execute(
            select(Project).where(Project.tenant_id == tenant.id, Project.code == payload.code)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project code already exists.")
        row.code = payload.code

    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.description is not None:
        row.description = payload.description.strip() or None
    if payload.background is not None:
        row.background = payload.background.strip() or None
    if payload.status is not None:
        row.status = payload.status.strip() or row.status

    write_audit_log(
        db,
        actor=ctx.user,
        action="project.update",
        tenant_id=tenant.id,
        details={"project_id": str(row.id)},
    )
    db.commit()
    db.refresh(row)
    return ProjectResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        code=row.code,
        description=row.description,
        background=row.background,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete("/{project_id}", status_code=status.HTTP_200_OK, summary="Delete project")
def delete_project(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict:
    tenant = _require_tenant(ctx)
    row = db.get(Project, project_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    db.delete(row)
    write_audit_log(
        db,
        actor=ctx.user,
        action="project.delete",
        tenant_id=tenant.id,
        details={"project_id": str(row.id)},
    )
    db.commit()
    return {"status": "ok"}
