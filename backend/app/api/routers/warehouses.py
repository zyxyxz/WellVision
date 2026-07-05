from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.models import DataSource, DataWarehouse, Project
from app.schemas.warehouse import (
    DataSourceCreate,
    DataSourceUpdate,
    DataSourceResponse,
    DataWarehouseCreate,
    DataWarehouseUpdate,
    DataWarehouseResponse,
)
from app.services.audit import write_audit_log

router = APIRouter(prefix="/warehouses", tags=["warehouses"])


def _require_tenant(ctx: AuthContext):
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")
    return ctx.tenant


def _get_warehouse(db: Session, tenant_id: uuid.UUID, warehouse_id: uuid.UUID) -> DataWarehouse:
    warehouse = db.get(DataWarehouse, warehouse_id)
    if warehouse is None or warehouse.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found.")
    return warehouse


@router.get("", response_model=list[DataWarehouseResponse], summary="List data warehouses")
def list_warehouses(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[DataWarehouseResponse]:
    tenant = _require_tenant(ctx)
    stmt = (
        select(DataWarehouse)
        .where(DataWarehouse.tenant_id == tenant.id)
        .order_by(DataWarehouse.created_at.desc())
    )
    rows = db.execute(stmt).scalars().all()
    return [
        DataWarehouseResponse(
            id=row.id,
            tenant_id=row.tenant_id,
            project_id=row.project_id,
            name=row.name,
            description=row.description,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post("", response_model=DataWarehouseResponse, summary="Create data warehouse")
def create_warehouse(
    payload: DataWarehouseCreate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> DataWarehouseResponse:
    tenant = _require_tenant(ctx)
    project_id = payload.project_id
    if project_id is not None:
        project = db.get(Project, project_id)
        if project is None or project.tenant_id != tenant.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    warehouse = DataWarehouse(
        tenant_id=tenant.id,
        project_id=project_id,
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
    )
    db.add(warehouse)
    db.flush()

    sources = payload.sources or []
    for source in sources:
        name = (source.name or source.source_type).strip()
        db.add(
            DataSource(
                tenant_id=tenant.id,
                warehouse_id=warehouse.id,
                name=name or source.source_type,
                source_type=source.source_type,
                config=source.config or {},
                enabled=source.enabled,
            )
        )

    write_audit_log(
        db,
        actor=ctx.user,
        action="warehouse.create",
        tenant_id=tenant.id,
        details={"warehouse_id": str(warehouse.id), "name": warehouse.name},
    )
    db.commit()
    db.refresh(warehouse)

    return DataWarehouseResponse(
        id=warehouse.id,
        tenant_id=warehouse.tenant_id,
        project_id=warehouse.project_id,
        name=warehouse.name,
        description=warehouse.description,
        created_at=warehouse.created_at,
        updated_at=warehouse.updated_at,
    )


@router.patch(
    "/{warehouse_id}",
    response_model=DataWarehouseResponse,
    summary="Update data warehouse",
)
def update_warehouse(
    warehouse_id: uuid.UUID,
    payload: DataWarehouseUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> DataWarehouseResponse:
    tenant = _require_tenant(ctx)
    warehouse = _get_warehouse(db, tenant.id, warehouse_id)

    if "project_id" in payload.model_fields_set:
        if payload.project_id is None:
            warehouse.project_id = None
        else:
            project = db.get(Project, payload.project_id)
            if project is None or project.tenant_id != tenant.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
            warehouse.project_id = payload.project_id

    if payload.name is not None:
        warehouse.name = payload.name.strip() or warehouse.name
    if payload.description is not None:
        warehouse.description = payload.description.strip() or None

    write_audit_log(
        db,
        actor=ctx.user,
        action="warehouse.update",
        tenant_id=tenant.id,
        details={"warehouse_id": str(warehouse.id)},
    )
    db.commit()
    db.refresh(warehouse)
    return DataWarehouseResponse(
        id=warehouse.id,
        tenant_id=warehouse.tenant_id,
        project_id=warehouse.project_id,
        name=warehouse.name,
        description=warehouse.description,
        created_at=warehouse.created_at,
        updated_at=warehouse.updated_at,
    )


@router.get(
    "/{warehouse_id}/sources",
    response_model=list[DataSourceResponse],
    summary="List data sources for a warehouse",
)
def list_sources(
    warehouse_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[DataSourceResponse]:
    tenant = _require_tenant(ctx)
    _get_warehouse(db, tenant.id, warehouse_id)

    stmt = (
        select(DataSource)
        .where(DataSource.tenant_id == tenant.id, DataSource.warehouse_id == warehouse_id)
        .order_by(DataSource.created_at.desc())
    )
    rows = db.execute(stmt).scalars().all()
    return [
        DataSourceResponse(
            id=row.id,
            tenant_id=row.tenant_id,
            warehouse_id=row.warehouse_id,
            name=row.name,
            source_type=row.source_type,
            config=row.config or {},
            enabled=row.enabled,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post(
    "/{warehouse_id}/sources",
    response_model=DataSourceResponse,
    summary="Add a data source to a warehouse",
)
def create_source(
    warehouse_id: uuid.UUID,
    payload: DataSourceCreate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> DataSourceResponse:
    tenant = _require_tenant(ctx)
    _get_warehouse(db, tenant.id, warehouse_id)

    source = DataSource(
        tenant_id=tenant.id,
        warehouse_id=warehouse_id,
        name=(payload.name or payload.source_type).strip(),
        source_type=payload.source_type,
        config=payload.config or {},
        enabled=payload.enabled,
    )
    db.add(source)
    db.flush()

    write_audit_log(
        db,
        actor=ctx.user,
        action="warehouse.source.create",
        tenant_id=tenant.id,
        details={"warehouse_id": str(warehouse_id), "source_id": str(source.id)},
    )
    db.commit()
    db.refresh(source)

    return DataSourceResponse(
        id=source.id,
        tenant_id=source.tenant_id,
        warehouse_id=source.warehouse_id,
        name=source.name,
        source_type=source.source_type,
        config=source.config or {},
        enabled=source.enabled,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


@router.patch(
    "/{warehouse_id}/sources/{source_id}",
    response_model=DataSourceResponse,
    summary="Update a data source",
)
def update_source(
    warehouse_id: uuid.UUID,
    source_id: uuid.UUID,
    payload: DataSourceUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> DataSourceResponse:
    tenant = _require_tenant(ctx)
    _get_warehouse(db, tenant.id, warehouse_id)

    source = db.get(DataSource, source_id)
    if source is None or source.tenant_id != tenant.id or source.warehouse_id != warehouse_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")

    changed: dict[str, bool] = {}
    if payload.name is not None:
        source.name = payload.name.strip() or source.name
        changed["name"] = True
    if payload.config is not None:
        source.config = payload.config
        changed["config"] = True
    if payload.enabled is not None:
        source.enabled = payload.enabled
        changed["enabled"] = True

    write_audit_log(
        db,
        actor=ctx.user,
        action="warehouse.source.update",
        tenant_id=tenant.id,
        details={"source_id": str(source.id), "warehouse_id": str(warehouse_id), "fields": list(changed.keys())},
    )
    db.commit()
    db.refresh(source)

    return DataSourceResponse(
        id=source.id,
        tenant_id=source.tenant_id,
        warehouse_id=source.warehouse_id,
        name=source.name,
        source_type=source.source_type,
        config=source.config or {},
        enabled=source.enabled,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )
