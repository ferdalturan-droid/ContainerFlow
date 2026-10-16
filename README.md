# ContainerFlow

Multi-tenant platform for Danish container/recycling logistics. Recycling sites
(genbrugspladser) order container pickups; logistics partners' drivers run the tours.
Live at containerflow.dk.

## Stack
- **Backend:** FastAPI + MongoDB (motor) — `backend/server.py` (main app, ~280 endpoints),
  `backend/auth.py` (JWT + tenant context), `backend/email_service.py` (Resend),
  `backend/ocr_service.py` (receipt OCR, Google Vision).
- **Frontend:** React 19 + Tailwind + shadcn/ui, installable PWA — `frontend/src/App.js`
  (order flow, driver UI, logistics admin) and `frontend/src/pages/` (one page per role).

## Roles
`super_admin` → `customer_admin` → `location_admin` → `order`, and
`logistics_admin` → `driver` (plus legacy `genbrug_plads`). See `HIERARCHY_SPEC.md`.

Tenant isolation: a `TenantAwareDB` wrapper injects `company_id` into every query on
tenant-scoped collections. Logistics companies see the customers listed in their
`serves_company_ids`.

## Docs in this repo
| File | What |
|---|---|
| `memory/PRD.md` | Full changelog of every phase/iteration (newest at the top) |
| `memory/LOGISTIK_MODERNISERING_PLAN.md` | Logistics rework plan (phases 1–8) |
| `HIERARCHY_SPEC.md` | Account hierarchy, scoping rules |
| `LOGISTICS_TIERS.md` | Premium vs. partner logistics firms - what applies where |
| `PRICING_SPEC.md` | Økonomi: price rules, time, holidays, approvals |
| `WORKFLOW.md` | Daily commands: local test, deploy, GitHub |
| `DEPLOY_SCALEWAY.md` | Migration from Emergent to Scaleway |
| `deploy/README.md` | Self-hosted VPS + nginx setup |
| `scripts/README.md` | MongoDB backups to Google Drive |
| `data-migration/README.md` | Restoring a database dump to production |

## Running
Backend reads `MONGO_URL` etc. from `backend/.env` (not committed). Tests live in
`backend/tests/` (pytest). Docker image: `Dockerfile`.
