# Logistik-modernisering — Analyse & Faseplan

> **Bemærk**: Denne plan er udelukkende dokumentation. Ingen kode skrives før du har godkendt planen.

---

## DEL 1 — Analyse: Container-delen vs. Logistik-delen

### Hvad fungerer godt på container-delen (mønstre vi vil have med)

| Mønster | Hvor det bruges i dag | Hvorfor det virker |
|---|---|---|
| **Rigtigt auth-flow** (`bcrypt`, JWT, ContextVar) | `LoginPage`, `SetPasswordPage`, `/api/auth/login` | Hver bruger har sin egen identitet → sporbarhed, ingen delt kode |
| **Invitations-flow med email** | `customer_admin` → `location_admin`, `order` brugere | Brugeren modtager link, sætter selv password (72h gyldighed) — ren UX, sikker, auditerbar |
| **Strict tenant-isolation via `ContextVar`** | `TenantAwareDB` wrapper, `current_company_id` | Garanti for ingen cross-tenant lækage |
| **Cross-company switcher** (`X-Acting-Company-Id`) | Logistics admin på container-delen | Skifter aktiv kontekst uden re-login |
| **Strict partner_id-binding** | Materialer, container-ordrer | Data lækker ALDRIG mellem partnere — beviste pattern |
| **`/api/plads` server-filtrering** | Order-medarbejder (`assigned_plads_ids`) | Backend afgør hvad du må se — frontend kan ikke snyde |
| **Shadcn UI + Tailwind + `sonner`** | Alle `pages/*.jsx` | Konsistent design-sprog, moderne komponenter |
| **`<ConfirmDialog>`** (erstatter `window.confirm`) | Alle nyere sletninger | Custom, brand-konsistent, ikke browser-låst |
| **ExcelJS rapporter + jsPDF** | LA/CA Rapport-tab | Professionel output med autofilter, frosne rækker |
| **`X-Acting-Company-Id` header** | Cross-tenant aktioner | Eksplicit, auditerbar, RBAC-håndhævet |

### Hvad logistik-delen mangler / hvor den halter

| Problem | Hvor | Konsekvens |
|---|---|---|
| **Delt "driver_code"** for ALLE chauffører + navne-picker | `auth/driver-name`, `system_settings.driver_code` | Ingen sporbar identitet, kompromitteret kode rammer alle |
| **`drivers` er en SEPARAT collection** (ikke `users`) | `class Driver`, `db.drivers` | Egen autentificering, ingen invitations-flow, ingen email |
| **`plads`-collection er adskilt fra `locations`** | `db.plads` vs. `db.locations` | LA og kunde-admin skal oprette samme lokation to gange |
| **Tours fra container-bestillinger blandes med manuelle ture** | Begge i `db.tours`, ingen `source`-felt | Svært at filtrere, rapportere, slette korrekt |
| **Ingen kunde-vælger på chauffør-siden** | DriverPage viser blot `customer_name` som badge | Multi-kunde chauffør ser blandet liste; risiko for fejl-leverance |
| **Tour-delegering virker ikke korrekt** | `driver_id` sættes, men `GET /api/tours` filtrerer IKKE på det for andre chauffører | Pre-tildelt tur til chauffør A er synlig for chauffør B |
| **Driver-side UI sidder i App.js (~3000 linjer)** | `App.js` linje ~8430+ | Svær at vedligeholde, ikke i `/pages/` |
| **AdminPage (logistik admin) bruger gammel rød/hvid styling** | `App.js` linje ~3979 — ~7500 | Bryder visuelt med moderniseret container-side |
| **Ingen ConfirmDialog/sonner-konsistens** | Driver & Admin UI bruger `window.confirm` + `alert` | UI-inkonsistens, irriterende popups |
| **Plads opretter manuelt på logistik-siden** | AdminPage "Pladser"-fane | Duplikatarbejde med kunde admin |

---

## DEL 2 — Hvad SKAL bevares (kritisk)

Disse er resultater af **mange måneders arbejde**. De bevares 100% — eventuelt internt re-wired, men funktionel adfærd og data-format ændres ikke:

| Funktion | Lokation | Status efter modernisering |
|---|---|---|
| **Pro Receipt Scanner med OCR** (Tesseract.js — læser vægt, nummerplade, dato automatisk) | `App.js` `ProReceiptScanner`, `ReceiptScanner` | **Bevares uændret** — bruges fra mobile-tour-kortet |
| **Argo PDF/email import** | `POST /api/parse-argo`, `POST /api/import-argo`, `POST /api/parse-pdf` | **Bevares uændret** — flyttes til ny "Manuelle ture"-fane |
| **PDF dagsrapporter med løn-cyklus-gruppering** | `POST /api/pdf-archive`, `GET /api/pdf-archive` | **Bevares uændret** |
| **Rute-optimering m. auto-geocoding (DK_CITIES)** | `POST /api/optimize-route` | **Bevares uændret** — bruges fra både LA og driver |
| **MobileTourPanel** (mobile-first tur-kort + Google Maps-link) | `App.js` `MobileTourPanel` | **Bevares**, eventuel UI-pudsning |
| **Driver-arkivet / historikken** | `GET /api/driver-archive`, `GET /api/driver-archive/{name}` | **Bevares** — switches til `driver_id` (UUID) i stedet for navn |
| **Push notifications for haster** | `POST /api/push/subscribe`, `_auto_push_haster` | **Bevares uændret** |
| **Driver chat (iMessage-style)** | `messages`-collection | **Bevares**, men `from_driver_name`/`to_driver_name` → `from_user_id`/`to_user_id` |
| **Container orders → automatisk tour** (via `order_id`) | `POST /api/customer-orders/submit` → tour-mirror | **Bevares uændret** — kun ny `source: "customer_order"` flag |
| **Daily overview KPIs** | `GET /api/daily-overview` | **Bevares**, opdateres til kunde-scoped |
| **Manual tour creation** + bulk + Excel import | `POST /api/tours`, `POST /api/tours/bulk` | **Bevares**, flyttes til ny "Manuelle ture"-fane |
| **Cross-company switcher** for logistics_admin | Allerede implementeret via `X-Acting-Company-Id` | **Bevares**, genbruges som "Kunde-vælger" |
| **Self-claim logik** (`claimed_by`, `claimed_by_id`) | `PUT /api/tours/{id}` med claim | **Bevares som grundlag** — pre-assignment bygges ovenpå |
| **Receipt OCR storage + viewer** | `POST /api/receipts`, `ReceiptList`, `ReceiptViewer` | **Bevares uændret** |

---

## DEL 3 — Faseplan (8 faser, testbare i isolation)

Hver fase er testbar selvstændigt. Vi bygger og verificerer fase for fase. Du tester efter hver fase før vi går videre.

### **Fase 1 — Sikker database-nulstilling af logistik-data**

**Mål**: Tøm alle logistik-relaterede collections uden at røre container-siden. Audit, dry-run, derefter wipe.

- Nyt script: `/app/scripts/wipe_logistics_data.py`
  - **Sletter**: `drivers` (gamle), `tours`, `reports`, `receipts`, `pdf_archives`, `driver_sessions`, `push_subscriptions`, `messages`, `tour_prices`, `genbrug_orders`, `container_counts`
  - **Sletter**: `users` hvor `role == "driver"`
  - **Sletter**: `invitation_tokens` knyttet til drivers
  - **Rydder**: `order_id`-links og `tour_id`-felter i `container_orders` (de bliver "ikke leveret endnu")
  - **BEVARER**: alle `companies` (logistik + kunde), `locations`, `holiday_calendars`, `holiday_deltas`, `material_calendars`, `hours_calendars`, `delivery_addresses`, `workshops`, `delta_notifications`, `capacity_measures`, `container_orders` (selve ordrerne), `location_groups`, `holiday_groups`, alle non-driver `users`
  - **Dry-run flag**: `--dry-run` viser hvad der ville blive slettet uden at gøre det
  - **Confirmation prompt**: Kræver at skrive `WIPE LOGISTICS` for at fortsætte
  - **Pre-flight check**: Tæller dokumenter før/efter, advarer ved orphans

**Test**: Dry-run viser præcis hvad der slettes. Faktisk kørsel → container_orders findes stadig, men har ingen tour_id. Genbrug, locations, kunder, materialer er intakte.

---

### **Fase 2 — Chauffør-login via rigtigt invitations-flow**

**Mål**: Erstat shared driver_code med email+password via eksisterende invitation-flow.

#### Backend
- Udvid `invite_only_roles = {"location_admin", "order", "driver"}` i `/api/org/users` (eller dedikeret driver-endpoint).
- `POST /api/drivers` (logistics_admin):
  - Input: `{name, email, plate (optional), phone, area, facility}`
  - Opretter `users`-row med `role="driver"`, `company_id=caller.company_id`
  - Genbruger eksisterende `_send_invitation_email` → driver modtager link til `/set-password`
  - Returnerer `Driver`-shape (compat mapping)
- `GET /api/drivers` → returnerer `users` med `role="driver"` mappet til Driver-shape (bagudkompatibilitet)
- `PUT /api/drivers/{id}`, `DELETE /api/drivers/{id}` → tilsvarende
- Driver login = standard `POST /api/auth/login` (email+password)
- Gamle endpoints `POST /api/auth/driver-name`, driver_code-system settings → markeres `deprecated`, returnerer 410 Gone

#### Frontend
- `LoginPage` (eksisterende) håndterer driver-login automatisk (samme endpoint, RoleRouter sender til DriverPage)
- Efter login → DriverPage. Plate-vælger (nummerplade) forbliver som separat trin (kan gemmes i `users.plate` eller pr. session)
- Fjern shared-code felt fra AdminPage "Indstillinger"-fane

**Test**:
- LA opretter chauffør → email sendes → chauffør sætter password → logger ind → ser DriverPage
- Pytest: invitation token er 72h gyldig, kun én gang brugbar
- Pytest: gammelt driver-name endpoint returnerer 410

---

### **Fase 3 — Genbrugspladser er auto-genereret fra kundens lokationer**

**Mål**: Ingen manuel oprettelse på logistik-siden. Kunde-admin = single source of truth.

#### Backend
- `GET /api/plads` (allerede tenant-aware) udvides for **logistics_admin + driver**:
  - Returnerer UNION af:
    1. `locations` fra kunder hvor `logistics_partner_ids` indeholder caller's logistik-firma
    2. Ad-hoc `plads` i logistik-firmaets egen kontekst (sjælden, fx Argo-special)
  - Felter normaliseret til Plads-shape (`name`, `location_code`, `city`, `address`, `lat`, `lng`)
- `POST /api/plads` blokeres for logistics_admin (return 405 med besked: "Pladser oprettes af kunde-admin")
  - Undtagelse: `is_ad_hoc=true` for legacy Argo-tur-pladser
- Eksisterende `plads`-rækker bevares (read-only legacy)

#### Frontend
- AdminPage "Pladser"-fane → bliver read-only liste, viser badge: "Fra kunde: ARGO / Helsingør Forsyning"
- Knap "Tilføj ad-hoc plads" gemmes bag en "Avanceret" toggle (sjælden brug)
- Driver UI bruger samme unified `/api/plads`

**Test**:
- Kunde admin opretter lokation "Boliggården" → automatisk synlig på logistik admin pladser-tab
- Chauffør logget ind hos ILK ser pladser fra både Helsingør Forsyning OG ARGO (hvis ILK serves begge)
- Pytest: forsøg på `POST /api/plads` som logistics_admin → 405

---

### **Fase 4 — Adskillelse: Manuelle ture vs. Bestillinger**

**Mål**: To separate sektioner på logistik admin siden — ikke blandet sammen.

#### Backend
- Tilføj `source` felt til Tour model: `"manual" | "argo" | "customer_order"` (default `"manual"`)
- `customer_orders/submit` → opretter tour med `source="customer_order"` (eksisterende mirror-logik beholdes, blot tagget)
- `parse-argo` + `import-argo` → opretter tours med `source="argo"`
- Manuelle `POST /api/tours` → `source="manual"` (default)
- `GET /api/tours` → tager `?source=` query-parameter

#### Frontend
- AdminPage: ny tab-struktur:
  - **"Ture"** (eksisterende, kan slettes/erstattes) splittes til to:
    - **"Manuelle ture"** → kun `source ∈ {"manual", "argo"}`. Indeholder "Tilføj tur", "Import Argo", "Import PDF", "Bulk import"
    - **"Bestillinger"** → kun `source="customer_order"`. Read-only feed med metadata (hvilken kunde, lokation, opgavetype, kommentar, haster-status, hvem oprettede ordren)
- Driver-siden viser begge typer i samme liste (sorteret), MEN med visuel skelnen — badge: "Bestilling" vs "Manuel" vs "Argo"

**Test**:
- LA opretter manuel tur → kun synlig under "Manuelle ture"
- Medarbejder bestiller container → tur dukker op under "Bestillinger"
- Chauffør ser begge i sin liste, med korrekte badges

---

### **Fase 5 — Multi-kunde adskillelse på chauffør siden (SIKKERHEDSKRITISK)**

**Mål**: Stram isolation pr. kunde, præcis som tenant-isolation. Nul lækage.

#### Backend
- Driver session udvides med `current_customer_id` felt (gemmes i `driver_sessions` collection)
- `POST /api/driver/active-customer`:
  - Input: `{customer_id}`
  - Verificerer: caller er `role=driver`, caller's `company_id` har `customer_id ∈ assigned_logistics_company_ids` for den lokation/kunde
  - Gemmer i session
- `GET /api/tours` for driver:
  - Hvis `current_customer_id` er sat: tilføj `{"company_id": current_customer_id}` til query
  - Hvis ikke sat: returnerer tom liste + 428 "Vælg kunde først"
- `GET /api/plads` for driver: filtreres tilsvarende
- `GET /api/driver-archive` for driver: filtreres tilsvarende
- **Re-validering ved hver request**: caller's company stadig serves customer (hvis kunde-adskillelse fjernes mellem requests, lukker adgangen)

#### Frontend
- DriverPage:
  - Efter login + plate-valg: **Kunde-vælger** (ligner PladsPickerPage). Viser kun kunder hvor driver's company er `assigned_logistics_company_id`
  - Header-dropdown "Kunde": ARGO ↓ — switcher omgår login-flow
  - Ved switch: clear tour-liste, fetch frisk
  - Visuel indikator (badge / farve) viser hvilken kunde der vises lige nu
- LA's eksisterende cross-company switcher (`X-Acting-Company-Id`) genbruges som "Kunde-vælger" på AdminPage

**Test (kritisk)**:
- Driver fra ILK serves både ARGO + Helsingør F. Vælger ARGO som aktiv kunde.
  - `GET /api/tours` returnerer KUN ARGO's ture, INTET fra Helsingør F.
  - `GET /api/plads` returnerer KUN ARGO-pladser.
- Pytest: forsøg på direkte API-kald med en ikke-served customer_id → 403
- Pytest: switching customer mid-session → fuldstændig data-reset, ingen residual

---

### **Fase 6 — Tur-delegering: pre-assignment + self-claim** ✅ DONE (iteration_49)

**Mål**: LA kan pre-tildele. Pre-tildelte ture er privat. Andre er åbne for self-claim.

#### Backend
- Tour visibility-regler i `GET /api/tours` for driver:
  - Pre-assigned (`driver_id` sat): synlig KUN for den driver (`driver_id == caller.id`)
  - Ikke-assigned (`driver_id` tom): synlig for alle drivers i den serving logistik-firma
  - Allerede claimed (`claimed_by_id` sat): synlig for alle, men markeret som taget
- Driver `PUT /api/tours/{id}`:
  - Driver MÅ KUN sætte `claimed_by_id = self.id`, aldrig `driver_id`
  - Driver MÅ IKKE sætte `claimed_by_id` til en anden driver
  - Pre-assigned tur kan kun "frigives" af logistics_admin (sætter `driver_id = ""`)
- LA `PUT /api/tours/{id}`:
  - MÅ sætte `driver_id` til en hvilken som helst driver i sin company

#### Frontend
- LA AdminPage:
  - Hver tur-række får dropdown "Tildel til chauffør → [Liste over drivers]"
  - Eller knap "Frigiv" som rydder driver_id
- Driver UI:
  - Pre-assigned ture får badge "Tildelt mig" (grøn) — kan ikke fortrydes uden LA
  - Andre ture vises som normalt, med "Tag denne tur"-knap (claim)
  - **Ingen mulighed for at give væk til anden chauffør** (UI'et eksponerer det ikke; backend afviser hvis nogen prøver via API)

**Test (kritisk)**:
- LA pre-tildeler tur til driver A. Driver B logger ind hos samme kunde. Driver B's `GET /api/tours` → tur er IKKE i listen. Driver A's liste → tur ER der med "Tildelt mig"-badge.
- Driver A forsøger via direct API-kald at sætte `driver_id` til B → 403
- Driver A self-claims en åben tur → success, claimed_by_id == A.id
- Pytest: alle ovenstående cases dækket

---

### **Fase 7 — UI-modernisering: Logistik admin + Driver UI til container-niveau**

**Mål**: Visuel ensartethed med container-siden. Bevarer adfærd 100%.

- Migrer AdminPage til ny page-fil: `/app/frontend/src/pages/LogisticsAdminPage.jsx`
  - Tailwind + Shadcn cards/tabs/buttons
  - Sonner toasts (erstatter alle `toast.error/success` med `sonner`-stil)
  - `<ConfirmDialog>` overalt (erstatter `window.confirm`)
  - Samme farvepalet (orange/slate-baseret) som LocationAdminPage
  - Tab-struktur:
    1. Overblik (dashboard KPIs)
    2. Manuelle ture
    3. Bestillinger (read-only feed)
    4. Pladser (read-only union)
    5. Chauffører
    6. Skema
    7. Statistik & Rapporter
    8. Arkiv (PDF)
    9. Priser
    10. Indstillinger (push, integrations)
- Migrer DriverPage til `/app/frontend/src/pages/DriverPage.jsx`
  - Tailwind + Shadcn, men bevarer MobileTourPanel struktur
  - Kunde-vælger i header (analogi til Logistik-partner-switcher)
  - Same data-testid coverage som container-siden (for testing-agent)

**Test**:
- Visuel sammenligning: side om side. Brug screenshots.
- Smoke test af alle eksisterende funktioner: OCR, route-opt, archive download, push.
- Testing agent (frontend) verificerer alle flows fortsat virker.

---

### **Fase 8 — Regression-testing + komplet end-to-end**

**Mål**: Fuld dækning af nye + gamle features. Klar til produktion.

- Pytest suite:
  - `test_driver_invitation_flow.py` (Fase 2)
  - `test_plads_unification.py` (Fase 3)
  - `test_tour_source_separation.py` (Fase 4)
  - `test_driver_customer_isolation.py` (Fase 5 — SIKKERHED)
  - `test_tour_pre_assignment.py` (Fase 6 — SIKKERHED)
  - `test_ocr_route_archive_smoke.py` (bevarede features)
- Frontend testing agent kørsel: hele logistik-flow fra LA-invite → driver login → tour pickup → completion → archive
- Manuel smoke-test af visuel kvalitet

---

## DEL 4 — Bonus-forslag (ikke nævnt i din brief, men hører naturligt med)

Her er ting jeg synes hører naturligt med, baseret på den røde tråd. Sig til hvis du vil have dem inkluderet:

| Forslag | Rationale | Fase |
|---|---|---|
| **Driver-status "Online/Offline"** | LA kan se hvem der er aktiv lige nu (vigtigt for haster-tildeling) | 7 |
| **Real-time tour-status mirror til ordre-historik** | Når chauffør markerer "completed" → kunde-medarbejderens "Mine bestillinger" opdateres øjeblikkeligt | 5 |
| **Geografisk gruppering af pladser** (efter postnummer-zone) | Hjælper rute-optimering når flere pladser tilhører samme zone | 3 |
| **Driver-permissions niveau** (junior/senior) | Junior chauffører ser kun ikke-hastere ture. Senior får haster-push. | 7 |
| **PWA install prompt** for chauffører (allerede halvt på plads) | "Add to home screen" guide ved første login | 7 |
| **Lokation-foto pr. plads** (vist for chauffør) | "Kontainer ligger bagerst — se foto" — reducerer kald | 3 |
| **Audit log på pre-assignment** | "LA Jens tildelte tur X til chauffør Maria kl. 14:32" — sporbarhed ved tvist | 6 |
| **Driver "uddelegér"-anmodning** | Chauffør kan IKKE selv give væk, men kan sende anmodning til LA om at give videre | 6 (alternativ) |
| **Excel-eksport af driver-arkiv** | Konsistens med container-siden's rapporter (ExcelJS) | 7 |

---

## DEL 5 — Risikolog

| Risiko | Sandsynlighed | Mitigation |
|---|---|---|
| Brud på OCR/Tesseract under UI-flytning | Lav | Pakker isoleres som komponent; smoke-test før hver fase commit |
| Tur-data tabt under nulstilling | Lav (men højeste impact) | Dry-run obligatorisk; pre-wipe snapshot dump til `/app/backups/pre-wipe-{timestamp}.json` |
| Driver mister adgang under invitation-rollout | Medium | Behold gammelt login parallelt i Fase 2; deprecate først efter Fase 8 |
| Cross-kunde leakage på chauffør-siden | Højest impact | Eksplicit pytest med adversarielt direct-API-kald; Fase 5 har sin egen audit |
| Argo/PDF parser brækker når tour source-flag tilføjes | Lav | Default `source="argo"` ved import; eksisterende felter uberørte |
| Push subscriptions går tabt ved driver-konvertering | Lav | Migration-script overfører `push_subscriptions` fra `driver_name` til `user_id` |

---

## DEL 6 — Anbefalet rækkefølge med checkpoints

```
Fase 1 (Wipe) → DU TESTER (kontrollér container-data intakt)
  ↓
Fase 2 (Driver auth) → DU TESTER (opret driver, modtage email, login)
  ↓
Fase 3 (Plads union) → DU TESTER (lokation oprettet på kundeside vises på logistik)
  ↓
Fase 4 (Tour separation) → DU TESTER (manuelle vs. bestillinger adskilt)
  ↓
Fase 5 (Kunde-isolation) → JEG KØRER FULD PYTEST (sikkerhed) → DU TESTER UI
  ↓
Fase 6 (Pre-assignment) → JEG KØRER FULD PYTEST (sikkerhed) → DU TESTER UI
  ↓
Fase 7 (UI modernisering) → testing-agent + visuel review → DU TESTER
  ↓
Fase 8 (Regression) → fuld testsuite, klar til prod
```

Jeg foreslår vi tager faserne én ad gangen — bygger, tester (jeg først, så dig), og rykker videre kun når begge er enige.
