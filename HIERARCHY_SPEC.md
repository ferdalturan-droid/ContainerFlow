# ContainerFlow — 5-Level Account Hierarchy (Architecture Spec)

This document describes the multi-level org structure implemented in this codebase.
It is the source of truth for how accounts, roles, isolation and the "who-creates-whom"
delegation works. Read this before extending the org logic.

## The five login experiences

| # | Role (code)       | Who              | Belongs to            | Creates / manages below                                  |
|---|-------------------|------------------|-----------------------|----------------------------------------------------------|
| 1 | `super_admin`     | System owner (you) | platform (company `*`) | customer orgs + logistics orgs, and each org's first admin |
| 2 | `customer_admin`  | e.g. Jørgen / ARGO | a **customer** company | locations, location admins, logistics-partner link        |
| 3 | `location_admin`  | e.g. KØGE site lead | one location in a customer company | employees (order users) + containers for that location |
| 4 | `order`           | site employee     | one location           | places container-pickup orders                            |
| 5 | `logistics_admin` | e.g. ILK super    | a **logistics** company | drivers + trucks, driver login accounts                  |
| 5 | `driver`          | ILK driver        | a logistics company    | drives by system suggestion, scans receipts               |

`genbrug_plads` (legacy reporting role) is kept for backward compatibility and maps
conceptually to customer_admin (HQ) / location_admin (site) reporting views.

## Org model

A `company` now has a **`company_type`**:
- `customer`  — buys the service (ARGO, MARTO). Has locations + employees inside it.
- `logistics` — provides the trucks/drivers (ILK). Serves one or more customers.
- (`default` company keeps `company_type="customer"`.)

**Locations are sub-units _inside_ a customer company** (recommended design — keeps each
customer's data unified so the customer_admin sees all sites at once). A location is the
existing `locations` collection (a 4-digit `code`, a `name`, a `company_id`). Tours/orders
are scoped by `company_id` (the customer) and, for site-level users, by location.

### The customer ↔ logistics partnership

Implemented with the existing **`serves_company_ids`** on the logistics company.
When ARGO's customer_admin "adds logistics partner ILK", the platform adds ARGO's
`company_id` to `ILK.serves_company_ids`. Result: ILK's drivers/admin see ARGO's tours
(read-merged). Add MARTO too → ILK serves `[ARGO, MARTO]` and a driver sees **both**
customers as options at login. Writes still go to each customer's own company.

## Scoping / who-can-create-what (enforced server-side)

All delegated actions live under the `/api/org/*` router and are checked against the
caller's role + company + location. The UI is never trusted.

- **super_admin**: anything (company `*` bypass).
- **customer_admin** (company = ARGO):
  - create/list/update locations where `company_id == ARGO`.
  - create users with role in {`location_admin`, `order`} where `company_id == ARGO`.
  - link/unlink a logistics partner → edits that logistics company's `serves_company_ids`
    to include/exclude ARGO; may create the logistics company's first `logistics_admin`.
  - cannot touch another customer, another customer's locations, or ILK's internals.
- **location_admin** (company = ARGO, location = KØGE):
  - create users with role `order` bound to their own location.
  - manage containers/materials for their location.
  - sees only their location's data.
- **logistics_admin** (company = ILK):
  - create `driver` users + trucks in ILK.
  - sees tours merged across every customer in `ILK.serves_company_ids`.

Permission helper: `require_org_scope(...)` in `backend/server.py` resolves the caller's
company/location from the JWT and rejects out-of-scope writes with 403.

## Data isolation (unchanged core)

`TenantAwareDB` still auto-injects `company_id` on every tenant-collection query
(`current_company_id` ContextVar set by `TenantContextMiddleware` from the JWT).
- customer users → scoped to their customer `company_id`.
- logistics users → scoped to their own `company_id`, with read-merge across
  `serves_company_ids` (the partner customers).
- location-level users additionally filtered by location (`location_code` /
  `assigned_plads_ids`) at the endpoint level.

## New backend surface (added in this change)

- `Company.company_type` (+ `CompanyCreate.company_type`, `CompanyUpdate.company_type`).
- `auth.VALID_ROLES` += `customer_admin`, `location_admin`.
- `User` already carries `company_id`, `location_code`, `assigned_plads_ids`,
  `managed_company_ids`, `is_hq_admin` — reused for scoping.
- Router `org_router` (`/api/org`):
  - `GET/POST/PUT/DELETE /api/org/locations`
  - `GET/POST /api/org/users`  (role-gated by what the caller may create)
  - `GET /api/org/logistics-companies`  (customer_admin: list logistics orgs to partner with)
  - `POST /api/org/logistics-partners`  (link ILK to my customer org + optionally create ILK admin)
  - `DELETE /api/org/logistics-partners/{logistics_company_id}` (unlink)
- `super_admin` quick-setup extended: choose `company_type`; first admin role is
  `customer_admin` for customer orgs, `logistics_admin` for logistics orgs.

## New frontend surface

- Routing in `App.js`: `customer_admin` → `CustomerAdminPage`; `location_admin` → `LocationAdminPage`.
- `CustomerAdminPage.jsx`: locations CRUD, location-admin creation, logistics-partner linking,
  link to reports (reuses `GenbrugPladsPage` / `PrijsPage`).
- `LocationAdminPage.jsx`: employees (order users) + containers for the site, place orders,
  site report.
- `SuperAdminPage.jsx` quick-setup: company_type selector (Customer / Logistics).

## Build order (phases)

1. **Backend foundation** — company_type, roles, org_router with permission checks. (done)
2. **System-owner flow** — create customer/logistics orgs + first admin. (done)
3. **Customer admin** — locations + location admins + logistics linking. (done)
4. **Location admin** — employees + containers + orders. (done)
5. **Polish** — DONE: per-company `haster_fee` (Company.haster_fee, falls back to legacy
   global), audit-log entries on every delegated create/link (`activity_log`, actions
   `org_company_created`, `org_location_created`, `org_user_created`, `org_user_deleted`,
   `org_logistics_linked`, `org_logistics_unlinked`), and location-scoped reporting for
   location_admin via the orders-by-location view. Remaining optional: rate-limit org
   writes, and a dedicated location-filtered tour report (today location admins use the
   orders view which is already location-scoped).

## Notes for Emergent (the builder)

- Everything is additive and backward-compatible; existing roles/screens still work.
- The permission tree is the security-critical part — keep the server-side `require_org_scope`
  checks; never rely on the React UI to hide options.
- `serves_company_ids` is the join table for customer↔logistics; a driver serving two
  customers is just two IDs in that list.
- Suggested next hardening: per-company `haster_fee` (today it is a single global setting),
  and audit-log entries on every delegated create/link.
