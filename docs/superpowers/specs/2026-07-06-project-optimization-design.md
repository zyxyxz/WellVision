# WellVision Project Optimization Design

Date: 2026-07-06

## Goal

Optimize WellVision in three ordered passes: engineering quality first, product workflow second, production readiness third. The work must keep the current FastAPI + React architecture intact, avoid broad rewrites, and produce changes that can be verified locally before pushing to GitHub.

## Current Architecture

The backend is a FastAPI application with SQLAlchemy models, PostgreSQL/Timescale-ready storage, object storage via S3-compatible APIs, tenant-scoped JWT authentication, import jobs, analysis algorithms, AI report generation, and report review state. The frontend is a Vite React application using Ant Design, route-level lazy loading, axios API wrappers, and pages for data, projects, algorithms, analysis, drill replay, reports, and admin. Deployment uses Docker Compose, Dokploy-oriented compose, Nginx, and PM2.

## Phase A: Engineering Quality

Add low-friction quality entry points and focused tests around existing behavior. The backend should gain a lightweight test setup that can run without a live database for pure functions and FastAPI dependency-independent behavior. The frontend should gain a typecheck script in addition to the existing production build. Existing behavior should be protected before refactoring.

Refactoring should target clear risk areas only: repeated role/report review logic, oversized analysis responsibilities, and scattered environment/security assumptions. The goal is smaller reviewable modules, not a full architecture rewrite.

## Phase B: Product Experience

Close the human-review workflow by replacing the `/review` placeholder with a real review queue for submitted reports. The page should let reviewers inspect report content, approve it, or reject it with a comment. It should reuse existing reports APIs and role context rather than introducing a new backend surface.

Improve login and operational messaging by avoiding production-default demo credentials and surfacing clearer request failures where touched. Large visual redesign is out of scope for this pass.

## Phase C: Production Readiness

Document and harden the operational path without risky infrastructure replacement. Clarify environment requirements, object storage CORS needs, schema evolution expectations, AI provider settings, and import-worker deployment caveats. Reduce worker duplication risk in common multi-worker deployments where possible.

Tenant isolation remains application-enforced in this pass, but critical paths should have tests or explicit guards. A full PostgreSQL RLS migration and an external task queue migration are deferred because they require production data and deployment coordination.

## Verification

The work is complete when these checks pass:

- Backend Python syntax compilation.
- Backend focused tests.
- Frontend TypeScript typecheck.
- Frontend production build.
- Git status reviewed before commit.
- Commit message follows the Lore commit protocol.
- Push to `origin/main` succeeds.

## Non-Goals

- No large UI redesign.
- No new heavy runtime dependency unless required to make tests or existing tools run.
- No destructive database migration.
- No replacement of the current deployment platform.
- No secret rotation or production data changes from this workspace.
