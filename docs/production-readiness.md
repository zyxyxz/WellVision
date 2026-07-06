# WellVision Production Readiness Notes

This project can run as a single FastAPI backend, React/Nginx frontend, PostgreSQL database, and S3-compatible object store. Before production traffic, verify the items below.

## Required Environment

- `SECRET_KEY` must be a strong random value with at least 16 characters.
- `DATABASE_URL` must point to PostgreSQL. TimescaleDB is optional but recommended for large time-series workloads.
- `OBJECT_STORE_BUCKET` plus provider credentials must point to an S3-compatible bucket.
- `BOOTSTRAP_ADMIN_PASSWORD` must be changed from `ChangeMe123!` whenever `ENV=production`.
- `CORS_ALLOW_ORIGINS` should contain only trusted frontend origins.
- `OPENAI_API_KEY` or platform `ai_config` is required only when AI reports or chat are enabled.

## Object Storage

Large file uploads use multipart presigned URLs. The object store CORS policy must allow browser `PUT` requests and expose `ETag`; otherwise multipart completion cannot collect part hashes.

Recommended exposed headers:

```text
ETag
```

Recommended allowed methods:

```text
GET, HEAD, PUT, POST
```

## Import Worker

The backend starts an in-process import worker when `IMPORT_WORKER_ENABLED=true`. This is acceptable for a single backend process, but multi-process or multi-replica deployments can increase import concurrency. For production scale, run exactly one importer role or migrate the import loop to an external queue worker such as Celery or RQ.

The current code prevents duplicate worker startup inside one Python process, but it cannot prevent multiple separate backend processes from each starting their own workers.

## Schema Evolution

`AUTO_CREATE_SCHEMA=true` creates tables and applies conservative additive schema patches at startup. This is convenient for development and early deployments, but production changes should be promoted through reviewed migration scripts before destructive or constraint-changing database work.

Use these checks before release:

```bash
bash scripts/verify.sh
```

For database changes, also run a restore rehearsal against a recent backup before applying changes to production.

## Tenant Isolation

Current tenant isolation is enforced at the application query layer with `tenant_id` filters and tenant-context validation. Keep tests around every new tenant-scoped query path. PostgreSQL RLS is the recommended next hardening step once production data ownership and migration windows are confirmed.
