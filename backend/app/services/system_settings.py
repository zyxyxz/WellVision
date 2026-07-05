from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SystemSetting


def get_setting(db: Session, key: str) -> SystemSetting | None:
    return db.get(SystemSetting, key)


def get_setting_value(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(SystemSetting, key)
    if row is None:
        return default
    return row.value_json or default


def upsert_setting(db: Session, *, key: str, value: dict, updated_by_user_id=None) -> SystemSetting:
    row = db.get(SystemSetting, key)
    if row is None:
        row = SystemSetting(key=key, value_json=value, updated_by_user_id=updated_by_user_id)
        db.add(row)
    else:
        row.value_json = value
        row.updated_by_user_id = updated_by_user_id
    db.flush()
    return row
