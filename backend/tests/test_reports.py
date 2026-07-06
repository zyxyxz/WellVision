from __future__ import annotations

import os
import types
import unittest
import uuid

os.environ.setdefault("SECRET_KEY", "test-secret-key-with-enough-length")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test")
os.environ.setdefault("OBJECT_STORE_BUCKET", "wellvision-test")

from fastapi import HTTPException

from app.models import ReportStatus
from app.services.reports import approve_report, reject_report, submit_for_review


class _Db:
    def __init__(self) -> None:
        self.flushed = False

    def flush(self) -> None:
        self.flushed = True


def _ctx(*, roles: list[str], platform_admin: bool = False):
    return types.SimpleNamespace(
        tenant=types.SimpleNamespace(id=uuid.uuid4()),
        user=types.SimpleNamespace(id=uuid.uuid4(), is_platform_admin=platform_admin),
        roles=roles,
    )


def _report(status: str):
    return types.SimpleNamespace(
        status=status,
        review_comment=None,
        reviewed_by_user_id=None,
        published_at=None,
    )


class ReportWorkflowTests(unittest.TestCase):
    def test_submit_for_review_requires_edit_role(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            submit_for_review(_Db(), ctx=_ctx(roles=["tenant_viewer"]), report=_report(ReportStatus.draft.value))

        self.assertEqual(raised.exception.status_code, 403)

    def test_reviewer_can_approve_in_review_report(self) -> None:
        db = _Db()
        report = _report(ReportStatus.in_review.value)
        ctx = _ctx(roles=["tenant_reviewer"])

        approve_report(db, ctx=ctx, report=report, comment="ok")

        self.assertTrue(db.flushed)
        self.assertEqual(report.status, ReportStatus.published.value)
        self.assertEqual(report.review_comment, "ok")
        self.assertEqual(report.reviewed_by_user_id, ctx.user.id)
        self.assertIsNotNone(report.published_at)

    def test_reject_clears_published_timestamp(self) -> None:
        db = _Db()
        report = _report(ReportStatus.in_review.value)
        report.published_at = object()

        reject_report(db, ctx=_ctx(roles=["tenant_admin"]), report=report, comment="revise")

        self.assertTrue(db.flushed)
        self.assertEqual(report.status, ReportStatus.rejected.value)
        self.assertEqual(report.review_comment, "revise")
        self.assertIsNone(report.published_at)


if __name__ == "__main__":
    unittest.main()
