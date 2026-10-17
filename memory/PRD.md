# ContainerFlow Multi-Tenant Extension - PRD

## Original problem statement
Extend the existing ContainerFlow logistics platform (Danish container/recycling logistics)
into a multi-company (multi-tenant) system WITHOUT rebuilding or breaking any existing
functionality. Add: single unified login page, JWT-based auth, role-based access,
super-admin management panel, and a new "Genbrug Plads" (recycling depot) role/page.
Data must be strictly isolated per company.

## Architecture decisions
- **Tenant isolation**: ContextVar-based per-request `company_id` + a `TenantAwareDB`
  wrapper around motor that auto-injects `company_id` into every find / insert / update /
  delete on tenant-scoped collections. Existing endpoints required ZERO changes.
- **Auth**: JWT bearer token (24h expiry), bcrypt password hashing.
- **Roles**: `super_admin`, `logistics_admin`, `driver`, `order`, `genbrug_plads`.
- **Backward compat**: Existing data migrated to `company_id="default"` on startup.
  Legacy admin password (`ilk2026`) and driver code (`3030`) still work.
- **Public bypass**: `/api/auth/login`, `/api/locations/code/{code}`, `/api/customer-orders/submit`
  and `/api/health` bypass tenant filtering so the QR-code customer flow continues to work.

## What's been implemented (2026-02-15)
## What's new in 2026-10-17 (Gods/container, Ny tur v2, chauffør v2, push)
- **Turtyper:** `tour_kind` er "container" eller "goods". Gods findes kun på premium-firmaets egne lokationer; B2B og partner er altid container (`_normalize_tour_doc`).
- **Nye felter:** strukturerede adresser (`address_parts`/`facility_parts`), `trailer_count` og `cargo_lines` (indhold pr. hænger). Vægt pr. læs gemmes i `container_weights` og summeres.
- **Ny tur v2:** Flere detaljer, by og postnummer (Datafordeler-liste i `frontend/src/data/postnumre.json`), kunderegister, aftalt pris med ventetid oveni.
- **Prisregler:** betingelsen "Antal hængere"; aftalt pris har `label` og `add_waiting`.
- **Chauffør v2:** `components/DriverTodayView.jsx` med fanerne Mine/Ledige/Færdige og nye kort. Profilen har kunde, vogn, hænger, notifikationer og log ud.
- **Push genaktiveret** (ophæver Fase 15.23b efter ønske):
  - Hændelser: tildeling, besked, ændring, aflysning, og haster til chauffører der har stemplet ind.
  - Chaufføren kan slå det fra.
  - VAPID-nøgle i PEM eller rå form (`_vapid_key`).
  - `/push/send` kræver nu login.
- **Koordinatorer:** kan begrænses til bestemte kunder (`customer_scope`).
- **Rettelser:** `fraction` er valgfri i TourCreate (kan komme fra `cargo_lines`). Vægt pr. læs kan rettes efter afslutning. Hænger er forvalgt, når turen har planlagte hængere.

## What's new in 2026-10-17 (Koordinatorer, prisversioner, Ring planlægger)

Se `TEAM_RETTIGHEDER.md`, `PRICING_SPEC.md` §3b og `LOGISTICS_ROADMAP.md` (svar A–F).
- **Koordinatorer**: logistik admin inviterer koordinatorer (role logistics_admin +
  is_coordinator) med 13 rettigheder; håndhæves centralt i TenantContextMiddleware.
  Ny side Mere › Team & rettigheder (`pages/TeamPanel.jsx`). Faner/knapper skjules.
- **Prisversioner**: ændring af prisregel = ny version fra nu/dato (eller
  bagudrettet). Ture prisberegnes med versionen gældende ved `created_at`.
  "Stop fra nu" i stedet for slet. Historik pr. regel.
- **Aftalt pris** i Ny tur (price_override fast, kræver "Ændre priser").
- **Ring til planlæggeren** for chauffører (tildeler → disponent-telefon).

## What's new in 2026-10-16 (Ture-arbejdsflade, tur-beskeder, live Rapportering)

Se `TURE_REDESIGN.md` og `LOGISTICS_ROADMAP.md`.
- **Ture** (ny startfane for logistik admin, `pages/ToursWorkspace.jsx`) erstatter
  Manuelle ture + Arkiv › Ture: dagsplan på tværs af kilder, opmærksomhedslinje,
  tildeling i rækken/massehandlinger, tur-panel med tidslinje og beskeder,
  ny tur med flere stop + gentagelse, kopiér/flyt dato, Historik og Excel-import.
- **Tur-beskeder** (`tour_messages`, `/api/tour-messages/*`) mellem planlægger og
  chauffør med ulæst-tællere, "Læst"-kvittering og hurtigsvar (in-app; web push til
  chauffører er fortsat slået fra jf. Fase 15.23b).
- **Push ved tildeling** (PUT /tours og /tours/bulk-assign).
- **Navigation**: Ture · Planlægning · Chauffører · Rapportering · Økonomi + "Mere"
  (Lokationer, Arkiv, Indstillinger); mobil-skuffe (`components/AdminTabNav.jsx`).
- **Rapportering** viste 0 for logistikfirmaer (læste tom `drivers`-kollektion og kun
  firmaets egne ture) - rettet; ny "I dag"-blok, auto-opdatering hvert 30. sek.
- **Chauffør TURE**: lyse `DriverTourCard` med Start → Afslut, Kort, Besked; den
  altid-skjulte mørke liste (~1.100 linjer) fjernet.
- **Sikkerhed**: gamle `/messages*` og `DELETE /tours/{id}` kræver login;
  bulk-assign kun på firmaets egne/tildelte ture.
- GET /tours: `date_from`, `date_to`, `pending`. TourUpdate: date, fraction, address,
  facility, plads, capacity_label (ikke for chauffører).

## What's new in 2026-10-16 (Logistik: Premium vs. Partner + oprydning)

Se `LOGISTICS_TIERS.md`.
- **Premium (option 1)** = logistikfirma oprettet som kunde med kundetype
  logistik; **Partner (option 2)** = logistik-partner fra biblioteket.
  `GET /api/logistics/profile` fortæller frontend hvilken type + om firmaet har
  tilknyttede genbrugsplads-kunder.
- Premium: egne lokationer (fanen hedder nu "Lokationer"), chauffører får
  "Egne ture" som valg (uden kunder springes kundevalget over), Økonomi
  prissætter egne ture pr. slutkunde (firma). Genbrugsplads-funktioner vises
  kun når der er tilknyttede kunder.
- **Fejlrettelse (alle logistikfirmaer):** manuelt oprettede ture blev aldrig
  knyttet til logistikfirmaet og var derfor usynlige for chaufførerne.
- Økonomi: "Åbn igen" hedder nu "Fjern faktureret-markering" og vises kun for
  ture der faktisk er faktureret.
- Emergent fjernet: emergent-main.js, "Made with Emergent"-badge, PostHog
  session recording, @emergentbase/visual-edits, .emergent/ og bot-.gitconfig.

## What's new in 2026-10-16 (Økonomi: prisregler, rapport, godkendelser)

"Priser & Rapport" (fast pris pr. plads + fraktion) er erstattet af **Økonomi**
på logistik admin-siden. Fuld specifikation: `PRICING_SPEC.md`.

- **Prisregler:** grundpris (fast / timepris / pr. container) + tillæg (weekend,
  helligdag, haster, hænger, aften/nat, ventetid, andet). Betingelser: kunde,
  lokation, leveringsadresse (matchet på modtagerens navn), materiale,
  opgavetype, prioritet, dagtype, hænger, containerstørrelse, tidsrum, udfald
  (gennemført/forgæves), gyldig fra/til. Mest specifikke grundpris vinder; ét
  tillæg pr. kategori (mest specifikke), så kundespecifikke satser overstyrer
  generelle uden dobbeltopkrævning.
- **Timepris:** "På vej" → "Afslut tur"; pauser fra "Tid" trækkes fra pr. regel;
  afrunding (op/nærmeste/ned, 15/30/60 eller eget tal), minimum minutter/beløb,
  startgebyr. Samtidige ture (hænger) får den fælles tid fordelt ligeligt
  (indstilling).
- **Helligdage:** egen kalender beregnes automatisk for alle år (påske/pinse) +
  valgfrie dage + egne dage; som standard bruges kundens/lokationens kalender
  først (samme kalender som bestillingssiden).
- **Rapport:** KPI'er, "mangler pris/tid", fakturagrundlag (CSV), markér som
  faktureret (prisen fryses), tur-detaljer med prisopbygning og tilpasning
  (fast beløb, ekstra linjer, rettede fakta - begrundelse påkrævet).
- **Chauffør:** ser afregningsform (aldrig beløb, undtagen timeprisen), vælger
  Med/Uden hænger pr. tur mens den kører, og kan anmode om rettelse af tid,
  hænger og ventetid efter turen → **Godkendelser** hos logistik admin.
- **Dagrapport-PDF:** nyt design (liggende A4, tabeller, nøgletal øverst) i
  `frontend/src/lib/dayReportPdf.js`, fælles for chauffør og Arkiv. Viser alle
  arbejds-/pauseperioder, alle ture afsluttet på dagen, pause i tur, netto-tid,
  afregning (fast/timepris + om pausen fratrækkes) og afregnet tid. I Arkiv
  bygges PDF'en FRISKT ved Download/ZIP (`/admin/day-report`), så godkendte
  rettelser og prisregler altid er med; den gemte fil ligger under "Original".
  "Timer i dag" står ikke længere på 0 efter login.
- **Logistik admin → Arkiv → Ture:** nyt tur-overblik (egne ture).
- Motor: `backend/pricing.py` (rene funktioner), tests i
  `backend/tests/test_pricing_engine.py`. Nye collections: `price_rules`,
  `price_settings`, `tour_change_requests`. Nye tur-felter: `used_trailer`,
  `fact_overrides`, `price_override`, `price_locked`, `price_history`.

## What's new in 2026-07-11 (Copy-config bug fix — kopierer nu ALT)

**Bug rapporteret af bruger:** "jeg lavede en kopi... så sørg for at alt bliver
kopieret og ingen fejl denne gang". Målet manglede kapacitetsmål, container-
overrides, container-antal, partner-materialer og CO2-mapninger efter en kopi.

**Fix i `POST /api/org/schedule/copy-config`:**
Endpoint kopierer nu ALT lokationsscopet data. Understøtter `sections: ["all"]`
(default hvis feltet mangler eller er tomt). Target ryddes helt før kopi — ingen
preudfyldning / ingen default-materialer på target efter kopi.

**Kollektioner der kopieres:**
1. `holiday_calendars` — helligdagskalendere
2. `hours_calendars` — åbnings-/lukketidskalendere
3. `material_calendars` — hvilken kalender pr. materiale (ID-remap til nye kal.)
4. `delivery_addresses` — leveringsadresser
5. `capacity_measures` — LA-bibliotek (NY — manglede før)
6. `container_overrides` — per-container adresse/tid/ID/lås/kapacitetsref
   (NY — remapper `capacity_measure_id` til target's nye caps)
7. `container_counts` — antal containere pr. materiale/partner (NY)
8. Plads/locations-dokumentet: `materials`, `inactive_materials`,
   `partner_materials`, `material_co2_categories`, `containers_per_material` (NY)

**Frontend `CopyConfigModal` (LocationAdminPage.jsx):**
Forenklet til "Kopier alt" — checkbox'ene er fjernet fordi brugeren ønsker
altid at kopiere alt. Modal viser tydelig liste over hvad der kopieres og en
rød konfirmationsdialog inden action.

**Verificeret via curl mod locations 1967 → 6164 (Helsingør Forsyning):**
Alle 8 sektioner kopierede 1:1. ID-remap valideret (0 orphan refs).
Idempotent — anden kopi giver samme counts (ingen duplikering).

## What's new in 2026-02-XX (Fase 18.28 — Mobil-redesign runde 2 + Pull-to-refresh)

**Bruger-feedback (med 5 vedhæftede billeder):**
1. "Vælg prioritet"-siden: 3 knapper er FOR store på mobil → scrolling krævet.
2. Kunde admin + Location admin: blå header for stor, "+ Ny location"-
   knappen for stor. Header bør konverteres til listebaseret menu-mønster.
3. "Mine bestillinger" filter-knapper overlapper og ser mærkelige ud.
4. "Opret CO2-type" knap for stor + "Faktor" usynlig under CO2-typer på mobil.

**Implementation:**

**1. Vælg prioritet (App.js step 4):**
- 3 knapper: `p-6 rounded-2xl` → `p-3 sm:p-6 rounded-xl sm:rounded-2xl`,
  `w-12 h-12` ikon → `w-10 h-10 sm:w-12 sm:h-12`, `text-xl` → `text-base sm:text-xl`,
  `text-sm` → `text-xs sm:text-sm`, `space-y-4 mb-8` → `space-y-2 mb-4 sm:mb-8`.
- Ordreopsummering: `p-4 mb-6` → `p-3 sm:p-4 mb-3 sm:mb-6`, `text-sm` →
  `text-xs sm:text-sm`, `space-y-1` → `space-y-0.5 sm:space-y-1`.
- Bestil-knap: `py-4 text-lg` → `py-3 sm:py-4 text-base sm:text-lg`.
- Resultat: alt synligt på én mobil-skærm uden scroll, stadig læsbart for
  dårligt syn.

**2. LocationAdminPage + CustomerAdminPage — Hamburger drawer (mobil):**
- Indført `Menu`-ikon-knap øverst til venstre på mobil (`sm:hidden`).
- Tabs-rækken (alle moduler) skjult på mobil (`hidden sm:block`).
- Ny side-drawer (via `createPortal`) der slider ind fra venstre med:
  - Header: logo + firmanavn + close-knap.
  - Liste-baseret menu med alle moduler — aktiv tab markeret med
    `border-l-4 border-emerald-500` + `bg-emerald-500/15`.
  - "Log ud"-knap nederst.
- Header viser nu aktuel-tab-label i underteksten på mobil (`<span className="sm:hidden">{activeTab.label}</span>`).
- "+ Naviger til bestillingsside" på mobil (LocationAdmin): kompakt
  fuldbredde-knap under header.

**3. Kompakte "+ Opret/Ny..." knapper (CustomerAdminPage):**
Alle CRUD-trigger-knapper i tab-headers ændret til mobil-kompakt mønster:
- `flex items-center gap-2 px-4 py-2` → `inline-flex items-center
  justify-center gap-1.5 p-2 sm:px-4 sm:py-2`
- Tekst gemt på mobil: `<span className="hidden sm:inline">...</span>`
- Resultat: kun ikon vises på mobil (kompakt + elegant). Desktop uændret.
- Gælder: `+ Ny lokation`, `+ Ny location admin`, `+ Ny lokationsgruppe`,
  `+ Opret CO2-type`.

**4. CO2-typer tabel → card-layout på mobil:**
- Desktop: original tabel (Navn / Faktor / Handlinger).
- Mobil (`sm:hidden`): vertikalt stablede kort. Hvert kort viser:
  - Leaf-ikon i lille rund baggrund (venstre)
  - Navn (top) + "Faktor: X kg/ton" (under) som tydelig label-værdi
  - Edit + Slet ikon-knapper (højre)
- "Faktor" er nu fuldt synlig (var gemt bag tabel-scroll på mobil).

**5. "Mine bestillinger" filtre — bedre spacing & polish:**
- Filter-chip-række: `gap-1.5` → `gap-2`, padding `px-2.5 py-1.5` →
  `px-3 py-1.5`, aktive chips får `shadow-sm shadow-{color}/30` for
  bedre visuel feedback. Tilføjet `pb-1 -mx-1 px-1` på scroll-container
  for at undgå clipping af skygge-kanter.
- Dato-rækken: `gap-2 mb-3` → `gap-1.5 mb-2` (tighter), aktive
  I dag/I går chips får også shadow.
- Refresh-ikon på mobil viser nu `animate-spin` når `historyLoading=true`.
- Pr. dato / Alle datoer: `mb-3` → `mb-2.5` (mere konsistent rytme).

**6. Pull-to-refresh på "Mine bestillinger" (mobil):**
- Tilføjet `onTouchStart` / `onTouchMove` / `onTouchEnd` på history-section.
- State: `pullDistance` (px), `isPulling` (bool), `pullStartY` (ref),
  threshold = 70px.
- Når `window.scrollY === 0` og bruger trækker ned: sektionen følger
  med (resistance-curve 0.5x), spinner-indikator vises øverst med tekst
  "Træk for at opdatere" → "Slip for at opdatere" (skifter farve ved threshold).
- Slip ved >= threshold: trigger `fetchOrderHistory()`.
- Transition tilbage til 0 på `touchend`.

**Filer ændret:**
- `/app/frontend/src/App.js` (prioritet-side, history pull-to-refresh,
  filter-chips polish)
- `/app/frontend/src/pages/LocationAdminPage.jsx` (drawer + kompakt header)
- `/app/frontend/src/pages/CustomerAdminPage.jsx` (drawer + kompakte knapper +
  CO2 card-layout)

**Test-status:** Compile clean. Mobil-screenshot (iPhone 12 Pro 390x844) på
"Mine bestillinger"-fanen bekræfter ren layout. E2E test sprunget over pga.
wipede DB-konti.


## What's new in 2026-02-XX (Fase 18.27 — Mobil-redesign af bestillingssiden + Admin-sider)

**Bruger-feedback (med 2 vedhæftede billeder):**
1. Mobil-versionen af bestillingssiden ser uprofessionel ud:
   - Filter-chips på "Mine bestillinger" stables klemt og ujævnt
   - Dato-vælger overload (pile + input + I dag/I går + datotekst i én række)
   - "Inkludér estimater"-toggle klemt mod kanten
2. Mobil-versionen af Location Admin har en overfyldt header
   (rolle + firma + lokation + login-bruger), 5+ tabs i én række
   med "Mere"-dropdown der er svær at ramme.
3. Brugeren har bedt om en grundig mobil-redesign — desktop-versionen
   skal forblive uændret.

**Implementation (alt via responsive Tailwind-klasser; desktop urørt):**

**1. CustomerOrderPage (App.js):**
- **Header**: `py-4 px-4` → `py-3 sm:py-4 px-3 sm:px-4`. Truck-ikon
  `w-5` → `w-4 sm:w-5`. "ContainerFlow" titel `text-lg` → `text-base sm:text-lg`.
  Lokationsnavn truncate. "Logget ind som X" gemt på mobil (`hidden sm:block`).
- **Main padding**: `px-8` → `px-4 sm:px-8`.
- **Tab pillerne ("Ny bestilling"/"Mine bestillinger")**: Fuld-bredde
  på mobil (`w-full sm:w-auto`), `flex-1 sm:flex-initial` på hver pille,
  mindre tekst (`text-xs sm:text-sm`), mindre padding (`px-3 sm:px-5`).
- **Grøn "+ Tilføj nyt materiale"-knap**: `w-full sm:w-auto` så den
  fylder hele bredden på mobil under tab-pillerne.
- **Step indicator (4 steps)**: To versioner — mobil viser
  "Trin X af 4 · [Label]" med progress-bar og %-tæller. Desktop beholder
  4 cirkler med labels.
- **Material-kort**: Mindre ikon-boks på mobil (`w-8 h-8` vs `w-10 h-10`),
  mindre tekst (`text-xs sm:text-sm`), giver materialenavn mere læseplads
  i 2-kolonners grid.
- **History-view (Mine bestillinger) — kerne af mobil-redesignet**:
  - **Pr. dato / Alle datoer**: Fuld-bredde segmented control på mobil
    (i stedet for klemte chips). Desktop beholder original flex-wrap.
  - **Filter-chips på mobil**: Kompakt vandret række med "Afventende",
    "Skjul fuldførte", "Estimater" som runde pills (`px-2.5 py-1.5 rounded-full
    text-[11px]`) + refresh-ikon yderst.
  - **Date navigation**: To versioner — mobil viser pile + fuld-bredde
    dato-input + "I dag"/"I går" som runde chips under. Desktop beholder
    inline-version.
  - **Scope toggle ("Mine"/"Alle bestillinger")**: Fuld-bredde segmented
    control på mobil. Desktop beholder inline + estimater-toggle på samme række.
  - **Inkludér estimater**: Dubleret som chip i mobile-rækken; den store
    toggle vises kun på desktop.
- **"Bekræft og rediger"-form (step 3)**: Alle `max-w-xs/lg/md` ændret
  til `sm:max-w-xs/lg/md` — fuld bredde på mobil, kompakt på desktop.

**2. LocationAdminPage:**
- **Header**: `px-6 sm:px-10 py-3` → `px-4 sm:px-10 py-2.5 sm:py-3`.
  Logo `w-9 h-9` → `w-8 h-8 sm:w-9 sm:h-9`. Lokationsnavn truncate.
  "name/email" gemt på mobil. Logout-knap som ikon-only (`p-2 rounded-lg
  bg-slate-800/70`) på mobil; tekst-version kun på desktop.
- **Tabs**: Sekundære faner (Kapacitetsmål, Leveringsadresser, Modtagne
  delta'er, Logistik-partnere, Slet permanent) vises direkte i den
  vandrette scroll på mobil (`sm:hidden` på "Mere"-knappen). Desktop
  beholder "Mere"-dropdown. Tilføjet `snap-x snap-mandatory` for swipe-snap
  og en gradient-fade på højre kant som visuel hint.

**3. CustomerAdminPage:**
- **Header**: Samme mobile-pattern som LocationAdminPage (kompakt header,
  ikon-only logout).
- **Tabs**: Tilføjet `snap-x snap-mandatory` + gradient-fade.

**Mobil-screenshot-validering**: Begge skærmbilleder bekræftede succesfuld
ren mobil-layout (kompakt header, fuld-bredde segmented controls, chip-række
filtre, læsbar dato-nav). Desktop forbliver uændret.

**Filer ændret:**
- `/app/frontend/src/App.js` (CustomerOrderPage — header, step indicator,
  history filtre, dato-nav, scope toggle, material-kort, bekræft-form)
- `/app/frontend/src/pages/LocationAdminPage.jsx` (header + tabs)
- `/app/frontend/src/pages/CustomerAdminPage.jsx` (header + tabs)

**Test-status**: Compile clean (kun pre-eksisterende eslint-warnings).
Mobil-screenshot på iPhone 12 Pro-størrelse (390x844) på ordrer-flow og
history-view bekræfter forbedring. E2E test sprunget over pga. wipede
DB-konti.


## What's new in 2026-02-XX (Fase 18.24 — CustomerOrder UI kompakt-runde)

**Bruger-feedback:**
1. "+ Tilføj nyt materiale"-knappen under materiale-grid'et blev forvekslet
   med et rigtigt materialekort. Flyttes op på samme række som "Ny bestilling"
   / "Mine bestillinger"-pillerne og styles tydeligt grøn.
2. Custom-material formularen var for stor (p-4 + py-3 + border-2).
3. "Bekræft og rediger"-trinnet (containernummer, leveringsadresse,
   åbner, lukker, afhentningsdato) føltes klodset — felter er for store.

**Implementation:**
- **Header-rækken** (`max-w-screen-2xl mx-auto mt-3`): segmented control +
  ny grøn knap (`bg-emerald-500 hover:bg-emerald-600`) på samme `flex
  justify-between`-række. Knappen vises kun når `view === "order" && step === 1
  && isAdmin && !showCustomMaterial`. `data-testid="add-custom-material-btn-header"`.
- **Gammel placering** under materialegridet er fjernet helt.
- **Custom-material-formularen**: padding `p-4 → p-3`, label-tekst krympet
  (`text-sm font-bold mb-2` → `text-xs font-bold mb-1.5 uppercase`), inputs
  `py-3 → py-2`, knapper `px-6 py-3 → px-4 py-2`, border `border-2 → border`.
- **"Bekræft og rediger"-trinnet** (step 3 — normal flow): 
  - Heading `text-2xl mb-1` → `text-lg sm:text-xl mb-0.5`. 
  - Hoved-container `border-2 rounded-2xl p-6 space-y-4 mb-6` → 
    `border rounded-xl p-4 space-y-3 mb-4`. 
  - Ikon-bokse `w-10 h-10` med `w-5 h-5`-ikon → `w-8 h-8` med `w-4 h-4`-ikon. 
  - Labels `text-xs uppercase mb-1` → `text-[10px] uppercase mb-0.5/1`. 
  - Værdier `font-bold text-lg` → `font-semibold text-sm`. 
  - Inputs `px-4 py-2` → `px-3 py-1.5`, alle med `text-sm`. 
  - Tid-felter (Åbner/Lukker) `px-3 py-2` → `px-2.5 py-1.5`. 
  - Opgavetype-knapper `p-2.5 rounded-xl border-2` → `p-2 rounded-lg border`,
    titel-tekst `text-sm` → `text-xs`. 
  - Dato-picker-card og kommentar-card: `border-2 rounded-2xl p-6 mb-6` → 
    `border rounded-xl p-4 mb-4`. Dato-knapper `py-3 rounded-xl` → 
    `py-2 rounded-lg`. Kommentar-textarea `h-20` → `h-16`. 
  - Submit-knappen `py-4 text-lg` → `py-3 text-base`.

**Filer ændret:** `/app/frontend/src/App.js` (linjer ~1996-2032, 2273-2335,
2491-2502, 2845-3245).

**Test-status:** Compile clean (kun pre-eksisterende eslint warnings).
Visual smoke test via super_admin-login OK. Customer-order flow ikke
e2e-testet pga. wipede test-konti (kun super_admin findes i DB) — bruger
godkendte at springe testing_agent over.


## What's new in 2026-02-28 (Fase 18.8 — Arkiv CO2-parity + Igangværende-toggle + Rapport-scroll)

**Bruger-feedback:**
1. CO2-kolonnen i Arkiv beregnede ikke altid CO2 som i Bestilling-fanen
   (stale order.co2_kg for løs afhentning).
2. Igangværende ture fyldte arkivet — bør filtreres væk by default, men
   med en toggle der viser dem øverst i tabellen.
3. Sortering skal være kronologisk (nyeste først).
4. Rapportering-fanen "halv-loadede" når man scrollede ned — recharts
   `ResponsiveContainer` ResizeObserver loop.

**Implementation:**
- **Backend `/api/org/tour-archive`:** CO2 beregnes nu altid som
  `co2_factor × tour.weight / 1000` når begge er > 0 (samme formel som
  Bestilling-fanen). Falder kun tilbage til `order.co2_kg` hvis factor
  eller vægt mangler. Sikrer 100% parity for både normal og løs.
- **Frontend `ArchiveTab`:**
  - Ny state `includeOngoing` (default = false). Igangværende ture
    (hvor `!completed && !not_completed`) filtreres væk by default.
  - **Toggle-knap** "Inkluder igangværende ture (N)" i filter-bar med
    badge der viser antal. Slået til = "Skjul igangværende".
  - **Sortering:** Igangværende altid ØVERST (når inkluderet) +
    kronologisk (nyeste først) baseret på `completed_at` →
    `ordered_at` → `order_date` → `date`.
- **Frontend `LocationAdminPage` (ReportsCharts):** Alle 4 recharts
  `ResponsiveContainer` har nu `debounce={150}` — fjerner
  ResizeObserver-loops under scroll og dermed "halv-loader"-følelsen.


## What's new in 2026-02-28 (Fase 18.7 — Chauffør: Kvittering pr. løs vægt)

**Bruger-feedback:** På chaufførsiden for "Løs afhentning" kunne man kun
uploade ÉN kvittering, og det var uklart hvilke kvitteringer der allerede
var uploaded pr. vægt-række.

**Implementation:**
- **Backend `/api/receipts`:** Tilføjet `tour_id` query param så chauffør-UI
  kan hente alle uploadede kvitteringer for én tur (sorteret efter
  `created_at` stigende, matcher row-index).
- **Frontend (`MobileTourPanel`):**
  - Ny state `uploadedReceipts[]` der hentes ved mount + efter draft-save.
  - Hver løs-vægt-række viser nu enten:
    - **"Åbn" grøn knap** (med øje-ikon) hvis kvitteringen er gemt på
      serveren — åbner `DriverReceiptQuickViewer` (blob-stream)
    - **"Vedh." gul badge** (med check-ikon) hvis kvitteringen er pending
      lokalt og endnu ikke uploaded
    - Intet hvis ingen kvittering vedhæftet endnu
  - Kamera-knappen får grøn baggrund + lille prik-indikator når der
    findes (lokal eller server-side) kvittering.
- **`handleSaveLooseDraft` udvidet:** Uploader nu også PENDING kvitteringer
  ved "Gem udkast" (via `enqueueReceiptUpload` med `skip_tour_update=true`),
  så de overlever sidereload. Bagefter genfetcher den server-kvitteringer
  så UI'et straks viser den nye "Åbn"-knap.
- **`DriverReceiptQuickViewer`:** Letvægts-modal til chauffør (uden
  download-knap — chaufføren skal kun verificere indholdet). Blob-stream
  via `/receipts/{id}/image-binary` (ingen base64 JSON-payload).


## What's new in 2026-02-28 (Fase 18.6 — Location Admin Arkiv: udvidet)

**Bruger-krav:**
1. Default visning = i dag, med periode-skifter (Uge / Måned / Alle / Brugerdef.)
2. "Åbn" pr. kvittering → modal med billede + download-knap
3. Vis logistik-partner (fx ILK Logistics)
4. Vis opgavetype tydeligt (Almindelig / Løs / Bytte / Værksted til/fra)
5. Vis bestilt af + tidspunkt for bestilling
6. Multi-location vælger med default = ALLE (ikke bare første)
7. CO2-kolonne ved siden af Vægt; løs afhentning bryder CO2 pr. afhentning
8. Excel reflekterer alle ovenstående felter

**Backend `/api/org/tour-archive` udvidelser:**
- Henter også `co2_factor`, `co2_type_name`, `partner_id`, `created_at`,
  `created_by_email` fra container_orders.
- Slår partner-navn op via companies-collection (både fra order.partner_id
  og tour.assigned_logistics_company_ids[0]).
- For løs afhentning hvor co2_kg ikke er gemt på ordren: genberegnes som
  `factor * (total_weight / 1000)`.
- Returnerer nye felter: `ordered_at`, `ordered_by_email`, `partner_id`,
  `partner_name`, `co2_factor`, `co2_type_name`.

**Frontend `LocationAdminPage.jsx` (ArchiveTab + ReceiptViewerModal):**
- **Default-state:** Periode = "I dag"; lokationer = ALLE tildelte.
- **Periode-skifter:** Quick-knapper (I dag / Uge / Måned / Alle / Brugerdef.);
  manuel ændring af dato-felterne sætter automatisk perioden til Brugerdef.
- **`TASK_TYPE_LABELS`** map: tour_type → label + farve-class. Vises som
  badge i Opgavetype-kolonne. Status-badge stables under den.
- **Nye kolonner:** Bestilt af (med tidspunkt under), Partner (cyan-badge),
  Opgavetype, CO2 (kg) med Leaf-ikon ved siden af Vægt.
- **Løs afhentning popover:** Hver afhentnings-række viser nu også CO2
  pr. delvægt (kg CO2 = factor × kg / 1000) + "Åbn kvittering"-link
  direkte i popoveren.
- **`ReceiptViewerModal` (NY):** Trækker billede via
  `/receipts/{id}/image-binary` (blob, ikke base64), viser i centreret
  modal med Download-knap (gemmer som `kvittering_{driver}_{date}.jpg`).
  Brugbar både fra ny "Åbn"-knap i Kvit.-kolonnen OG fra popover-link
  for hver løs afhentning.
- **KPI-kort** udvidet med CO2-kort (teal, m. Leaf-ikon).
- **Excel-eksport** opdateret med Bestilt tidspunkt, Bestilt af,
  Logistik-partner, Opgavetype, CO2 (kg) — også i Løse afhentninger-fanen.

**Verificeret backend:** 18 ture i arkiv, `partner_name="ILK Logistics"`,
`ordered_by="Helsingør Forsyning Boliggården Location Admin"`,
`ordered_at` ISO-tidsstempel — alt udfyldt korrekt.


## What's new in 2026-02-28 (Fase 18.5 — Søge-fix + Tur-Arkiv på Location Admin)

**Bruger-feedback:**
1. Søgefeltet "Søg i tekst/Beskrivelse" på Kvitterings-arkiv fandt aldrig
   noget — den søgte kun i `ocr_raw_text` (tomt efter OCR-fjernelse) og
   `description`.
2. Location Admin manglede en "Arkiv"-fane med turhistorik (på linje med
   "Bestillinger", "Rapportering" osv.) med multi-lokation-support og
   detaljeret breakdown for løse afhentninger.

**Implementation:**
- **Backend `/api/receipts-archive` (søg):** `$or`-listen udvidet til at
  matche partial regex på `ocr_raw_text`, `description`, `driver_name`,
  `plads`, `fraction`, `id`, `tour_id` — alle case-insensitive.
- **Backend `/api/org/tour-archive` (NY):** Returnerer turhistorik
  filtreret på `location_codes` (CSV, multi-location). Tilladt for
  `location_admin` (kun egne `assigned_plads_ids`), `customer_admin`
  (alle i selskab), `super_admin`. Hver tur beriges med:
  - `order_date` fra container_orders (bestilte dato)
  - `completed_at` (Fuldført)
  - `tour_type`, `container_weights`, `loose_estimated_count`
  - Linkede `receipts` (uden image_data — frontend trækker via binary-endpoint)
- **Frontend `LocationAdminPage.jsx`:** Ny tab "Arkiv" mellem
  Rapportering og Logistik-partnere. Indeholder:
  - Multi-lokation-vælger (samme pattern som ReportsTab)
  - Dato-fra/til + søgefilter (lokal text-filter)
  - KPI-kort: Ture, Containere (inkl. løse), Total vægt
  - Tabel med kolonner: Bestilt, Fuldført, Lokation, Materiale,
    Container, Type, Antal, Vægt, Tur start, Tur slut, Chauffør, Kvit.
  - **Løs afhentning:** vægt-celle har badge "Nx" + både desktop-tooltip
    (kortform med tider) og klik-popover (fuld breakdown med X-knap).
    Popover viser pr. afhentning: nummer, tidspunkt, vægt + grand total.
  - Excel-eksport (2 faner: "Ture" + "Løse afhentninger") via `xlsx`.
- Verificeret backend (Ferdal/9984): søg → 11 træf (var 0); tour-archive
  → fuld payload med tours+receipts.


## What's new in 2026-02-28 (Fase 18.4 — PDF Arkiv duplikat-fix + XLSX-eksport)

**Bruger-feedback:**
1. PDF Arkiv viste de SAMME 4 stat-badges (contai./tid/dage/kg) på år-,
   måned- og chauffør-niveau, hvilket lavede visuel støj når der kun var
   én periode/én chauffør.
2. Den downloadede CSV-rapport viste KUN aggregerede dagstal — ikke de
   enkelte IND/UD/pause-vinduer. Brugeren skal kunne tilgå alle stempler
   på timeslice-niveau.

**Implementation (`/app/frontend/src/App.js`):**
- **Badge-deduplikering:** Måned-badges skjules nu hvis året kun har én
  periode (`singlePeriodInYear`). Chauffør-badges skjules hvis måneden
  kun har én chauffør (`singleDriverInMonth`). CSV/ZIP-actions beholdes
  altid synlige.
- **Eksporter alt (Excel)** (tidligere CSV): Bruger nu `xlsx`-biblioteket
  til at generere `.xlsx` med **to faner**:
  1. **Dagrapporter** — én række pr. dag med Dato, Chauffør, Plads,
     Ture, Vægt, Start (første IND), Slut (sidste UD), Arbejde (min/HH),
     Pause, Total span, Antal stempler.
  2. **Tidsstempler** — én række pr. `driver_time_entry`, sorteret efter
     start_time, med Dato, Chauffør, Rækkefølge, Type (Arbejde/Pause),
     Start, Slut, Varighed, Manuel ja/nej, Stempel-type, Årsag, Åben.
  Hvis ingen entries findes for perioden vises en "Ingen tids-
  registreringer"-besked på Tidsstempler-fanen.
- Pr-måned og pr-chauffør "CSV"-knapper er nu også **Excel**-knapper
  (samme funktion, lokalt scope).
- Auto-kolonnebredde sat på begge faner for læsbarhed.


## What's new in 2026-02-28 (Fase 18.3 — Kvitterings-arkiv fixes)

**Bruger-feedback (4 issues):**
1. "Plads"-feltet i Pr. chauffør → expanderet dag-panel var tomt.
2. Tabel-visning manglede tur start/slut tidspunkter.
3. Tabel-filtre (chauffør/plads/fraktion) virkede ikke (eksakt match returnerede 0).
4. Dagsrapporter (PDF) viste kun én start/slut/TID, ikke flere IND/UD + pauser.

**Implementation:**
- **Backend `/api/receipts-archive`**:
  - `driver_name`, `plads`, `fraction` bruger nu case-insensitive REGEX
    partial match (i stedet for eksakt match) — "ferd" matcher nu
    "Ferdal Turan".
  - Hver række beriges med `tour_started_at`, `tour_completed_at`,
    `tour_claimed_at` ved at slå turen op via `_raw_db.tours`.
- **Backend `/api/pdf-archive`**: Beriger hver dagrapport med
  `time_summary` via samme `_summarize_day_entries`-helper som
  Driver Archive. Slår driver-id'er op via `users` (alias-håndtering)
  og henter `driver_time_entries` for (driver_id, date).
- **Frontend `ReceiptOCRArchive.jsx`**: To nye kolonner i Tabel-visning,
  "Tur start" (grøn) og "Tur slut" (rød). Ny `fmtTimeShort` helper
  håndterer både "HH:MM" og fuld ISO-tidsstempel.
- **Frontend App.js (Pr. chauffør expanderet dag)**: Plads-felt bruger
  nu unikke pladser fra `day.tours[]` som primær kilde (komma-separeret
  hvis flere), legacy-felt som fallback.
- **Frontend App.js (PDF Arkiv tabel)**:
  - Kolonner: Dato, Plads, Ture, Vægt, **Start, Slut, Arbejde, Pause,
    Total** (start→slut inkl. pauser), PDF.
  - Hvis flere stempler samme dag: blå "Nx" badge ved Start-tiden med
    tooltip der lister alle vinduer (▶ arbejde / ☕ pause).
  - `getStartTime`/`getEndTime`/`calcDuration` foretrækker
    `time_summary` over legacy `start_time`/`end_time`.
  - CSV-eksport udvidet med Pause + Total-kolonner.

**Verificeret backend (Ferdal Turan):**
- `/receipts-archive?driver_name=ferd` → 10 rows m. `tour_started_at`/`tour_completed_at`.
- `/pdf-archive` → time_summary attached på arkiver der har stempler
  (eks. 2026-06-29: start=11:59, end=12:21, work=12m, slices=2).


## What's new in 2026-02-28 (Fase 18.2 — "Afslut dag" lov-validering)

**Bruger-prompt:** Dansk lov (1. juli 2024) kræver objektiv tidsregistrering
for alle ansatte. Chauffører glemmer ofte at stemple ud før de afslutter
dagen. Implementér tre scenarier på "Afslut dag"-knappen.

**Implementation (`/app/frontend/src/App.js`):**
- `handleEndOfShift` tjekker `timeEntries` for `reportDate` med
  `slice_type="work"` og `!deleted` FØR shift-flow startes.
- **Scenarie 1** (ingen IND): Modal "Ingen tidsregistrering" med to
  knapper — primær blå "Gå tilbage og registrer" lukker modalen; lille
  grå "Afslut alligevel" fortsætter den oprindelige flow.
- **Scenarie 2** (IND uden UD): Auto-stempler chaufføren ud via
  `POST /api/driver/time-entries/punch {type:"ud"}` (ingen direkte
  DB-skrivning). Viser modal "Vi har stemplet dig ud" med klokkeslæt,
  en blå "OK, afslut dag"-knap fortsætter.
- **Scenarie 3** (komplet IND+UD): Fortsætter direkte uden modal.
- Oprindelig slut-tid-validering flyttet til ny `proceedToEndOfShift()`
  helper, så alle scenarier deler samme efterfølgende flow.
- Modal er mobile-first: full-width bottom-sheet på mobil (`items-end`),
  centreret på sm+ (`sm:items-center sm:max-w-md`), store touch-targets
  (`py-3 text-base`).
- data-testids: `time-reg-modal`, `time-reg-modal-title`,
  `time-reg-modal-back`, `time-reg-modal-skip`, `time-reg-modal-ok`,
  `time-reg-modal-auto-time`.
- PDF-generering, tidsregistrering-system og øvrige knapper er IKKE
  ændret.


## What's new in 2026-02-28 (Fase 18.1 — Driver Archive: IND/PAUSE/UD-tider på dagsrækken)

**Bruger-prompt:** Vis chaufførens daglige start/slut-tider baseret på
faktiske IND/PAUSE/UD-stempler (kan være flere vinduer pr. dag). Første
IND = start, sidste UD = slut. Alle vinduer skal være synlige inkl.
mellemrum. Pauser tæller IKKE i primær varighed, men en separat total
inkl. pauser skal også vises. Samme logik i rapporter.

**Implementation:**
- Ny helper `_summarize_day_entries(entries, today_str, now_hhmm)` i
  `/app/backend/server.py` (~linje 4632). Returnerer per dag:
  `{start, end, work_min, pause_min, span_min, gap_min, work_slices,
  pause_slices, open, any}`. Soft-deleted entries filtreres væk; åbne
  IND-stempler på dagens dato tæller frem til "nu".
- `/api/driver-archive/{driver_name}` udvidet:
  - Slår `driver_id` op via `users` (token-baseret navne-match)
  - Henter `driver_time_entries` for de drivers i `_raw_db`
  - Vedhæfter `entries` + `time_summary` pr. dag i payload.
- `/api/admin/statistics` (Priser & Rapport): `total_hours` beregnes nu
  fra `driver_time_entries` via samme helper. Reports/sessions er kun
  fallback for dage UDEN entries — så grid-chips i Driver Archive
  matcher 1:1 med rapportens timetal.
- Frontend `App.js` AdminReceiptList:
  - Day-row chips: `🕐 start–slut` (blå) + `⏱ Xt Ym + Zm pause`
    (indigo, m. tooltip der viser inkl./ekskl. pause + gap).
  - Expanded day-panel viser:
    1. Summary-felter (Start, Slut, Arbejde, Pause, Ikke-stemplet,
       Total start→slut).
    2. Pill-liste over ALLE stempel-vinduer (grøn `▶` = arbejde,
       gul `☕` = pause), sorteret efter start_time, med tooltip
       (manual/årsag).
  - Faldback til legacy `sessions[0]/reports[0]` hvis ingen entries.
- Data-testids: `day-times-{date}`, `day-duration-{date}`,
  `day-slices-{date}` til testing.

**Verificeret backend-payload (Ferdal Turan, 2026-06-26):**
4 entries → start=22:19, end=23:35, work=65m, pause=11m, gap=0m,
span=76m, 2 work-slices + 2 pause-slices, open=True (en slice åben).


## What's new in 2026-02-27 (Fase 17 — jscanify scanner + merged Kvittering-arkiv)

### 🟢 Fase 17 — Full rewrite of ReceiptScanner.jsx with jscanify (DONE)

**User pivot:** Fjern al OCR (Google Vision) helt. Erstat med `jscanify`
til perspektiv-korrigeret scanning direkte i browseren. Streng iOS Safari
kompatibilitet krævet.

**Implementation:**
- `/app/frontend/src/components/ReceiptScanner.jsx` fuldstændig omskrevet
  (ingen `search_replace` — hele filen genskabt).
- Dependency: `jscanify@1.4.2` installeret. Import sker som
  `import jscanify from "jscanify/client"` (browser entry) for at undgå
  at webpack følger node-entry'en og forsøger at bundle jsdom/canvas.
- OpenCV.js (`https://docs.opencv.org/4.10.0/opencv.js`) lazy-loades via
  runtime `<script>` tag i `loadOpenCv()` første gang scanneren åbnes.
  Cachet derefter via `openCvLoadingPromise` på modul-niveau.
- **Streng iOS Safari pattern:**
  - Modalen er ALTID monteret. Synlighed styres via CSS `visibility` +
    `pointerEvents` + `opacity`. INTET conditional unmount.
  - `<input type="file" accept="image/*" capture="environment">` er en
    permanent del af komponenten med `position:absolute; opacity:0` (IKKE
    `display:none`, som Safari ignorerer).
  - `<label htmlFor="receipt-file-input">` over inputtet — brugeren trykker
    på label'en, hvilket Safari behandler som ægte user-gesture på input.
- **Flow:** idle → processing → preview → saving → saved.
  Vægten udfyldes ALDRIG automatisk; chaufføren indtaster manuelt og
  trykker "Bekræft & gem".
- **Multi-scan for løse afhentninger:** `isLoose=true` → efter save vises
  "Scan endnu en"-knap. Modal lukkes ikke automatisk fra parent for
  loose-mode (App.js opdateret).
- POST'er til samme endpoint `/api/receipts/save-for-tour` med
  `final_weight_kg` + `append_for_loose` + `skip_tour_update:true`.

### 🟢 Fase 17 — Merged Kvittering-arkiv (DONE)

**Bestilling:** Saml "Chauffør Arkiv (kvitteringer)" og "OCR-Arkiv" i ét
praktisk arkiv for logistik-admins.

**Implementation:** I `/app/frontend/src/App.js`:
- Fjernet de gamle subtabs `archives-subtab-receipts` (Chauffør Arkiv) og
  `archives-subtab-ocr` (OCR-Arkiv) som separate sektioner.
- Erstattet med ÉN subtab "Kvittering-arkiv" (genbruger testid
  `archives-subtab-receipts`).
- Inde i den merged sektion (`merged-receipts-archive-section`) er der en
  view-mode toggle:
  - **Tabel** (`receipts-archive-view-table`, default) →
    `<ReceiptOCRArchive>` med dato/chauffør/plads/fraktion/søge-filtre +
    paginering.
  - **Pr. chauffør** (`receipts-archive-view-drivers`) →
    `<AdminReceiptList>` (klassisk chauffør → dag → ture-mappe-struktur).
- Begge views deler den samme bagvedliggende data — kvitteringer fra
  jscanify-scannede + manuelt vedhæftede kvitteringer (uden OCR).

### Testing
- Backend regression: 17/17 pytest pass i
  `/app/backend/tests/test_phase17_receipt_scanner.py`.
- Frontend source-verified: jscanify/client import, ingen OCR-referencer,
  modal altid monteret med CSS visibility, permanent file input med
  korrekt opacity:0 placement.
- iter52 test report: `/app/test_reports/iteration_52.json`.


## What's new in 2026-02-27 (Fase 16.1 — Multi-tenant company_id fix + iOS-safe direct upload)

### 🟢 Fase 16.1 — Critical multi-tenant bug fix (DONE)

**Bug:** Kvitteringer uploadet via `/api/receipts/save-for-tour` blev gemt
med `company_id=''` (tom streng), så de var **usynlige** for logistik-admins i
OCR-Arkivet (multi-tenant filter skjulte dem).

**Root cause:** `TenantAwareDB._inject_doc` injicerer kun `company_id` hvis
nøglen MANGLER fra dokumentet. Men Pydantic-modellen `Receipt` har
`company_id: str = ""` som default, så nøglen er der (bare tom) → wrapperen
hopper over → tom `company_id`. Bug blev opdaget af brugeren da kvitteringer
gemt på iPhone aldrig dukkede op i logistik-admin arkivet selvom
`save-for-tour` returnerede 200 OK.

**Fix:** I `receipts_save_for_tour` poppes `company_id` fra `model_dump()`
hvis den er tom — så `TenantAwareDB` kan injicere den korrekt fra
`current_company_id` ContextVar.

### 🆕 Fase 16.1 — iOS-safe direct receipt upload (DONE)

Tilføjet en **"📎 Vedhæft kvittering (uden OCR)"** knap direkte i chaufførens
vægt-popup som alternativ til OCR-scanneren. Bruger `<label>` + standard
`<input type="file">` (det iOS-velkendte mønster) — virker uden modal, uden
`getUserMedia`, uden iOS Camera takeover. Auto-gemmer til `/api/receipts/save-for-tour`
med korrekt `company_id`.

**Tests:** 30/32 grønne (2 env-skips).

**Backfill script:** 3 ud af 27 legacy receipts kunne matches til en company
via driver-name lookup. De resterende 24 fra agentens tidlige test-runs har
ingen driver-info og forbliver med tom `company_id` (kun synlige for
super_admin).

---
## What's new in 2026-02-26 (Fase 16 — Kvitteringsscanning med OCR & Arkiv)

### 🟢 Fase 16 — OCR Receipt Scanning + Archive + Per-Customer Retention (DONE)

**Brugerønske:** "Kvitteringsscanning med OCR & Arkiv" via Google Cloud Vision API i EU-region.
Chauffører skal kunne scanne papirkvitteringer på pladsen og få nettovægten automatisk
udfyldt. Logistik-admin skal kunne søge i et arkiv. Per-kunde opbevaringsperiode skal kunne
konfigureres af super_admin.

**Implementeret (alle 10 user-decisions):**

1. **OCR-knap valgfri på vægt-popup** — manuel indtastning fortsætter med soft validation.
2. **Auto-fill vægt med driver confirm + multi-receipt for "løs afhentning"** — hver scan
   tilføjes som ny række (vægte summeres), aldrig overskrives.
3. **MongoDB GridFS-lignende inline base64** — gratis, ingen ekstern infra, samme retention
   som MongoDB (EU-residency).
4. **Per-kunde retention** konfigureret på Super Admin ("Administrer dataopbevaring"-fane,
   default 1095 dage = 3 år).
5. **Logistik-admin "OCR Arkiv"-fane** + (kommende) "Dokumenter"-fane for location admins.
6. **Filtre:** dato, chauffør, plads, fraktion, kunde, søgning i OCR-tekst — samme stil som
   resten af systemet.
7. **OCR-fejl-fallback:** manuel vægt-indtastning + client-side blur-validering så billedet
   bliver godt nok.
8. **Format:** JPG/PNG/HEIC max 10 MB. HEIC konverteres server-side via pillow-heif.
   Client downsizer til ~1800px før upload.
9. **Multi-receipt kun for "løs afhentning"** — normale ture = 1 kvittering pr. tur.
10. **Audit-log** for hver kvittering: original værdi + ny værdi + bruger + tidspunkt +
    begrundelse. "Ret vægt"-knap i detaljevisning.

**Backend (`server.py` + `ocr_service.py`):**
- Ny modul `/app/backend/ocr_service.py` med EU-endpoint (`eu-vision.googleapis.com`),
  pillow-heif-baseret HEIC-konvertering, og dansk Bruttovægt/Tara/Netto-heuristik.
- `POST /api/receipts/ocr-scan` — pure OCR (preview, ingen persist).
- `POST /api/receipts/save-for-tour` — OCR + persist + tour-update (loose: append, normal: set;
  `skip_tour_update` til staged uploads).
- `GET /api/receipts-archive` — tenant-scoped arkiv med pagination + filtre.
- `GET /api/receipts-location-documents` — for location admins (matcher
  `customer_company_id`).
- `GET /api/receipts/{id}/full` — fuldt billede + OCR-tekst + audit-log for detaljevisning.
- `PUT /api/receipts/{id}/weight-override` — manuel rettelse med audit.
- `GET /api/superadmin/retention-policies` — liste over kunder + nuværende opbevaringsdage.
- `PUT /api/superadmin/companies/{id}/retention-policy` — opdater retention (30–36500 dage).
- `GET /api/ocr/status` — diagnostisk endpoint (er Vision klar?).
- Auto-cleanup-cron opdateret: respekterer per-kunde retention; fallback 1095 dage for
  legacy receipts uden `customer_company_id`.

**Datamodel-udvidelser:**
- `Receipt` (auth.py/server.py): `ocr_raw_text`, `ocr_weight_kg`, `ocr_confidence`,
  `ocr_candidates`, `ocr_status`, `final_weight_kg`, `audit_log[]`, `customer_company_id`,
  `tour_id`, `fraction`.
- `Company` (auth.py): `receipt_retention_days: int = 1095`.

**Frontend:**
- Ny komponent `/app/frontend/src/components/ReceiptScanner.jsx` (drop-in modal, camera +
  galleri + HEIC + blur-detection + OCR-preview).
- Ny komponent `/app/frontend/src/components/ReceiptOCRArchive.jsx` (filter-tabel + detalje-
  modal med billed-preview, OCR-tekst, audit-log, manuel rettelse).
- `App.js`: scan-knap i normal vægt-prompt + per-row scan-knap på løs-afhentning. Staged
  receipts cached lokalt og persisteres via `save-for-tour` når chaufføren afslutter turen
  (med `skip_tour_update=true` så vægten ikke dobbelt-skrives).
- `SuperAdminPage.jsx`: ny `RetentionPolicyPanel`-fane "Administrer dataopbevaring" med
  presets (1 år, 3 år, 7 år, 10 år) + pr-kunde manuel indtastning + validation.
- Ny logistik-admin sub-fane "OCR Arkiv" under "Arkiver".

**3rd party integration:**
- Google Cloud Vision API, EU-endpoint `eu-vision.googleapis.com` (GDPR).
- Genbruger samme service account JSON som Drive-backup (`/app/secrets/google_drive_sa.json`).
- Bruger skal aktivere "Cloud Vision API" + tildele rolle `Cloud Vision API User`.
- Gratis kvota: 1000 enheder/måned.

**Tests:** 12/12 phase 16 pytests grønne (`tests/test_phase16_ocr.py`).

**Status:** Backend + frontend implementeret. OCR-funktionalitet kræver brugeren aktiverer
Vision API i sit Google Cloud projekt (instrukser delt i chat). Indtil da returnerer
`/api/ocr/status` 503 og scanner-knappen falder pænt tilbage til manuel indtastning.

---
## What's new in 2026-02-22 (Fase 15.44 — Løs afhentning fix-pakke)

### 🟢 Fase 15.44 — UX-fixes + draft-vedholdenhed + CO2 (DONE)

**Bruger-rapport (5 stk):**
1. *"De gemte vægte forsvinder når jeg går ud og ind fra panelet."*
2. *"Customer-filter chips flasher ved 'Gem udkast'."*
3. *"Skift 'Opgavetype: Normal afhentning' til 'Løs afhentning' i Mine bestillinger og i edit-modalen."*
4. *"Vis CO2 også for løs afhentning på Mine bestillinger."*
5. *"Tilføj 'Tilføj vægt'-knap. Soft-confirm ved Afslut. Multi-vægt-UI skal være ALTID synlig så man kan tilføje til eksisterende drafts."*

**Root cause + fixes:**

**Backend (`server.py`):**
1. **`Tour`-model manglede `container_weights` + `loose_estimated_count`** → `response_model=Tour` strippede dem væk fra PUT /tours/{id}-svaret. Lokal frontend-state mistede vægte. **Fix:** Tilføjet begge felter eksplicit på Tour-modellen (Fase 15.43-T5 regression-test dækker det).
2. **CO2 hardkodet til 0 for `loes_afhentning`** i `update_tour` (mirror) + `submit_customer_order` + `update_container_order`. **Fix:** Erstattet `is_normal_tour` med `is_co2_tour = tt in ("normal", "loes_afhentning")`. CO2-faktor snapshottes ved bestilling og beregnes når chaufføren rapporterer vægt.
3. **6 legacy `loes_afhentning`-ordrer** mangler CO2 → kørt én-gangs migration der slog CO2-kategori op fra `plads.material_co2_categories` og populerede `co2_type_id`, `co2_type_name`, `co2_factor`, `co2_kg`.
4. **`ContainerOrderUpdate` manglede flere felter** (`estimated_count`, `loose_estimated_count`, `custom_address`, `workshop_*`) → tilføjet så edit-modalen kan opdatere alle.

**Frontend (`App.js`):**
5. **`handleUpdateTour`** opdaterede `tours[]` men IKKE `selectedTourForPanel` → panelet beholdt stale tour-prop. **Fix:** Tilføjet `setSelectedTourForPanel(prev => res.data hvis samme id)`. `fetchTours` polling synkroniserer også panelet ved fjern-opdateringer.
6. **`MobileTourPanel` useEffect** kørte kun ved `tour?.id`-skifte → re-init af `containerWeights` skete ikke når tour-prop fik nye vægte. **Fix:** Init kun ved mount/tour-skift; sync via parent-prop. Brugerens lokale "næste-vægt"-felt bevares.
7. **Multi-vægt-UI'en skjult bag `askingWeight`-flag** → bruger kunne ikke se eller tilføje til eksisterende drafts efter genåbning. **Fix:** `askingWeight` initialiseres til `true` ved mount når `tour.tour_type === "loes_afhentning" && !tour.completed`. UI ER ALTID synlig for løs afhentning. Cancel-knap fjernet for løs afhentning.
8. **"Gem udkast" tilføjer automatisk nyt tomt felt** efter succesfuldt gem så chaufføren ikke skal lede efter "+Tilføj vægt".
9. **Ny prominent "Tilføj vægt"-knap** (stor amber-dashed) vises kun når sidste række har en gyldig vægt.
10. **Vægt-input-farver** ændret fra `dark:bg-slate-800 text-slate-900` (sort på mørkeblå) → `bg-white dark:bg-amber-50 text-amber-950 font-mono font-bold` (læsbar i begge themes).
11. **Soft-validation på Afslut** for ALLE opgavetyper (`window.confirm` med materiale + vægt + container-antal). Forhindrer fejlklik.
12. **`OrderInfoLine`**: skjuler purple Wrench-chip når isLoes (duplikat med amber LØS AFHENTNING badge).
13. **CustomerOrderPage** "Mine bestillinger"-detalje: viser nu "Løs afhentning" (ikke "Normal afhentning") + CO2-data hvis ordren har det.
14. **`OrderEditModal`** har nyt reduceret felt-set for `loes_afhentning` (samme princip som estimat): Opgavetype låst, Prioritet, Antal containere, Bestillingsdato, Kommentar. Sender `loose_estimated_count` til backend.
15. **"Udkast"-badge** (pulsende blå) vises på bestillingssiden mens chaufføren stadig tilføjer vægte.

**Tests:**
- `/app/backend/tests/test_phase15_41_loes_afhentning.py` — 6/6 PASS
- `/app/backend/tests/test_phase15_43_loes_draft.py` — 5/5 PASS:
  * T1: Draft-PATCH uden completed.
  * T2: Flere drafts opdaterer progressivt.
  * T3: Drafts spejles til container_orders.
  * T4: Endelig completion afslutter turen.
  * T5: PUT response inkluderer container_weights + loose_estimated_count (regression vagt).

---


## What's new in 2026-02-22 (Fase 15.42 + 15.43 — Løs afhentning UI-pol)

### 🟢 Fase 15.42 — Prioritetsvalg + tydelig "LØS AFHENTNING"-markering (DONE)

**Bruger-rapport:** *"Når man opretter en løs bestilling fra 'tilføj tilpasset bestilling' skal man også kunne vælge prioritet... derudover på bestillingssiden under 'mine bestillinger' og på chaufførsiden skal det highlightes bedre, ikke separat sektion."*

**Implementering (frontend kun, `App.js`):**
1. **Prioritetsvælger på Løs afhentning-formular** (~L2680): 3 knapper (HASTER/NORMAL/LAV) med samme look som almindelige bestillinger. Default = "normal". Testid: `loes-priority-{haster|normal|senere}`.
2. **Submit sender `priority` korrekt** (~L2754): `priority: priority || "normal"` — ikke længere hardcoded "normal".
3. **Amber LØS AFHENTNING badge i OrderInfoLine** (~L246): Solid amber bg + hvid tekst + Truck-ikon. Vises i Mine bestillinger og Alle bestillinger. Testid: `order-loes-badge-{order_id}`.
4. **Chaufførside MobileTourCard** (~L4826): Amber LØS AFHENTNING badge (solid bg, hvid tekst, Truck-ikon) ERSTATTER den tidligere diskrete purple opgavetype-chip. Plus ny `tour-loes-count-{tour_id}` chip der viser estimeret containerantal. HASTER-prioritets-pulsen virker uændret oven på.

### 🟢 Fase 15.43 — Draft-gem på løs afhentning + bug-fix på grøn Afslut-knap (DONE)

**Bruger-rapport:** *"På chauffør siden skal løs afhentning kunne gemmes flere gange undervejs... gem udkast så man senere kan lave en final 'gem'. Derudover når man vælger løs tur 'afslut' så står der 'afslut tur' i gult og 'afslut' i grønt — fjern den gule. Dog virkede den grønne ikke for løs tur, så fiks det. Også: sort skrift på mørkeblå baggrund i vægt-input er svær at læse."*

**Implementering (frontend `App.js`):**
1. **`handleSaveLooseDraft`** (~L13192): Ny handler der PATCHer tour med `container_weights` UDEN `completed:true`. Backend opdaterer `weight` som SUM automatisk og spejler til container_orders. Driver kan kalde flere gange undervejs.
2. **Multi-vægt-UI redesign** (~L13315): Erstattede den gule "Afslut tur"-knap med en BLÅ "💾 Gem udkast"-knap. Hjælpetekst: *"Tryk på den grønne Afslut-knap nederst når alle containere er vejet."*
3. **Grøn "Afslut"-knap fix** (~L13524): To-trins flow — første klik åbner multi-vægt UI; andet klik (når UI er åben + mindst 1 vægt > 0) kalder direkte `handleConfirmLooseWeights` for endelig afslutning. Eliminerer dobbelt-CTA-forvirring.
4. **Input-farver fixet** (~L13325): Tidligere `dark:bg-slate-800 text-slate-900` gav sort-skrift-på-mørkeblå. Nu `bg-white dark:bg-amber-50 text-amber-950 font-mono font-bold` — tydeligt læsbar i begge themes, matcher amber-temaet.
5. **"Udkast"-badge på bestillingssiden** (~L283): Når `looseRegistered > 0 && !order.completed` vises en pulsende blå "UDKAST"-badge ved siden af vægt-info så order-user ved at chaufføren stadig er i gang.
6. **Save-ikon tilføjet til imports** fra `lucide-react`.

**Backend (`server.py`):** Ingen ændringer nødvendige — `update_tour` accepterede allerede `container_weights` uden `completed`, beregnede sum, og mirrorede til ordren. Pytest dækker nu også draft-flowet.

**Tests:**
- `/app/backend/tests/test_phase15_41_loes_afhentning.py` — 6/6 PASS (regression)
- `/app/backend/tests/test_phase15_43_loes_draft.py` (NY) — 4/4 PASS:
  * T1: Draft-PATCH uden completed → array+sum opdateret, completed ikke sat.
  * T2: Flere på hinanden følgende drafts opdaterer progressivt.
  * T3: Drafts spejles til container_orders med weight_kg men status forbliver pending/in_progress.
  * T4: Endelig completed=True afslutter turen og spejler status="completed".

---


## What's new in 2026-02-22 (Fase 15.40c — Dynamisk feature-polling)

### 🟢 Fase 15.40c — Live feature-flag-opdatering uden re-login (DONE)

**Bruger-rapport:** *"Nu har jeg slukket 'estimat' og nu fjerner den ikke dynamisk på logistik admin siden under planlægning. Sørg for at det virker. Når man slukker skal det væk og når man slår til skal den på."*

**Implementering:**
1. **Frontend polling-loop** (`AuthContext.jsx`): `setInterval(reloadFeaturesOnly, 30_000)` + initial fire ved mount + lytter på `focus`/`visibilitychange`-events. Henter `/clients/me/features` og opdaterer `user.features` i React state — kun hvis værdier rent faktisk er ændret (undgår unødvendige re-renders).
2. **Rate-limit exempt** (`server.py` global rate limit middleware): `/api/clients/me/features` er undtaget fra 120-req/min-global-limiteren. Ellers ville en travl admin's poll-trafik blive blokeret efter få minutter.
3. **Effect deps optimeret**: `useEffect` lytter på `user?.id` (ikke hele `user`-objektet) så interval ikke resettes hver gang features ændres.

**Polling-frekvens:**
- Hver 30. sekund
- Også straks ved app-mount (efter login eller page-refresh)
- Også straks når browser-fanen får fokus (typisk når brugeren skifter tab tilbage)

**Verificeret end-to-end:**
- SA toggler ARGO estimate=OFF → ILK's `/clients/me/features` returnerer `false` → React state opdateres → "Planlæg ressourcer"-tab **forsvinder fra ILK's UI** inden for 30 sek. ✓
- SA toggler ARGO estimate=ON → ILK's poll returnerer `true` → tab dukker op igen ✓

**Screenshot-evidens:** ILK's Planlægning-fane viser kun "Planlæg ture" + "Tidsregistrering" når ARGO=OFF. Når ARGO=ON er "Planlæg ressourcer" også synlig.

**Designvalg:**
- 30s polling-interval er et godt kompromis: hurtigt nok til "føles dynamisk" uden at overbelaste backend.
- Browser-throttling i baggrunden er acceptabelt — `focus`+`visibilitychange`-listenerne dækker tab-switch-scenariet.
- Eksisterende rate-limit-middleware (120 req/min) blokerede polling — fix via path-exempt-set.

---

## What's new in 2026-02-22 (Fase 15.40b — LA aggregerer kunde-features)

### 🔧 Fase 15.40b — Bug-fix: LA-bruger aggregerer features fra kunderne de betjener (DONE)

**Bruger-rapport:** *"Jeg har aktiveret 'estimat' for en kunde, men når jeg tjekker logistik admin siden under 'Planlægning' dukker 'Planlæg ressourcer' ikke frem?"*

**Bug-roden:** I første implementering var LA's `user.features.estimate` udelukkende baseret på LA-FIRMAETS eget `client_features`-row. Men toggle ligger pr. KUNDE (per dit valg 1=A), så LA's egen flag var altid OFF → tab vistes aldrig.

**Fix (`get_features_dict_for_user` i `server.py`):**
- Læser nu firmaets `serves_company_ids` (LA-firma → list af kunder de betjener).
- For hver feature: **OR-aggregering** på tværs af alle kunder. Hvis MINDST ÉN kunde har feature ON, så får LA også feature ON.
- Customer-brugere (order/customer_admin/location_admin) får uændret deres EGET firmas features.

**Design rationale:**
- ARGO har estimate=ON → ILK serves ARGO → ILK ser estimate=ON i sin planlægning → "Planlæg ressourcer"-tab vises.
- Hvis ALLE kunder har estimate=OFF → ILK ser estimate=OFF → tab skjules.
- Hvis SA toggler en kunde fra OFF→ON, slår det automatisk igennem hos LA's brugere ved deres næste login.

**E2E verificering (ARGO=ON, ILK serves ARGO):**
- ILK login → `user.features.estimate = true` ✓
- ILK navigeret til Planlægning → "Planlæg ressourcer"-tab SYNLIG ✓
- Klik tabben → Estimat-bestillinger vises (Tegl × 6 fra Helsingør Forsyning — også selvom Helsingør Forsyning IKKE har estimate=ON, fordi tab-synligheden er på LA-niveau, ikke per-ordre)

**Tests (`/app/backend/tests/test_phase15_40_client_features.py` — 9/9 PASS + 1 skip):**
- T6b (NY): LA aggregates customer features verified — ARGO=ON → ILK ser estimate=ON.

---

## What's new in 2026-02-22 (Fase 15.40 — Klient-platformsfunktioner)

### 🟢 Fase 15.40 — Administrer Klientplatformsfunktioner (DONE)

**Bruger-spec:** Tilføj en super-admin-fane hvor man kan toggle platforms-features per klient. Start med `estimate`. Features skal slå igennem automatisk uden ødelagte UI.

**Bruger-valg:**
- (1) Klient = **Kunde-organisationen** (kunder som ARGO, Helsingør Forsyning)
- (2) Placering = **Ny top-level tab** i SuperAdminPage
- (3) UX = **Lokal toggle + eksplicit "Gem"-knap**
- (4) Cache = **Ved næste login/refresh** (acceptabelt at ændringer kræver re-login)
- (5) Default = **DISABLED for ALLE klienter** (også eksisterende)

**Backend (`server.py` + `auth.py`):**
- Konstant `FEATURE_KEYS = {"estimate": "..."}` — let at udvide med nye features.
- `client_features`-collection med doc-skema: `{company_id, feature_key, is_enabled, updated_at, updated_by_user_id, updated_by_email}`
- Helpers: `get_company_features(company_id)`, `is_feature_enabled(company_id, key)`, `get_features_dict_for_user(company_id)` — bruges fra både API og auth-pipeline.
- 3 nye endpoints:
  - `GET /api/admin/companies/{id}/features` (super_admin) — fuld liste med audit-felter
  - `PATCH /api/admin/companies/{id}/features/{feature_key}` (super_admin) — upsert + activity_log entry
  - `GET /api/clients/me/features` (any auth) — kompakt `{key: bool}` dict for nuværende bruger
- `UserPublic` udvidet med `features: Dict[str, bool]` — sendes både ved `/auth/login` og `/auth/me`.

**Frontend (`App.js` + `AuthContext.jsx` + `SuperAdminPage.jsx`):**
- `useFeatureFlag()` central hook i `AuthContext` — returnerer `(key) => bool`. Læser fra cached `user.features`. Brug overalt hvor UI skal gates.
- **Sted 1: Bestillingsside → Opret tilpasset bestilling** (`CustomerOrderPage`): "Estimat"-mode-option SKJULES helt (grid skifter til 1 kolonne) + form-rendering defensiv-gated. `useFeatureFlag()("estimate")` → false: ingen DOM-spor.
- **Sted 2: Logistik admin → Planlæg → Planlæg ressourcer** (`AdminPage`): "Planlæg ressourcer"-tab-knap SKJULES + `<PlanningResourcesView/>` rendering defensiv-gated.
- **Super Admin → ny tab "Administrer Klientplatformsfunktioner"** (`ClientFeaturesPanel`):
  - 2-kolonne layout: venstre = klient-liste med søg + select; højre = feature-tabel pr. klient
  - Pr. række: feature-navn, beskrivelse, "Sidst ændret: {dato} af {email}", toggle-switch
  - "Ugemt"-badge + tæller; "Gem ændringer"-knap kun aktiv ved dirty state; "Annuller"-knap fjerner lokale ændringer
  - Audit-feltet `updated_at` + `updated_by_email` opdateres automatisk ved hver PATCH
  - Sucess-toast: *"Gemt ✓ (N ændringer)"*; partial-failure toast: *"Gemt delvist..."*

**Fremtidssikring:**
For at tilføje en NY feature: (1) Tilføj key til `FEATURE_KEYS` i `server.py`; (2) Wrap UI-elementet med `useFeatureFlag()("ny_key")`. Backend + super-admin-tab håndterer det automatisk.

**Tests (`/app/backend/tests/test_phase15_40_client_features.py` — 8/8 PASS, 1 skip):**
- T1: Default DISABLED for nye klienter ✓
- T2: PATCH toggle'r korrekt + skriver audit-felter (updated_at, updated_by_email) ✓
- T3: Ukendt feature_key → 400 ✓
- T4: Ukendt company_id → 404 ✓
- T5: Non-super-admin (logistics_admin) → 403 ✓
- T6: `/clients/me/features` returnerer kompakt dict ✓
- T7: `/auth/me` indeholder `features`-felt ✓
- T8: `/auth/login`-respons indeholder `features`-felt ✓
- T9: Toggle propagerer til auth-pipeline (skipped — kræver order-bruger med kendt password)

**E2E Playwright verifikation:**
1. SA → klik tab "Administrer Klientplatformsfunktioner" → panel rendres med 3 kunder (ARGO, Customer A, Helsingør Forsyning)
2. Klik ARGO → feature-tabel viser Estimate-toggle, "aldrig ændret"
3. Klik toggle → "ugemt"-badge + "1 ugemt ændring" tæller + "Gem"-knap aktiveres
4. Klik "Gem ændringer" → grøn toast *"Gemt ✓ (1 ændring)"*
5. Tabel viser nu "Sidst ændret: 22.06.2026, 15.31 / doganmiketuran@gmail.com"

**Aktivitetslog:** Hver feature-toggle skrives også til `activity_log`-collection så super-admin kan spore historik gennem eksisterende activity-log-skærm.

---

## What's new in 2026-02-22 (Fase 15.39 — HASTER-puls stopper på "på vej")

### 🟢 Fase 15.39 — HASTER-chip pulserer kun i VENTER, stopper i PÅ VEJ (DONE)

**Bruger-rapport:** *"På chauffør-siden, når en tur er en 'haster-tur' så blinker feltet 'haster' og det ser fint ud. Men det gør det kun når tur-status er 'på vej'. Lav det om så den blinker i 'venter'-status og stopper med at blinke når den er i 'på vej'-status."*

**Logik (frontend `App.js`, 2 steder):**
- Tidligere: `isHasterChip && !tour.completed` → pulserer i BÅDE "venter" + "på vej", stopper kun på "færdig".
- Nu: `isHasterChip && !tour.completed && !tour.on_way` → pulserer KUN i "venter", stopper i "på vej" + "færdig".

**Steder ændret:**
1. `TourCard` (linje ~4582-4594) — `animate-haster-pulse`
2. Hoved-driver-listen (linje ~17578-17590) — både `animate-haster-pulse` (HASTER-sektion) og `animate-haster-pulse-strong` ("Mine ture"-sektion)

**Rationale:** Pulsen er en opmærksomheds-krog der skal trække chaufførens øje til ledige HASTER-ture. Når chaufføren først er "på vej" til en HASTER-tur, har pulsen gjort sit job — fortsat pulsering er unødvendig støj og distraherer fra de andre ledige HASTER-ture på skærmen.

---

## What's new in 2026-02-22 (Fase 15.38 — Strikt partner-scope på bestillinger)

### 🔴 BUG-FIX — Multi-tenant data-isolation lækage på kundebestillinger (DONE)

**Bruger-rapport:** *"Når en medarbejder bestiller en container på bestillingssiden vælger de først 'logistik partner', men bestillingen vises på chauffør- og logistik-admin-siden for BÅDE Logistik Partner A OG Partner B. Dette er forkert — det skal adskilles!"*

**Røde tråd (root cause):**
- `order.partner_id` (medarbejderens valg i partner-pickeren) blev gemt korrekt på `container_orders`.
- MEN `assigned_logistics_company_ids` (synligheds-listen) blev sat til **HELE pladsens partner-liste** `[A, B]` uafhængigt af medarbejderens valg.
- Både `/api/tours` (driver + LA), `/api/plads` og admin tour-overblikket bruger `assigned_logistics_company_ids` til at filtrere → derfor lækage til alle partnere knyttet til pladsen.

**Fix (`server.py` `submit_customer_order` — Fase 15.38):**
```python
_chosen_partner = (order.partner_id or "").strip()
if _chosen_partner and _chosen_partner in _location_partners:
    doc["assigned_logistics_company_ids"] = [_chosen_partner]   # NEW: kun den valgte partner
elif _chosen_partner and not _location_partners:
    doc["assigned_logistics_company_ids"] = [_chosen_partner]   # plads uden liste → respekter valget
else:
    doc["assigned_logistics_company_ids"] = _location_partners  # legacy QR-flow uden picker
```
`tour_doc["assigned_logistics_company_ids"]` arvet fra `doc` så fixet propagerer automatisk til driver-/admin-turen.

**Database-oprydning på brugerens anmodning:**
- Slettet alle `container_orders` (96 docs), `tours` (28 docs), `customer_orders_history` (18 docs), `tour_audit_log` (173 docs).
- **Bevaret:** users, companies, plads, drivers, vehicles, trailers, messages, driver_sessions, driver_time_entries, tour_counters, invitation_tokens, activity_log, container_overrides, container_counts, delivery_addresses, workshops, reports.

**Tests (`/app/backend/tests/test_phase15_38_partner_scope.py` — 4/4 PASS):**
- T1: Multi-partner plads + `partner_id=A` → ordre+tour får `[A]` (ikke `[A, B]`).
- T2: Multi-partner plads + INTET `partner_id` (legacy QR) → bevarer hele pladsens liste (backwards-compat).
- T3: Multi-partner plads + ugyldigt `partner_id` (ikke knyttet til pladsen) → defensiv fallback til pladsens fulde liste (forhindrer total skjul).
- T4: To ordrer på samme plads med hver sin partner_id → fuldstændig kryds-scope-adskillelse verificeret.

**E2E API-verificering (efter cleanup):**
- Submit ordre via `POST /api/customer-orders/submit` med `location_code=2893` (multi-partner: ILK + City Container), `partner_id=ILK` → DB-tur har `assigned=[ILK]`.
- Login som **ILK admin** → `GET /api/tours` viser KUN Pap-touren (deres egen) ✓
- Login som **City Container admin** → `GET /api/tours` viser KUN Plast-touren ✓
- Kryds-leakage GONE.

**Samlet test-status:** 14/14 PASS (Fase 15.35 + 15.36 + 15.38 kombineret).

---

## What's new in 2026-02-22 (Fase 15.37 — Filter-flyt + bugfix)

### 🟢 Fase 15.37 — "Mangler stempel" + "Vis slettede" flyttet til "Alle registreringer"-tabellen + bug-fix (DONE)

**Bruger-rapport:** *(1)* `Send påmindelse`-knappen returnerede *"Ingen chauffører har åbne stemplinger"* selvom UI tydeligt viste 2 chauffører med "1 mangler"-badges.
*(2)* `Mangler stempel`-filter knappen lå i den øverste værktøjslinje — uintuitivt, da den skal filtrere rækkerne i "Alle registreringer"-tabellen.
*(3)* `Vis slettede`-knappen samme problem — hører til tabellens header.

**Bug-fix (`server.py` `_compute_missing_clock_for_drivers`):**
Det forrige filter `entries_filter["company_id"] = la_company` matchede ingenting i produktion, fordi mange legacy `driver_time_entries` slet IKKE har et `company_id`-felt udfyldt (kun `driver_id`). Fix: scope nu via chaufførens user-record (`users.company_id`), ikke entry-feltet. Vi finder først alle drivers i firmaet (via `users`), så queryer `driver_time_entries` med `{"driver_id": {"$in": driver_ids}}` + datointervall + `end_time` mangler + ikke deleted. Det er præcis samme pattern som `/api/admin/time-entries` allerede bruger.

**Verificeret som super_admin (cross-company):** 2 chauffører fundet — Ferdal Turan (3 åbne) + Test Driver (1 åben). Bug elimineret.

**Frontend (`App.js`):**
- Top-værktøjslinjen: **fjernet** "Mangler stempel" og "Vis slettede"-knapperne.
- API-kald: **fjernet** `missing_only=true` query-param fra `GET /admin/time-entries` (filtreringen sker nu client-side).
- Header-bjælke i `Alle registreringer`-tabellen: **tilføjet** `Vis slettede` + `Mangler stempel`-knapperne på højre side. Knapperne vises kun når Detaljeret liste er åben (hvilket er den eneste kontekst hvor de giver mening).
- Flat-list rendering: **wrappet** i IIFE der filtrerer rækker client-side baseret på `showOnlyMissing`. Tom-tilstand:
  - `"Ingen rækker mangler UD-stempel i visningen. ✓"` når filter slået til + tom liste
  - `"Ingen registreringer på denne dato."` når intet filter + tom liste
- Timeline og chauffør-totaler påvirkes IKKE af filteret (kun flat-list rækker).

**Tests (`/app/backend/tests/test_phase15_36_sunday_reminder.py` — 5/5 PASS, opdateret til at tolerere produktionsdata):**
- T1: Tom DB → drv absent / baseline match.
- T2: Seed 2 entries → drv.entries_count = baseline + 2.
- T3: `days_back=1`→baseline+0, `=4`→baseline+1, `=7`→baseline+2.
- T4: Driver-token → 403 *"Adgang nægtet for denne rolle"*.
- T5: Lukket entry (end_time) + soft-deleted entry → entries_count = baseline (ingen stigning).

**Verificeret via Playwright (E2E):** Login som ILK admin → Planlægning → Tidsregistrering →
- Top toolbar har IKKE længere de 2 filterknapper ✓
- Klik "Detaljeret liste" → "Alle registreringer"-header viser nu *"Vis slettede"* + *"Mangler stempel"*-knapperne ✓
- Klik "Mangler stempel" → flat-list filtreres til kun missing-clock rækker; viser tom-tilstand korrekt når ingen matcher ✓

---

## What's new in 2026-02-22 (Fase 15.36 — Søndag aften påmindelse)

### 🟢 Fase 15.36 — Automatisk søndags-mail til chauffører med åbne stemplinger (DONE)

**Bruger-request:** *"jeg vil gerne have en automatisk søndag aften påmindelse til chauffører med åbne missing_clock entries, den skal sendes til deres email som en notification"*

**Specs (bekræftet med bruger):**
- Tidspunkt: **søndag kl. 18:00 Europe/Copenhagen**
- Modtager: **kun chaufføren** (ikke admin-CC)
- Vindue: **kun de seneste 7 dage** (ugentlig oprydning)
- Manuel trigger: **ja**, knap i Admin → Planlægning → Tidsregistrering

**Backend (`server.py`):**
- `_compute_missing_clock_for_drivers(days_back, company_id=None)` — aggregerer åbne entries (`end_time` mangler, `is_deleted!=true`, `cutoff <= date < today`) via `_raw_db` (bypass tenant), grupperer pr. driver_id, slår navn+email op fra `users`-kollektionen. Kun aktive drivers med email returneres.
- `send_weekly_missing_clock_reminders(days_back, company_id=None)` — kalder email_service pr. driver, returnerer `{sent, skipped, drivers: [{driver_id, name, email, entries_count, delivered, error}]}`.
- `POST /api/admin/missing-clock/send-reminders?days_back=7` — `require_role("logistics_admin","super_admin")`. Logistics admin scopes til eget firma (`la_company`); super admin sender på tværs af alle firmaer. `days_back` clampes til 1..90.
- `_seconds_until_next_sunday_1800()` + `sunday_evening_reminder_task()` async loop — sover indtil næste søndag 18:00 Europe/Copenhagen, kalder `send_weekly_missing_clock_reminders(days_back=7)`, sover 90s, gentager. Registreret via `async_lib.create_task()` i `startup_db_client`.

**Email (`email_service.py`):**
- `send_missing_clock_reminder_email(to_email, name, entries, days_back=7)` — bygger HTML-mail med tabel (Dato, IND-tidspunkt, Type), branded shell, dansk tekst. Subject: *"Manglende stempel — N registrering(er) mangler at blive lukket"*. CTA-knap linker til `APP_PUBLIC_URL/`.
- Genbruger eksisterende `_send()` + `EMAIL_OVERRIDE`-banner-logik.

**Frontend (`App.js`):**
- Ny knap [data-testid='planning-time-send-reminders-btn'] i PlanningTimeOverview, ved siden af CSV-knappen — orange Mail-ikon, deaktiveret under request, viser confirm-dialog først, så toast med resultat (sent/skipped/empty-state).
- `sendingReminders` state + `sendMissingClockReminders()` handler.

**Tests (`/app/backend/tests/test_phase15_36_sunday_reminder.py` — 5/5 PASS):**
- T1: Tom DB → `sent=0`, `drivers=[]`.
- T2: Seed 2 åbne entries (3+5 dage tilbage) → `sent=1`, `entries_count=2`, `delivered=true`.
- T3: `days_back=1`→0, `days_back=4`→1, `days_back=7`→2.
- T4: Driver-token → 403 *"Adgang nægtet for denne rolle"*.
- T5: Lukket entry (med `end_time`) + soft-deleted entry → ingen mail (`sent=0`).

**Verificeret via Playwright:** Login som ILK admin → Planlægning → Tidsregistrering → klik *"Send påmindelse"* → toast vises: *"Ingen chauffører har åbne stemplinger i de seneste 7 dage. Alt er i orden! ✓"*.

**Cron-status ved startup:** `Sunday reminder background task started (every Sunday 18:00 Europe/Copenhagen)` — næste run er logget i `sunday_reminder: sleeping Xs (Yh) until next Sunday 18:00`.

---

## What's new in 2026-02-22 (Fase 15.35 — Strict end>start + Mangler stempel)

### 🟢 Fase 15.35 — `start < end` validering + "Mangler stempel" visualisering (DONE)

**Iteration_49: Backend 5/5 pytest PASS (8 acceptance criteria). Frontend Playwright 100% PASS på validerede stier.**

**Backend (`server.py`):**
- `_compute_duration_minutes` (L4377-4393) returnerer `-1` når `end < start` (ingen overnight wrap). Alle endpoints tjekker `duration_min <= 0` og kaster 400 med dansk besked: *"Sluttidspunkt skal være efter starttidspunkt"*.
- `POST /driver/time-entries` med `end < start` → 400.
- `PATCH /driver/time-entries/{id}` med `end < start` → 400.
- `PATCH /admin/time-entries/{id}` med `end < start` → 400.
- `POST /driver/time-entries/manual-punch` UD < åben IND → 400: *"UD-tidspunkt {HH:MM} er før IND-tidspunkt {HH:MM}"*.
- `_is_entry_missing_clock` (L4400-4412): regel = `date_str < today_local` AND `no end_time`. Undgår false positives på samme-dag åbne slices.
- `GET /admin/time-entries` (L5378+): flagger `missing_clock` pr. entry; tæller `missing_clock_count` pr. chauffør; `missing_only=true`-filter fjerner chauffører uden manglende stempler.

**Frontend (`App.js`):**
- `ManualTimeEntryModal` (L289-305): `computedDuration.invalid=true` ved start≥end → viser rød tekst *"Ugyldig — slut skal være efter start"* + Gem-knap disabled. Testid: `manual-time-duration`, `manual-time-save-btn`.
- `EditOwnEntryModal` (L810) + `AdminEditEntryModal` (L11467): identisk valideringsmønster med `startend-error` selectors.
- Timeline-markør (L11085): åbne IND fra TIDLIGERE dage rendres som 4px-wide rød `animate-pulse` markør (IKKE en fuld bar til 22:00). Testid: `time-bar-missing-{driver_id}-{idx}`.
- Row-badge (L11215): `row-missing-clock-{drv}` viser *"X mangler"* når chauffør har åbne historiske IND.
- Detaljeret liste: `flat-entry-missing-{drv}-{idx}` viser tekst *"Mangler stempel"* på hver åben fortidsentry.
- Filter-knap: `planning-time-toggle-missing` toggler *"Mangler stempel"* ↔ *"Vis alle"*.

**Verificeret manuelt + via testagent (Playwright):**
- T1: POST end<start → 400 dansk fejl ✅
- T2: Manuel UD før åben IND → 400 ✅
- T3-T4: Driver/Admin PATCH end<start → 400 ✅
- T5: YESTERDAY åben IND → `missing_clock=true`, count≥1 ✅
- T6: `missing_only=true` filter virker ✅
- T7: Pairing UD samme dato fjerner `missing_clock` flag ✅
- T8: TODAY åben entry har `missing_clock=false` (regression sikret) ✅
- Frontend: timeline-markør 4px (ikke fuld bar), row-badge, flat-list badge, filter toggle, ManualTimeEntryModal disabled save → ALLE PASS ✅

**Test fil:** `/app/backend/tests/test_phase15_35_strict_endtime_and_missing_clock.py`

---

## What's new in 2026-02-22 (Fase 15.34 — Driver hard-delete)

### 🟢 Fase 15.34 — Driver DELETE er nu HARD-delete (DONE)

**Problem:** Bruger rapporterede at slettede time-slices "stadig sad fast" — fx Ud-knappen var grået ud på forkerte tidspunkt efter sletning. Brugerønske: *"sørg for at en sletning fjerner referencen helt så den ikke sidder fast."*

**Fix:** `DELETE /driver/time-entries/{id}` (driver-side) er ændret fra soft-delete til **HARD-delete**. Entry'en fjernes permanent fra databasen. Eliminerer hele kategorien af edge-case-bugs hvor soft-deleted entries kunne lække ind i logik via en glemt filter-clause.

**Admin-side bevares som soft-delete** (`DELETE /admin/time-entries/{id}`) — admins har stadig "Vis slettede"-toggle + audit-trail.

**Migration:** Eksisterende `deleted=True`-records (fra tests/tidligere sessions) blev hard-cleaned ved deploy.

**Verificeret manuelt:** Seed → DELETE → bekræftet doc fjernet fra DB → ny IND kan oprettes umiddelbart efter uden konflikt.


## What's new in 2026-02-22 (Fase 15.33 — Manuel stempel transition-logik)

### 🟢 Fase 15.33 — Manuel IND/UD følger samme transition-logik som fysisk stempel (DONE)

**Problem:** Chauffør kunne ikke oprette en manuel "Pause" (slice_type=pause) når en åben work-slice eksisterede — fik fejlen *"Der er allerede en åben IND-stempling kl. 18:11 på den dato — afslut den først."* Den fysiske /punch endpoint understøttede transitionen, men den manuelle gjorde ikke.

**Fix (backend, `server.py` `/driver/time-entries/manual-punch`):**
Manuel IND følger nu **præcis samme regler som /punch**:
- **Ingen åben slice + slice_type=work** → almindelig manuel IND.
- **Ingen åben slice + slice_type=pause** → 409 *"Du skal være stemplet ind på arbejde før du kan starte pause."*
- **Åben work + slice_type=pause** → atomisk: luk work ved payload.time, åbn ny pause-slice.
- **Åben pause + slice_type=work** → atomisk: luk pause ved payload.time, åbn ny work-slice.
- **Åben slice af SAMME type** → 409 *"Du er allerede i {arbejde|pause} kl. XX:XX — afslut den først eller skift type."*

Tidligere transition-logik var KUN i `/driver/time-entries/punch` (fysisk knap). Nu er manuel og fysisk identiske — chauffør kan glemme at stemple skift mellem work/pause og rette det bagudrettet via manuel.

**Verificeret manuelt (6/6 curl-tests PASS):**
- T1: Manuel IND work 08:00 (ingen åben) → 200.
- T2: Manuel IND pause 12:00 (åben work) → 200, transition: work 08:00→12:00 + pause 12:00→åben.
- T3: Manuel IND work 12:30 (åben pause) → 200, transition: pause 12:00→12:30 + work 12:30→åben.
- T4: Manuel IND work 12:45 (åben work) → 409 "allerede i arbejde kl. 12:30".
- T5: Manuel UD 17:00 → lukker den åbne work.
- T6: Final state — 3 entries: work 08:00-12:00 (240m), pause 12:00-12:30 (30m), work 12:30-17:00 (270m).


## What's new in 2026-02-22 (Fase 15.32 — Edit/Slet på hver række + CSV-export + visuelle fikse)

### 🟢 Fase 15.32 — Per-row edit/slet, CSV-eksport, åben-cap, chauffør-filter (DONE)

**Iteration_47 + iteration_48: Backend 9+14=23/23 PASS. Frontend 5/6 admin-criteria PASS (driver-side 1/1 ikke E2E-testet pga. tom seed; data-testids verificeret i kode).**

**Backend (`server.py`):**
- `_verify_driver_owns_manual` opdateret regel: chauffør må nu redigere/slette ALLE sine egne entries (`driver_id==self`) — kun admin-oprettede (`created_by_role IN ('logistics_admin','super_admin')`) er låste. Tidligere krævede `manual=True ∧ created_by_role='driver'`.
- `PATCH /admin/time-entries/{id}` (NY) — admin opdaterer felter (date, start, end, slice_type, reason). Overlap-tjek med `exclude_id=self`. Multi-tenant company-scope tjek. **Ingen** fremtid-validering (kun manuel stempel-events er underlagt fremtid-blokering pr. spec).

**Frontend (`App.js`):**
- **Slet-knap virker nu** — erstattet `window.confirm` (PWA-blokeret) med to-trins state-baseret bekræftelse (`pendingDeleteId`): første klik viser "Bekræft slet" + "Annullér"; bekræft kalder DELETE.
- **Edit + Slet på HVER egen entry på chaufførsiden** — uanset auto IND/UD eller manuel. Vises ikke for admin-oprettede.
- **Edit + Slet på HVER række i admin's Detaljeret liste** — pr. række data-testid `flat-entry-actions-{driver}-{idx}`, `flat-entry-edit-...`, `flat-entry-delete-...` + to-trins bekræftelse.
- **`AdminEditEntryModal` (NY)** — admin redigerer date/start/end/slice_type/reason med single click. Validerer overlap via backend.
- **Åbne entries i timeline cappes** til current local time (kun dags-dato) — fylder ikke længere hele dagen ud. Beregnes via `nowMinFromStart` baseret på `Date.now()` + hoistede `HOUR_START/HOUR_END`-konstanter.
- **Chauffør-filter dropdown** [`planning-time-driver-filter`] — påvirker timeline, detaljeret liste og CSV-download. "Alle chauffører" eller specifik.
- **CSV-download knap** [`planning-time-csv-btn`] — eksporterer Detaljeret liste til Excel-DK-venlig CSV (UTF-8 BOM + semicolon-separator). 12 kolonner: Chauffør, Dato, Start, Slut, Varighed (min), Type, Manuel, Manuel-type, Årsag, Slettet, Slettet af, Oprettet af rolle. Filnavn: `tidsregistrering_YYYY-MM-DD[_DriverName][_med-slettede].csv`.

**Bugfix (TDZ ReferenceError):** Phase 15.32-initial-version havde TDZ-fejl — `downloadCsv` og `nowMinFromStart` brugte `HOUR_START`/`HOUR_END` 50 linjer FØR deres deklaration. Hoistet konstanterne til toppen af `PlanningTimeOverview` for at fixe (iteration_48 verificeret OK).

**Adgangsregler — opdateret tabel:**
| Entry-type                                            | Chauffør rediger | Chauffør slet |
|-------------------------------------------------------|------------------|---------------|
| Egen manuel (`created_by_role`='driver')             | ✓                | ✓             |
| Egen automatisk IND/UD (`created_by_role`='')         | ✓ (NYT)          | ✓ (NYT)       |
| Admin-oprettet (`created_by_role`='logistics_admin') | ✗                | ✗             |

**Test-filer:** `/app/backend/tests/test_phase15_32_admin_patch_and_auto_edit.py` (9 tests, 9 PASS) + Phase 15.31 regression 14/14 PASS.


## What's new in 2026-02-22 (Fase 15.31 — Fremtid-validering + driver edit/delete + soft-delete)

### 🟢 Fase 15.31 — Manuel stempel: fremtid-blokering, ejer-edit/delete, soft-delete (DONE)

**Bekræftet via iteration_46.json: Backend 14/14 PASS, Frontend live OK.**

**Backend (`server.py`):**
- `_is_future_datetime(date, time)` — sammenligner dato+klokkeslæt mod current local time i Europe/Copenhagen (+1 min buffer). Bruges af `/driver/time-entries/manual-punch` (driver + admin).
- `_not_deleted_filter()` — global Mongo-filter; anvendes overalt hvor entries hentes (driver GET, admin GET, overlap-check, punch/manual-punch "allerede åben"-tjek).
- **Future-blokering på Manuel stempel:** Både driver- og admin-kald får 400 ved fremtidig dato eller fremtidig klokkeslæt i dag. Returnerer dansk besked.
- **Periode (admin):** `POST /driver/time-entries` er UNDTAGET fremtid-blokering (jf. brugerens spec).
- `PATCH /driver/time-entries/{id}` (NY) — driver kan opdatere SIN EGEN manuel entry: felter `start_time`/`end_time`/`date`/`reason`/`slice_type`. Revaliderer fremtid + overlap. Ejer-tjek: `manual=true ∧ created_by_role='driver' ∧ driver_id==self ∧ deleted!=true`. Fejlkoder: 400 (fremtid), 403 (ikke egen / auto-stempling / admin-oprettet), 404 (ikke fundet), 410 (allerede slettet), 409 (overlap).
- `DELETE /driver/time-entries/{id}` (NY) — soft-delete egen manuel entry. Audit-felter: `deleted=true`, `deleted_at`, `deleted_by_id`, `deleted_by_name`, `deleted_by_role='driver'`.
- `DELETE /admin/time-entries/{id}` — konverteret til soft-delete by default. `?hard=true` til permanent fjernelse (test-cleanup).
- `GET /admin/time-entries?date=X&include_deleted=true` (NYT toggle) — viser slettede entries med `deleted=true` på hver entry. Default false skjuler dem. **`deleted_count`-feltet pr. chauffør beregnes via separat `$group` aggregation** så badge-tælleren altid er korrekt uanset toggle-state.

**Frontend (`App.js`):**
- **Driver-topbar OPRYDDET:**
  - 🗑️ Fjernet "Manuel"-knappen (`manual-time-entry-btn`) — manuel oprettes nu via "Tilføj manuel" inde i Dagens stempling-modalet (klokke-overview).
  - 🗑️ Fjernet pause-quick-knapper "15m"/"30m"/"45m" — ikke længere relevante med slice-baseret pause.
  - `time-overview-btn` (klokke-knappen) er nu ALTID synlig (også uden entries — viser "Stempling"-label).
- **ManualPunchModal:** Inline fejl `manual-punch-future-error` + disabled save-knap når dato/tid er i fremtiden. Lokal validering + autoritativ backend-tjek.
- **EditOwnEntryModal (NY)** — vist når chaufføren klikker "Rediger" på egen manuel entry. Felter: dato, start, slut, type (work/pause), årsag. Future-error + disabled save når fremtid-tid indtastes. PATCH'er backend, viser toast "Manuel registrering opdateret".
- **Dagens stempling-modal:** Hver entry der ejes af chaufføren (manual+created_by_role=driver) har nu `time-entry-own-actions-N` med 2 knapper: "Rediger" (`time-entry-edit-N`) + "Slet" (`time-entry-delete-N`). Slet → confirm → DELETE → toast "Manuel registrering slettet".
- **Admin Planlæg → Tidsregistrering:** Ny `planning-time-toggle-deleted`-knap (vises kun når Detaljeret liste er slået til). Når aktiv → `?include_deleted=true` + slettede entries vises overstreget + `flat-entry-deleted-{driver}-{idx}`-badge med audit-info i tooltip. Timeline ekskluderer slettede entries via `.filter(e => !e.deleted)`.
- **UX:** Efter ManualPunchModal save OG efter EditOwnEntryModal save: time-overview-modal genåbnes automatisk så chaufføren ser den friske entry og kan redigere/slette med det samme.

**Adgangsregler (chauffør side, oversigt):**
| Entry-type                           | Rediger | Slet  |
|--------------------------------------|---------|-------|
| Egen manuel (created_by_role=driver) | ✓       | ✓     |
| Egen automatisk fysisk stempling     | ✗       | ✗     |
| Admin-oprettet (uanset om manuel/periode) | ✗  | ✗     |

**Test-fil:** `/app/backend/tests/test_phase15_31_future_softdelete.py` (14 tests, 14 PASS).


## What's new in 2026-02-22 (Fase 15.30 — Start pause + overlap-validering)

### 🟢 Fase 15.30 — Pause som ny slice-type + global overlap-blokering (DONE)

**Bekræftet via iteration_44.json: Backend 12/12 PASS, Frontend live-verificeret.**

**Princip:** Pause er IKKE en parallel mekanisme — det er endnu en slice-type i samme ind/ud-kæde. Hvert tryk lukker det aktive slice og åbner det næste atomisk med samme tidspunkt.

**Datamodel-tilføjelse:**
- `driver_time_entries.slice_type ∈ {"work","pause"}` — default "work" for bagudkompatibilitet. Eksisterende docs uden feltet behandles som arbejde.

**Backend (`server.py`):**
- `_check_time_overlap(driver_id, date, new_start, new_end, exclude_id)` — fælles helper. Bruges fra `/punch` (efter atomisk transition), `/manual-punch` og `/driver/time-entries` (admin periode). Returnerer dansk fejl med eksisterende periodes start/slut.
- `TimePunch.slice_type`: 
  - `type=ind + slice_type=work` + ingen åben → standard IND.
  - `type=ind + slice_type=pause` på åben work → atomisk: luk work + åbn pause.
  - `type=ind + slice_type=work` på åben pause → atomisk: luk pause + åbn work.
  - `type=ind + slice_type=pause` uden åben work → 409 "Du skal være stemplet ind på arbejde før du kan starte pause."
  - `type=ind + slice_type=samme som åbne` → 409 "Du er allerede i {arbejde|pause} kl. XX:XX."
  - `type=ud` lukker den åbne slice uanset type.
- `ManualPunch.slice_type` + `ManualTimeEntry.slice_type`: chauffør/admin kan oprette pause-slices direkte.
- `GET /admin/time-entries`: returnerer nu `work_minutes` + `pause_minutes` + `total_minutes` pr. chauffør.

**Frontend (`App.js`):**
- **Driver-knaprække** (3 tilstande):
  - Ingen åben slice → grøn "Ind" + grå "Ud".
  - Åben work → blå "Start pause" + orange "Ud".
  - Åben pause → grøn "Start arbejde" + orange "Ud".
- **Driver-day-overview-modal**: 3 tal i bunden — Arbejde / Pause / Total. Hver entry har en "ARBEJDE"/"PAUSE" badge med ikon.
- **Driver collapsed-toolbar**: viser `{wh}t {wm}m +Xm P` + "PAUSE"/"ÅBEN" badge.
- **ManualPunchModal**: ny "Hvilken slags slice?"-toggle (vises kun for IND) — Arbejde (grøn) / Pause (blå).
- **ManualTimeEntryModal**: samme toggle. "Beregnet varighed" får (pause — tæller ikke som arbejdstid) hint.
- **Admin PlanningTimeOverview**:
  - 3 totals i header: Arbejde / Pause (kun hvis >0) / Tilstede.
  - Per-row: arbejdstid + "+Xt Ym pause" hvis driver havde pauser.
  - Timeline: pause-bars i blå, work-bars i grøn. Åbne pulser i deres farve.
  - Legend opdateret: Arbejde / Åben arbejde / Pause / Åben pause / Manuel.
  - Detaljeret liste: ny slice-badge ("Arbejde"/"Pause") på hver entry.

**Overlap-validering:**
- Manuel-punch (driver + admin): 409 hvis IND-tidspunkt falder inden i eksisterende periode.
- Admin-periode: 409 hvis [start,end) ∩ [eksisterende] ≠ ∅. Besked: "Periode HH:MM–HH:MM overlapper med eksisterende {arbejde|pause}-periode HH:MM–HH:MM. Vælg et andet tidsrum."
- Fysisk `/punch` post-transition: tjekker at den lige-lukkede slice ikke overlapper andre (exclude_id på den lukkede entry).

**Test-fil:** `/app/backend/tests/test_phase15_30_pause_overlap.py` (12 tests, 12 PASS, isoleret 2026-01-15 + cascade-delete cleanup).


## What's new in 2026-02-22 (Fase 15.29 — Fjern duplikeret HASTER + pulserende ramme)

### 🟢 Fase 15.29 — Én HASTER-markering pr. tur-kort (DONE)

**Mål:** Tur-kort viste tidligere "HASTER" to steder: (a) som badge øverst ved siden af materiale/lokation/bestillingstype-badges OG (b) som prioritets-chip i info-rækken med flag-ikon. Derudover pulserede der en rød ring/glow rundt om hele kortets ramme. Bruger ønsker kun ÉN HASTER-markering (chippen i info-rækken).

**Ændringer (kun frontend, `App.js`):**
- **`renderSoloTour`** (~L16700): fjernet HASTER/HØJ/LAV-badge (`tour.priority !== "normal"` blok) ved siden af container/customer/source-badges i tur-titel-rækken.
- **`renderSoloTour`** (~L16660): fjernet `animate-haster-border-pulse`-klasse + `showMineHasterPulse`/`_soloIsHaster`-detektion. Border bruger nu altid `statusStyle.border` (statisk farve pr. status).
- **Hænger-kort** (~L16250): samme fix — duplikeret HASTER/HØJ/LAV-badge fjernet i titel-rækken.
- **Beholdt:** Prioritets-chippen i info-rækken (med flag-ikon + `animate-haster-pulse`/`animate-haster-pulse-strong`) er uændret og er nu eneste HASTER-markering.

**Resultat (verificeret i smoke-test):** Driver UI viser 0 "HASTER"-tekst-forekomster på tur-kort + 0 pulserende ramme-elementer; prioritets-chip "Haster" med flag-ikon vises 1 gang pr. HASTER-tur og pulserer som forventet.



### 🟢 Fase 15.28 — Split manuel tidsregistrering (DONE)

**Mål:** Chauffører får single-event (IND eller UD) manuel stempling — admin får legacy periode-baseret (start + slut) på vegne af en chauffør. Konfigurerbart krav om "Årsag" pr. firma.

**Backend (allerede gjort i forrige session, valideret i denne):**
- `POST /api/driver/time-entries/manual-punch` — event-baseret (IND/UD), FIFO-pairing over midnat.
  - Chauffør: driver_id afledes altid fra token; payload-felt ignoreres.
  - Admin: skal angive driver_id i payload.
- `POST /api/driver/time-entries` — periode-baseret. Kun logistics_admin/super_admin (driver → 403).
- `PATCH /api/company/payroll-settings` — partial-update, accepterer `require_driver_punch_reason` + `require_admin_punch_reason` uden at klobre payroll-felter.
- `GET /api/company/punch-reason-settings` — slank read-endpoint til frontend.

**Bugfix 1 (kritisk — backend startede ikke):**
- `server.py` linje 8125 havde syntax-fejl: function body på samme linje som `def...:` → `IndentationError`.
- Fix: split funktion + body på separate linjer.

**Bugfix 2 (kritisk — admin overblik viste 0 rækker):**
- To `@api_router.get("/admin/time-entries")` registreret samtidigt; FastAPI brugte først-registrerede (flat-list med date_from/date_to), som skjulte den per-driver struktur frontend forventede.
- Fix: omdøbt flat-list-endpoint til `/admin/time-entries-list`. Per-driver `/admin/time-entries?date=` virker nu.

**Frontend (nyt i denne session):**
- `PlanningTimeOverview` (`App.js` ~L10460): 3 nye admin-knapper i sub-tab "Tidsregistrering":
  - `planning-time-open-punch-btn` → `ManualPunchModal` (admin-mode, driver-dropdown, IND/UD).
  - `planning-time-open-period-btn` → `ManualTimeEntryModal` (admin-mode, driver-dropdown, start+slut).
  - `planning-time-toggle-list` → `planning-time-flat-list` viser alle entries m. **"Manuel"-badge** + årsag-tekst.
- `AdminSettingsPanel` (Indstillinger-fanen): ny kort `settings-punch-reason-card` med 2 auto-gemmende toggles:
  - `settings-require-driver-reason-toggle` — "Krav om årsag for chauffører"
  - `settings-require-admin-reason-toggle` — "Krav om årsag for admin"
  - Hver toggle PATCH'er payroll-settings og viser toast "Krav om årsag opdateret".

**Testing (iteration_43.json):** Backend 12/12 pytest PASS. Frontend admin + driver flows valideret live (modaler, toggles, badges, toast).


## What's new in 2026-06-19 (iteration_39 — Fase 15.3: Andre-chaufførers PÅ VEJ ture skjult + Tidsregistrering-overblik)

### 🟢 Fase 15.3 — Bugfixes + nyt admin-overblik (DONE)

**Bugfix 1 — "PÅ VEJ" ture fra andre chauffører skjult:**
- Root: når admin frigjorde en tildelt tur via `driver_id=""`, blev `on_way` + `claimed_by*` IKKE ryddet. Andre chauffører så herefter en orphan-"PÅ VEJ"-tur uden ejer.
- Fix backend (`server.py` ~line 1772-1800): når admin frigør (driver_id="" eller claimed_by=""), ryd også `on_way`, `on_way_time` og hele claim-state'en (claimed_by, claimed_by_id, claimed_at) hvis claim hørte til den fjernede chauffør.
- Fix frontend: defensiv filter i `fetchTours` der ALTID skjuler tours hvor `on_way=true && !mine` — uanset hvad backend leverer.

**Bugfix 2 — Kapacitetsvalidering tællede på tværs af chauffører:**
- Root: `t.claimed_by_id === (selectedDriver?.id || "")` matchede ALLE ledige (claimed_by_id="") ture når `selectedDriver.id` var tom — falsk overskred kapacitet på tværs af alle chauffører.
- Fix: kræv ikke-tomt id/navn før vi tæller — `(myId && t.claimed_by_id === myId) || (myName && t.claimed_by === myName)`.

**Forbedring 3 — Forsinkede mine-ture vises altid for ejeren:**
- `fetchTours` henter altid `?limit=500` og inkluderer:
  - I dag (reportDate): alle
  - Tidligere ikke-afsluttede: kun mine (eller alle hvis toggle on)
  - Fremtidige: aldrig
  - Tidligere afsluttede: aldrig
- Røde "X dage forsinket"-badges allerede på MobileTourCard fra iter 38.

**Feature 4 — "Tildelt af" synlig for admin:**
- Ny `admin-assigned-by-{tour.id}` chip under driver-knappen i adminens tur-overblik. Viser "Tildelt af X" når en LA/SA har tildelt turen.
- Chauffør-side viser allerede `tour-assigned-by-{id}` (iter 36).

**Feature 5 — Ny "Tidsregistrering"-undersektion i Planlægning:**
- Backend: `GET /api/admin/time-entries?date=...` returnerer pr-chauffør timeline med entries, total_minutes, has_open, first_in, last_out, entries_count. Role-gated til logistics_admin/super_admin.
- Frontend: Ny `PlanningTimeOverview`-komponent — SuccessFactors-inspireret timeline:
  - Per chauffør: avatar + navn + first_in → last_out
  - 06-22 timeline med farvekodede intervaller (grøn=lukket, pulsing-grøn=åben, blå=manuel)
  - Top-bar med aggregerede tal: aktive nu / færdige / ikke aktive / total tid
  - Auto-refresh hvert 30 sek
  - Tilgængelig via `planning-tab-time` ved siden af `planning-tab-assign`

**Tests:**
- `/app/backend/tests/test_phase15_3_release_and_time_overview.py` — 2/2 GREEN.
- Regression: **15/15 backend pytest GREEN** (Phase 14 + 15 + 15.1 + 15.2 + 15.3).


## What's new in 2026-06-19 (iteration_38 — Fase 15.2: "På vej" rootfix + Afventende-toggle)

### 🟢 Fase 15.2 — Bug + UX (DONE)

**Root cause "På vej virker ikke på admin-tildelte ture":**
- `GET /api/tours` filtered med `active_cid` strict-AND mod `company_id`. LA-skabte ture har `company_id = LA's egen virksomhed`, men chaufførens `active_cid` er kundens id (fx ARGO). Filtret skjulte derfor admin-tildelte ture for chaufføren.
- Chaufføren kunne se turen i "Afventende ture"-modal'en (som loopede over en separat liste) men ikke i hoved-state `tours[]`. Når chaufføren trykkede "På vej" → `handleToggleOnWay` kaldte `tours.find(t => t.id === tourId)` → **fandt INTET → returnerede stille uden fejl-toast**.
- **Fix** (`server.py` line ~1147): Driver's `partnership_clause` er nu et `$or` der også matcher `{driver_id: <driver_uid>}` → pre-assigned ture er ALTID synlige for den tildelte chauffør uanset kunde.
- Backend test: `/app/backend/tests/test_phase15_2_admin_assigned_visibility.py` — 1/1 GREEN.

**"Afventende ture"-knappen flyttet ned + integreret i hovedlisten:**
- Modal-baseret tilgang FJERNET (`showPendingToursModal` → `showPendingInList` toggle).
- Ny `afventende-toggle-btn` placeret VED SIDEN AF søgefeltet (lige over tur-listen) i stedet for i toolbar.
- Når toggle ON: `fetchTours` henter `/api/tours?limit=500` og inkluderer alle ikke-afsluttede ture fra i dag + tidligere fra hele chaufførens scope. `filteredTours` tillader nu også ture fra andre pladser at vises hvis de er pending-from-past — så chaufføren kan starte dem direkte uden at skifte plads.
- Røde `tour-delay-{id}` "X dage forsinket" badges på selve MobileTourCard når `tour.date < today`.
- Backend `date`-felt på turen RØRES IKKE — original dato er bevaret.
- `afventende-toggle-note` lille hjælpetekst når toggle on.

**Tests:**
- 13/13 backend pytest GREEN (Phase 14 + Phase 15 + 15.1 + 15.2).


## What's new in 2026-06-19 (iteration_37 — Fase 15.1: Driver UX refinements)

### 🟢 Fase 15.1 — Pending tours modal, date-locked punch buttons, FIFO + midnight block, OrderEditModal field-swap, planning collapse bugfix (DONE)

**Backend (`server.py`):**
- Punch FIFO pairing: `update_tour` punch-out branch nu `sort=[("start_time", 1)]` (ASC) — ÆLDSTE åbne IN matches først (SuccessFactors-princip).
- Midnatsblokering: hvis ingen åben IN findes for dagen MEN en åben IN findes på en TIDLIGERE dato → 409 med dansk besked "Kan ikke stemple ud efter midnat. Brug Manuel tidsregistrering."

**Frontend (`App.js`):**
- **OrderEditModal** (Mine bestillinger / Alle bestillinger):
  - `handleTypeChange` nu rent felt-skift — IKKE længere soft-validation ved on-change.
  - `_doSave()` kører `getFieldsToClear` ved Gem; hvis felter ryddes → soft-validation dialog (`edit-type-change-confirm`) → bekræft via `edit-type-change-confirm-btn` ("Gem og ryd felter").
  - "Byt container" (flyt) skjuler nu BÅDE leveringsadresse OG værksted-felter (`showAddress = !workshopType && !flytType`).
  - Skift til normal viser leveringsadresse igen øjeblikkeligt.
- **Planning collapse-isolation**: ny `planningCollapsedDrivers` Set (i stedet for "expanded set med all-expanded-when-empty"-trick). Default alle åbne; klik på chevron → kun den valgte chauffør collapser, andre uberørt.
- **Driver date-locked knapper** (`isFuture` flag på line ~10640):
  - `punch-in-btn` + `punch-out-btn` deaktiveret når `reportDate !== today` (titel-tooltip).
  - `manual-time-entry-btn` deaktiveret kun for fremtidige datoer; i dag + tidligere OK.
- **Ny "Vis alle afventende ture"-modal** (`pending-tours-modal`, åbnes via `pending-tours-btn`):
  - Full-screen på mobil.
  - Viser ikke-afsluttede ture for i dag + tidligere; fremtidige skjult.
  - Inkluderer unclaimed, claimed_by==me, og driver_id==me (admin-pre-assigned).
  - Skjuler ture claimed/assigned til andre chauffører.
  - Rød `pending-delay-{id}` badge på ture før i dag: "X dage forsinket" (kalenderdage).

**Tests:**
- `/app/backend/tests/test_phase15_punch_fifo_midnight.py` — 2/2 GREEN.
- Regression: Phase 14 (5/5) + Phase 15 (5/5) + Phase 15.1 (2/2) = **12/12 backend pytest GREEN**.
- Frontend live-verified på iter_37: planning collapse driver-isolation perfekt; date-locked Ind/Ud + Manuel tooltips korrekte; pending-tours-modal åbner med korrekt empty-state.
- Test report: `/app/test_reports/iteration_37.json`

### Carry-over P0
- **ilkdistadmin@gmail.com password drift** (3. iteration i træk): kræver Mongo bcrypt-reset hver gang. Root cause endnu ikke fundet — ikke i startup-seed, ikke i synlige test-scripts. Mitigation:
  ```python
  cd /app/backend && python -c "import asyncio,bcrypt,os;from motor.motor_asyncio import AsyncIOMotorClient;from dotenv import load_dotenv;load_dotenv('/app/backend/.env');async def m():cli=AsyncIOMotorClient(os.environ['MONGO_URL']);db=cli[os.environ['DB_NAME']];h=bcrypt.hashpw(b'TestPass2026!',bcrypt.gensalt()).decode();await db.users.update_one({'email':'ilkdistadmin@gmail.com'},{'\$set':{'password_hash':h,'failed_login_attempts':0,'locked_until':None}});asyncio.run(m())"
  ```


## What's new in 2026-06-19 (iteration_36 — Fase 15: Logistik Planlægning rework)

### 🟢 Fase 15 — Tour numbers, bulk-assign, admin-assignment attribution, planning rework (DONE)

**Backend (`server.py`):**
- `Tour` model fået 4 nye felter: `tour_number`, `assigned_by_id`, `assigned_by_name`, `assigned_at`.
- `_generate_tour_number(customer_code, customer_name)` helper — atomisk `find_one_and_update` på `tour_counters`-kollektionen med `$inc` + upsert. Format: `{PREFIX}-{nnnn}` (4-cifret zero-padded). PREFIX = customer_code uppercase, ellers 3 første bogstaver af customer_name, ellers "TUR".
- `POST /api/tours` og `POST /api/tours/bulk` auto-genererer `tour_number` hvis ikke sat.
- `TourCreate` udvidet med `customer_name`, `customer_code`, `tour_type`, `capacity_*`, `order_date`, `created_by_*` så koden kan bygges korrekt.
- `POST /api/tours/bulk-assign` — ny endpoint: body `{tour_ids:[], driver_id, driver_name}`. Role-gated til LA/SA (driver=403). Sætter `driver_id/name`, `assigned_by_id/name`, `assigned_at` + audit-log pr. tur.
- `PUT /api/tours/{id}` — når LA/SA sætter `driver_id` eller claimer på vegne af, populeres `assigned_by_*` automatisk. Når `driver_id=""` eller `claimed_by=""` ryddes `assigned_by_*` igen.
- `PUT /api/tours/{id}` (driver) — hvis `assigned_by_id` er sat OG driver sender `claimed_by=""` eller `claimed_by_id=""` → 403 "Denne tur er tildelt af administrator — kontakt din logistikadmin for at frigøre."
- Migration `/app/scripts/migration_phase15_backfill_tour_number.py` — 210 ældre ture fået `tour_number` retroaktivt.

**Frontend (`App.js`):**
- `formatCapacity(obj)` helper bruges nu overalt — chip viser `{label} ({m³} m³)` på Driver-kort, OrderInfoLine, order-success, mm.
- `OrderEditModal` modeller "Bekræft og rediger"-step:
  - Felter vises/skjules dynamisk efter `tour_type`: normal/flyt → leveringsadresse; vaerksted/afhent_vaerksted → værksted-snapshot (navn/adresse/tlf) med dropdown der auto-udfylder.
  - Soft-validation dialog (`edit-type-change-confirm`) før typeskift når noget vil blive ryddet.
  - Send tomme værdier for irrelevante felter → backend rydder data + audit-logger pr. felt.
- Planlægning-fanen totalt rewritet (`planning-workspace`):
  - Checkbox pr. ikke-tildelt tur (`planning-bulk-check-{id}`) + "Vælg alle" (`planning-select-all`).
  - Sticky bulk-bar (`planning-bulk-bar`) der dukker op ved ≥1 valg — chauffør-dropdown (`planning-bulk-driver-select`) tildeler alle valgte i én handling via `POST /tours/bulk-assign`.
  - Ny "Tildelte ture pr. chauffør"-sektion (`planning-assigned-section`) — collapsible per driver med tour-cards der viser turkode, status, lokation og "Tildelt af X kl. HH:mm" + Frigiv-knap (kun for ikke-startede ture).
  - Hver række (både ikke-tildelt og tildelt) viser `tour_number` badge (`planning-tour-number-{id}`, `tour-number-{id}`).
  - Kapacitetsvalidering FJERNET fra admin-siden — ingen `1/1`/`2/2` badges, ingen "Over kapacitet"-italic-tekst. Drivers panel viser kun antal tildelte ture i dag.
- "Hurtigt overblik" Fuldførte (data-testid=`quick-overview-completed`) bruger nu `planningTours` (alle kilder) i stedet for `adminTours` (kun manuel+argo) — customer-order-ture tæller med i realtid (5s polling).
- Driver MobileTourCard viser to nye chips: `tour-assigned-by-{id}` ("Tildelt af {Navn}") og `tour-number-{id}`.
- Driver MobileTourPanel: "Fortryd"-knap er skjult når `assigned_by_id` er sat — i stedet vises info-boks `mobile-tour-panel-admin-locked` med besked om at kontakte logistik-admin.

**Tests:**
- `/app/backend/tests/test_phase15_logistik_rework.py` — 5/5 GREEN.
- Regression suite (Phase 14): 5/5 GREEN.
- Test report: `/app/test_reports/iteration_36.json`


## What's new in 2026-06-18 (iteration_35 — Fase 14: Korrigér ture)

### 🟢 Fase 14 — Driver "Ret vægt" + Admin "Ret tur" (DONE)
**Driver MobileTourPanel (`App.js`):**
- "Fortryd" knappen vises KUN når `tour.on_way && !tour.completed`. Tidligere blev den også vist på afsluttede ture.
- Afsluttede ture viser i stedet info-banner `mobile-tour-panel-completed-notice`: **"Turen er afsluttet — kontakt din logistikadmin ved fejl."**
- Ny `mobile-tour-panel-edit-weight-btn` ("Ret vægt") på afsluttede `tour_type=normal` ture giver chaufføren mulighed for at korrigere vægten uden at genåbne turen. Bagved: `PUT /api/tours/{id}` med `claimed_by` sat for at omgå backend's restricted_fields-guard.
- Plads-vælgeren (`plads-dropdown-btn`) begrænset fra fuld bredde til `max-w-[260px]` så badget sidder lige ved siden af navnet (ingen tomrum).

**Admin "Ret tur" modal (`App.js`):**
- Ny `Edit2` (pencil) knap pr. tur-række i "Ture i {plads}" overblikket (data-testid `edit-tour-btn-{id}`).
- Åbner `EditTourModal` med: opgavetype-select, vægt-input (kun for `normal`), "Genåben tur"-checkbox (kun for afsluttede), Gem, Annullér og Slet.
- Genåbning sender `{completed:false, on_way:false, claimed_by:'', claimed_by_id:''}` så turen vender tilbage til "Venter" og kan tages af enhver chauffør igen.

**Tests:**
- `/app/backend/tests/test_phase14_edit_tour.py` — 3/3 GREEN (driver edits weight on completed tour, admin reopens, restricted_fields 409 guard).
- Test report: `/app/test_reports/iteration_35.json`


## What's new in 2026-06-17 (iteration_51 — Fase 8 Regression + Fase 9 CO2-beregning)

### 🟢 Fase 8 — Fuld rolle-isolation regression test (DONE)
- Ny pytest: `/app/backend/tests/test_phase8_role_isolation.py` — 13/13 grøn
- Dækker alle 6 roller: `super_admin`, `logistics_admin`, `customer_admin`, `location_admin`, `order`, `driver`
- Kritiske isolation-tests:
  * SA ser alle companies på tværs af tenants
  * LA-X (m. partnered cust_a+cust_b) ser begge kunders plads; LA-Y (uden partners) ser ingen
  * CA-A blokeret fra at læse/redigere CA-B's plads (403)
  * Order-rolle ser KUN egen lokations container_orders
  * Driver med active_customer_id=cust_a ser KUN cust_a's plads
  * Driver kan IKKE pre-tildele (Fase 6 silent strip)
  * Driver blokeret fra audit-log (403)
  * Cross-LA tour-isolation
  * SA kan se enhver tours audit-log
- Samlet regression: pytest 2/3/4/4.1/5/6/8 = 48/48 grøn

### 🟢 Fase 9 — CO2-beregning på bestillinger (DONE)
**Backend** (`server.py`):
- Ny collection `co2_types` — per-kunde materialebibliotek (scope: customer's `company_id`)
- Ny model `CO2Type {id, company_id, name, factor (kg CO2/ton), active, created_at}`
- Endpoints:
  * `GET /api/co2-types` — alle roller i kunden læser
  * `POST /api/co2-types` — kun customer_admin (egen kunde) + super_admin
  * `PUT /api/co2-types/{id}` — customer_admin (egen kunde) + super_admin
  * `DELETE /api/co2-types/{id}` — blokeres hvis aktive ordrer bruger typen
- Order-model udvidet: `co2_type_id, co2_type_name (snapshot), co2_factor (snapshot), weight_kg, co2_kg`
- Auto-beregning: ved order-create snapshot navn+faktor; ved weight_kg-update → co2_kg = factor × (kg/1000)
- Også mirroret i `update_tour` når chaufføren leverer vægten

**Frontend**:
- `CustomerAdminPage` ny tab "CO2-typer" med CRUD-modal (Leaf icon, emerald accent)
- Bestillingsformular: ny "CO2-type"-dropdown (vises kun hvis kunden har oprettet typer)
- Edit-modal: kan ændre CO2-type bagefter — auto-recalc
- Mine bestillinger: nye linjer "CO2-type", "Vægt (kg)" og "CO2" — viser snapshot factor + "afventer chauffør" placeholder
- Rapport-tab: ny KPI "CO2 (kg)", 2 nye charts ("CO2-udvikling over tid" LineChart + "CO2 pr. materiale" BarChart)
- Excel-eksport: ny "CO2-aftryk pr. materiale" sektion + CO2-kolonne i "Pr. lokation" + samlet CO2 KPI

**Pytest** (`test_phase9_co2.py`): 13/13 grøn — alle 3 brugereksempler verificeret:
  * Træ (80 kg/ton) × 500 kg = 40.0 kg CO2 ✓
  * Metal (22 kg/ton) × 1.200 kg = 26.4 kg CO2 ✓
  * Beton (0 kg/ton) × 3.000 kg = 0.0 kg CO2 ✓
- Multi-tenant isolation: CA-A ser ikke CA-B's typer; cross-tenant edit 403
- Sletning blokeres hvis aktive ordrer bruger typen (409)
- Negativ faktor afvises (400)

## What's new in 2026-06-17 (iteration_50 — Fase 6 Audit-modal + Fase 7 UI-modernisering + Driver kunde-isolation fix)

### 🔴 P0 Bug — Chauffør så ikke genbrugspladser efter kundeskift (FIXED)
- **Root cause**: DriverPage's `useEffect` for `/api/plads` afhang kun af `authUser.id` + `authUser.company_id` — IKKE af `activeCustomer.id`. Da `handleSwitchCustomer` rydder `pladsList` til `[]` men ikke trigger refetch, blev listen tom indtil næste side-reload. Samtidigt blev `selectedPlads` restored fra forrige session (fx "SAC" fra Helsingør Forsyning) selv om driver nu var på ARGO — gav "ghost" valg i header.
- **Fix**: 
  1. Tilføjede `activeCustomer?.id` til `useEffect` deps for `/api/plads` refetch
  2. Ny validation `useEffect` der rydder `selectedPlads` hvis det ikke længere findes i `pladsList`
  3. `fetchTours` deps udvidet med `activeCustomer?.id` (tours refetcher også ved kundeskift)

### 🟢 Fase 6 follow-up — Audit-log tidslinje-modal (DONE)
- Ny komponent `TourAuditLogModal` viser iMessage-style tidslinje af alle assign/reassign/release-events for en tur
- LA klikker `History`-ikon ved `Tildel`-dropdown → modal åbner og fetcher `GET /api/tours/{id}/audit-log`
- Hver entry vises med farve-kodet badge (Tildelt=indigo, Frigivet=grey, Om-tildelt=amber), tidsstempel (da-DK locale), `before → after` driver-navn, brugernavn + rolle
- Lukker via X-knap, klik udenfor, eller Escape

### 🟢 Fase 7 — UI-modernisering AdminPage (DONE)
- **Header**: Mørk slate (`#0F172A`), sticky top, røde brand-ikon (Shield i red-600 firkant), kompakt typografi
- **Tabs flyttet INDE I header**: pill/underline-style med rød border-bottom for aktiv tab (matcher CustomerAdminPage)
- **Kunde-filter dropdown**: ny `data-testid="filter-customer"` i Filtre-sektion med "Alle kunder" + dynamiske kunde-options
- **Vælg Genbrugsplads grupperet per kunde**: Hver kunde får sin egen overskrift (uppercase tracking-wide) + ramme — ARGO og Helsingør Forsyning vises adskilt
- **Quick Stats**: Modernized til icon-on-left card design (rounded-2xl, shadow-sm, hover-shadow-md). Røde FileText / grønne CheckCircle2 / blå Weight / amber Building2

### 🟢 Backend forbedringer
- `GET /api/plads` enriches hver plads med `customer_name` + `customer_code` (hentet fra `companies` collection) — nødvendigt for kunde-gruppering på begge sider
- Plate-picker fallback: free-text input (`data-testid="setup-plate-input"`) — `/api/drivers` returnerer 401 for drivers, så preset-knapper var altid tomme. Nu kan chaufføren altid indtaste pladen selv.

### Test status
- Backend pytest 2/3/4/4.1/5/6: 35/35 grøn
- Frontend testing agent (iteration_30.json): 13/13 review-request assertions PASS
  * Default tab Statistik ✓
  * Alle 7 tabs renderer indhold ✓
  * Kunde-filter virker ✓
  * Plads grupperet pr. kunde ✓
  * Tildel-dropdown + audit-knap ✓
  * Pre-assign + release toasts ✓
  * Audit-modal tidslinje åbner/lukker ✓
  * Modernized header + Quick Stats ✓
  * Free-text plate input ✓
  * Driver ser KUN TEST LOCATION ARGO (kunde-isolation) ✓
  * Helsingør Forsyning's pladser USYNLIGE for ARGO-driver ✓

## What's new in 2026-06-16 (iteration_49 — P0 Bugfix + Fase 6: Pre-assignment & Audit log)

### 🔴 P0 Bug — Blank screen på AdminPage faner (FIXED)
- **Root cause**: Ved "Arkiv" merge i forrige iteration blev en `<div className="space-y-4">` wrapper åbnet på linje 5643 men aldrig lukket før linje 7499. Dette betød at ALLE øvrige faner (Manuelle ture, Planlægning, Chauffører, Genbrugsplads, Historie, Bestillinger) plus Quick Stats var nestet INDEN I `{activeTab === "archives" && (…)}` — som evaluerede `false` for alle andre tabs.
- **Fix**: Flyttede `{archivesSubTab === "receipts"}` sub-block + lukkende `</div>)}` op til lige efter PDF sub-tab close, så arkiv-wrapperen lukker korrekt på linje 6024.
- **Bonus fix**: Default-tab ændret fra `"tours"` til `"statistics"` (brugerens ønske). Tyrkisk "Yönetiyor:" i header omdøbt til dansk "Administrerer:".

### 🟢 Fase 6 — Tur-delegering: Pre-assignment + Self-claim (DONE)
- **Backend (`server.py`)**:
  - Ny helper `_tour_audit(tour_id, action, payload, before, after)` skriver til `tour_audit_log` collection
  - `PUT /api/tours/{tour_id}` udvidet:
    - Auth påkrævet (var tidligere ingen auth)
    - Tenant guard: LA/driver kan kun opdatere ture i egen virksomhed eller hos partnered kunde
    - **Driver-restriktioner**: 
      * `driver_id`/`driver_name` strippes silently (kun LA må pre-tildele)
      * `claimed_by_id` skal være == self id (403 hvis B's id)
      * Hvis tur er pre-tildelt anden driver → 403 på enhver opdatering
    - Audit-log: enhver assign/reassign/release fra LA logges
  - `GET /api/tours` udvidet med pre-assignment filter for drivers:
    - Drivers ser KUN ture hvor `driver_id` er tom ELLER == caller id
    - Pre-tildelte ture skjules komplet for andre chauffører
  - Nyt endpoint `GET /api/tours/{tour_id}/audit-log` (LA/SA only, tenant-guarded)
- **Frontend (`App.js`)**:
  - AdminPage tur-tabel: ny "Tildel" kolonne med dropdown der viser alle chauffører
  - `handleAssignTour(tourId, driverId)`: kalder PUT med `driver_id` + viser toast "Tildelt {navn} — kun synlig for denne chauffør" eller "Tur frigivet — åben for alle"
  - Status-badge udvidet: "Tildelt" (indigo) når pre-assigned, "Taget" (blue) når claimed, "Færdig" (emerald), "På vej" (yellow), "Venter" (grey)
  - Driver UI (MobileTourCard): "TILDELT MIG" badge (indigo med users-icon) på pre-assigned ture
- **Pytest**: `/app/backend/tests/test_phase6_preassignment.py` — 11/11 grøn:
  1. Open tour synlig for begge drivers
  2. LA pre-assigner tour til driver A
  3. Pre-assigned tour SKJULT for driver B
  4. Pre-assigned tour synlig for assignment driver A
  5. Driver A kan IKKE sætte `driver_id` (silently stripped)
  6. Driver A kan IKKE self-claim med B's id (403)
  7. Driver A self-claim med eget id (success)
  8. Driver B blokeret fra at opdatere A's pre-assigned tour (403)
  9. LA release (driver_id="") → tur åben for alle igen
  10. Audit-log har 'assign' + 'release' entries
  11. Driver blokeret fra audit-log (403)
- Regression: Fase 2/3/4/4.1/5 alle stadig grøn.

## What's new in 2026-06-11 (this session)
## What's new in 2026-06-12 (iteration_13)
## What's new in 2026-06-12 (iteration_15 — bugfix)
## What's new in 2026-06-12 (iteration_16 — Leveringsadresser feature)
## What's new in 2026-06-12 (iteration_17 — year/active/soft-delete batch)
## What's new in 2026-06-14 (iteration_20 — Brugerkrav-runde 1)
## What's new in 2026-06-15 (iteration_28 — Copy-on-write semantik)
## What's new in 2026-06-15 (iteration_29 — Krav 1 CA Toggle LA + Krav 2 Delta multi-publish)
## What's new in 2026-06-15 (iteration_30 — Forbedret Excel-eksport · ÉT ark + professionel styling)
## What's new in 2026-06-16 (iteration_48 — Cleanup + Fase 5: Multi-kunde isolation chauffør)
### Cleanup på AdminPage:
- Fjernede tabs: **"Oversigt"**, **"Historik"**, **"Bestillinger"** (brugte dem ikke)
- **Merged "Arkiv" + "PDF Arkiv" → én "Arkiv"-tab** med interne sub-tabs ("Dagrapporter (PDF)" + "Chauffør Arkiv (kvitteringer)")
- Default tab nu "Manuelle ture" i stedet for "Oversigt"

### Fase 5 — Multi-kunde isolation (SIKKERHEDSKRITISK):
- **Backend (3 nye endpoints)**:
  - `GET /api/driver/customers` — kunder driverens logistik-firma servicerer
  - `GET /api/driver/active-customer` — current active customer (med automatic stale-state cleanup)
  - `POST /api/driver/active-customer {customer_id}` — sætter active, re-validerer serves-relation, returnerer 403 hvis ikke-served
- **STRICT filter**: `GET /api/tours` og `GET /api/plads` for driver kræver active_customer_id og filtrerer hårdt på `company_id == active_customer_id`. Hvis ikke valgt → tom liste.
- **Helper-fn**: `_driver_serves_customer(payload, customer_id)` — defense-in-depth verificering på HVER request.
- **Real-time tour-status mirror**: bekræftet at eksisterende logik allerede opdaterer `container_orders` (completed, on_way, claimed_by, status, weight, time) når driver opdaterer tour. Kundens "Mine bestillinger" ser status live.
- **Frontend driver-flow**:
  - Efter login + step 2 (greet): hvis 0 kunder → empty-state, hvis 1 kunde → auto-vælg, hvis 2+ → step 3 (kunde-picker)
  - Step 4 (plate-picker) viser nu badge "Kører for: {kunde}" så driver ser kontekst
  - Header-dropdown "Kunde" vises kun ved 2+ kunder, switcher nulstiller tours/plads/selectedPlads så ingen data-leakage
- Pytest: `/app/backend/tests/test_phase5_customer_isolation.py` (7 sikkerhedstests — empty uden valg, 403 på ikke-served, strict filter A vs B, data-swap ved switch, real-time mirror, clear active)

## What's new in 2026-06-16 (iteration_47 — Fase 4.1: Standardiseret Excel-skabelon for manuelle ture)
- **Brugerkrav**: "+ Tilføj ture" (mail-paste), "Upload PDF", "Argo" knapper fjernet — erstattet med én standardiseret Excel-skabelon (à la SuccessFactors).
- **Backend (nye endpoints)**:
  - `GET /api/tours/template` — genererer .xlsx med 8 kolonner: Lokation (dropdown med LA's tilladte pladser), Materiale, Container-nummer, Containertype, Leveringsadresse, Åbningstid, Lukketid, Note. Hidden helper-sheet ("Lokationer") driver data validation. Frosne header-række + farve.
  - `POST /api/tours/upload-template` — parser uploaded .xlsx, validerer hver række, server-re-validerer at Lokation findes i LA's tilladte pladser, deriver `company_id` + `customer_name` auto fra plads, opretter tours med `source="manual"`. Returnerer `{created, errors[]}` med række-specifikke fejl.
- **Tour-model**: nyt felt `container_type` (free-text fx "Lav åben 20 m³") distinct fra `container` (nummer).
- **TourUpdate**: tilføjet `open_from`, `open_to`, `remark`, `container_type` så manuelle ture kan redigeres senere.
- **Frontend AdminPage**:
  - Knapper fjernet: "+Tilføj ture" (mail), "Upload PDF", "Argo" (+ Argo modal helt fjernet)
  - Nye knapper: **"Hent skabelon"** (grøn, Download-icon) + **"Upload udfyldt skabelon"** (blå, Upload-icon)
  - Upload-resultat vises som banner (succes eller række-fejl-liste)
  - Ture-tabel: kolonner splittet til **Åbningstid** + **Lukketid** + **Note** som tre separate kolonner (var én "Åben"-kolonne). Container-type vist ved siden af container-nummer.
- **Dependencies**: `openpyxl==3.1.5` (Python Excel I/O) tilføjet til requirements.txt
- Pytest: `/app/backend/tests/test_phase4_template.py` (5 cases — download m. dropdown, upload skaber tours, fejlhåndtering på ugyldige rækker, tenant-isolation — forbidden plads ikke i dropdown)

## What's new in 2026-06-16 (iteration_46 — Fase 4: Tour-source separation)
- **Backend**: Tour-model får `source: "manual" | "argo" | "customer_order"` (default `"manual"`)
- `POST /api/customer-orders/submit` → tour med `source="customer_order"` (auto-link til ordre)
- `POST /api/import-argo` → `source="argo"` (allerede sat — verificeret)
- `POST /api/tours` → `source="manual"` (default via Pydantic)
- `GET /api/tours?source=X` eller `?source=X,Y` (CSV) — kan filtreres
- **Logistics admin GET /api/tours**: ser nu UNION af egne + kunde-tours (`assigned_logistics_company_ids` matching) — samme pattern som plads i Fase 3
- **Frontend AdminPage**: "Ture"-fanen → omdøbt til **"Manuelle ture"**, fetcher med `?source=manual,argo`. Customer-orders-tours vises i den separate eksisterende "Bestillinger"-fane.
- **Driver UI**: Source-badge på hver tour-række (kun synlig hvis ikke "manual"): grøn **"Bestilling"** for customer_order, lilla **"Argo"** for argo-import. Manuel ture viser ingen badge (default-state).
- Pytest: `/app/backend/tests/test_phase4_tour_source.py` (6 cases — alle 3 sources oprettes korrekt, filter single + CSV virker).

## What's new in 2026-06-16 (iteration_45 — Fase 3: Plads auto-synkronisering)
- **Backend**: `GET /api/plads` for `logistics_admin` returnerer nu UNION af egne pladser + pladser hvor `assigned_logistics_company_ids` indeholder LA's company_id. Når kunde-admin tildeler logistik-firma som partner, dukker pladsen automatisk op for det firmas LA og chauffører.
- **Backend (lock-down)**: `POST/PUT/DELETE /api/plads` returnerer nu **405 Method Not Allowed** for logistics_admin. Pladser administreres EKSKLUSIVT af kunde-admin via `/api/org/locations`.
- **Frontend**: AdminPage "Pladser"-fane er nu **read-only** med:
  - Forklarende info-banner "Pladser oprettes ikke længere her"
  - Badge "Kunde: {navn}" eller "Ad-hoc" pr. plads
  - Ingen tilføj/rediger/slet-knapper
- Pytest: `/app/backend/tests/test_phase3_plads_auto_sync.py` (8 cases — auto-sync, tenant-isolation, blokerede mutationer, CA-update propagerer korrekt).

## What's new in 2026-06-16 (iteration_44 — Fase 2: Chauffør-login via invitations-flow)
- **Drivers er nu users**: Backend gemmer drivers i `users` collection med `role="driver"`. Den gamle `drivers` collection er udfaset (slettet i Fase 1).
- **Invitation-flow**: Logistik-admin opretter chauffør med email → invitation sendt → chauffør sætter password via `/set-password?token=…` → logger ind via standard `/api/auth/login`.
- **Gamle endpoints 410 Gone**: `POST /api/driver/login` og `POST /api/driver/verify-code` returnerer nu 410 med klar besked om at bruge `/api/auth/login`.
- **Tenant-isolation**: Logistics admin A kan ikke se/modify drivers fra logistics company B (verificeret med pytest, 8/8 cases).
- **UI opdateret**:
  - AdminPage driver-tab: email er nu påkrævet (plate er valgfri); "Send invitation"-knap erstatter "Gem"; "Afventer"-badge på pending drivers; mail-icon-knap for "Send invitation igen".
  - SuperAdminPage: "Chauffør adgangskode"-felt fjernet, erstattet med deprecation-besked.
  - Driver setup step 1 (email + driver_code) udfaset — viser nu kun "Gå til login"-knap som fallback.
- **Driver Pydantic-model**: tilføjet `invitation_status` felt; `plate` ikke længere required.
- **Helper-funktioner**:
  - `_user_to_driver_shape(u)` → mapper user til legacy Driver-shape (bagudkompatibilitet)
  - `_require_logistics_admin_or_sa(payload)` → guard for /api/drivers endpoints
- **Nye endpoints**: `POST /api/drivers/{id}/resend-invitation` (kun pending drivers)
- Pytest: `/app/backend/tests/test_phase2_driver_invitation.py` (8 cases — 410 endpoints, invitation flow, accept, login, tenant isolation, update, resend block)

## What's new in 2026-06-16 (iteration_43 — Fase 1: Logistik-data nulstilling)
- **Logistik-modernisering Fase 1 GENNEMFØRT**: Alle logistik-specifikke collections nulstillet, container-side 100% bevaret.
- Slettet: `tours` (17), `reports` (17), `drivers` (1), `container_counts` (4) — i alt 39 dokumenter.
- Ryddet: `tour_id`, `driver_id`, `driver_name`, `tour_completed`, `tour_on_way`, `tour_weight` felter i 17 container_orders (selve ordrerne bevaret, status "pending").
- Bevaret: 4 companies, 10 users, 17 container_orders, alle holiday/material/hours/capacity-kalendere, workshops, delivery_addresses, location_groups, m.fl.
- **Snapshot**: `/app/backups/pre-wipe-20260616T190826Z.json` (65 KB, valid og åbnbar)
- Nyt script: `/app/scripts/wipe_logistics_data.py` (--dry-run / --snapshot-only / --confirm flags, kræver "WIPE LOGISTICS" frase)
- Klar til Fase 2: Chauffør-login via invitations-flow.

## What's new in 2026-06-16 (iteration_42 — Lokation-switcher på bestillingssiden)
- **Feature**: Multi-lokation brugere (både `order`-medarbejder og `location_admin`) kan nu skifte plads direkte på bestillingssiden via et nyt **"Lokation"-dropdown** placeret ved siden af eksisterende "Logistik-partner"-dropdown — ingen log-ud nødvendig længere.
- **Datakilde**: 
  - Order-medarbejder → `/api/plads` (server-side filtreret efter `assigned_plads_ids` + `location_code` — sikker mod leakage).
  - Location admin → `/api/org/locations` (kun deres managed pladser).
- **State-reset**: Ved skift nulstilles ALT bestilling-state (material, container, workshop, kommentar, åbningstider, partner, step) så data IKKE blandes mellem lokationer.
- **Implementering**: Ny `onSwitchLocation(code, name)` prop på `CustomerOrderPage`. Employee-flow opdaterer React state (re-mount via key-skift); LA-flow opdaterer `sessionStorage` + reload.
- Smoke test (`/app/backend/tests/test_location_switcher_smoke.py`): Verificerer at `/api/plads` ikke leaker forbudte plads-koder ✓.
- Filer: `/app/frontend/src/App.js`.

## What's new in 2026-06-15 (iteration_41 — Bestillinger pr. time-diagram fix)
- **Bug**: "Bestillinger pr. time"-diagrammet viste kun "00:00" for alle ordrer, fordi backend læste `open_from` (leveringsvindue — typisk tomt).
- **Fix**: Backend bruger nu `created_at` (faktisk oprettelsestidspunkt) konverteret til **Europe/Copenhagen** lokal tid (håndterer CET/CEST sommertid).
- **Bucketing-strategi**: Floor-to-hour, 24 faste bins (00:00–23:00). Samme tilgang som Google Analytics, Mixpanel, Tableau, Power BI — skalerer fra 10 til 10M ordrer uden at sprænge x-aksen. "14:01" og "14:59" lander begge i "14:00".
- Gælder `/api/org/reports/orders` (LA) + `/api/org/reports/orders-multi` (CA).
- Smoke test (`/app/backend/tests/test_hourly_bucketing_smoke.py`): 3 ordrer ved 14:01, 14:35, 08:15 DK-tid → pattern={"14:00":2, "08:00":1} ✓.

## What's new in 2026-06-15 (iteration_40 — Opgavetype synlig + Værksteder uden dobbelttælling)
- **UI (App.js)**: "Opgavetype" vises nu på hver ordre i både "Mine bestillinger" og "Alle bestillinger" — labels: "Til værksted", "Afhent fra værksted", "Flyt container", "Normal afhentning".
- **Backend (`server.py`)**: `workshop_count`-KPI tæller nu KUN `tour_type='vaerksted'` (til værksted). `afhent_vaerksted` udelukkes for at undgå dobbelttælling — gælder både `/reports/orders` og `/reports/orders-multi`.
- Smoke test (`/app/backend/tests/test_workshop_count_smoke.py`): 2 `vaerksted` + 3 `afhent_vaerksted` + 1 normal → workshop_count=2 ✓.

## What's new in 2026-06-15 (iteration_39 — "Afventer (i alt)" → "Haste bestillinger")
- **UX**: KPI-tilen "Afventer (i alt)" var redundant ift. "Afventer (periode)" og misvisende. Ændret til **"Haste bestillinger"** der tæller ordrer med `priority='haster'` inden for den valgte periode.
- **Backend**: `/api/org/reports/orders` og `/api/org/reports/orders-multi` returnerer nu `urgent_count` (count af `priority=='haster'`).
- **UI**: `LocationAdminPage.jsx` Rapport-tab + `CustomerAdminPage.jsx` rapport-KPI'er bruger nu `urgent_count`. PDF-eksport og Excel-eksport (`excelExport.js`) opdateret tilsvarende.
- Filer: `/app/backend/server.py`, `/app/frontend/src/pages/LocationAdminPage.jsx`, `/app/frontend/src/pages/CustomerAdminPage.jsx`, `/app/frontend/src/lib/excelExport.js`.
- Smoke test: `/app/backend/tests/test_urgent_count_smoke.py` (3 seedede ordrer → 2 haster, urgent_count=2 ✓).

## What's new in 2026-06-15 (iteration_38 — Delta-import dato-aware fix)
- **Fixed**: `op:'add'` i helligdags-delta blev tavst skippet hvis kalenderen havde en helligdag med samme navn (men anden dato). Resulterede i success-toast men 0 tilføjet i kalenderen.
- **Fix**: Backend matcher nu på `navn+dato` for add-ops → forskellige år/datoer for samme helligdag tilføjes som separat række. Idempotent: ægte duplikater (samme navn OG samme dato) skippes.
- **Frontend**: "Allerede publiceret"-kalendere er ikke længere disabled i `DeltaReviewModal` — LA kan gen-vælge dem og trygt klikke igen (backend deduplikerer på navn+dato). Knappen "Publicér igen" vises altid i "Modtagne delta'er"-tab, selv når alle kalendere er markeret som publiceret.
- Regression test: `/app/backend/tests/test_delta_import_date_aware.py` — verificerer både `add 2027 ved siden af 2026` OG idempotent retry.
- Filer: `/app/backend/server.py` (import-endpoint), `/app/frontend/src/pages/LocationAdminPage.jsx`.

## What's new in 2026-06-15 (iteration_37 — Medarbejder-tabel layout fix)
- **Fixed**: Multi-lokation medarbejdere blev tidligere duplikeret som en separat række under HVER tildelt lokation. Nu vises de som **én række** med alle lokationer som chips i en dedikeret "Lokationer"-kolonne.
- **Fixed**: Lokation-chips lå fejlagtigt under "TLF"-kolonnen pga. manglende `<th>` header. EmployeesTable har nu en ordentlig "Lokationer"-kolonne når LA administrerer flere pladser.
- **Fixed**: Tomme TLF/Ansat fra-felter viser nu tom celle i stedet for "—".
- Filer: `/app/frontend/src/pages/LocationAdminPage.jsx` (groups-logik fjernet, EmployeesTable header opdateret, renderRow celle-fallback ændret).

## What's new in 2026-06-15 (iteration_30b — KRITISK FIX: Strict partner-materiale-separation)
## What's new in 2026-06-15 (iteration_31 — Schedule-tab materiale-union)
## What's new in 2026-06-15 (iteration_32 — Strict per-partner ORDRE-isolation)
## What's new in 2026-06-15 (iteration_33 — SA UI forbedringer: toggle, auto-sort, fixed delete)
## What's new in 2026-06-15 (iteration_34 — Login-fix for inaktiv logistik + DB wipe + KPI fix)
## What's new in 2026-06-15 (iteration_35 — Logistik-partner edit + multi-lokation medarbejder + Excel KPI omdøb)

### Brugerklager (runde 9 — verbatim)
> 1. "når jeg editere en eksisterende logistics partner gemmer den ikke admin
>     navn og admin email (man får heller ikke en email til kodegendannelse)"
> 2. "når man logger ind som en almindelig medarbejder, ser man ikke materialer,
>     bestillinger og andre ting"
> 3. "kolonne 'afventer i alt - live' forstår ikke denne... gør den endnu federe"
> 4. "Når man opretter en medarbejder skal man kunne vælge flere lokationer"

### 1. SA logistik-partner edit → opret admin + send invitation
`sa_update_company` opdaterede tidligere kun en EKSISTERENDE admin. Hvis firmaet
blev oprettet uden admin (admin_email tom), skete intet når SA senere udfyldte
felterne. **Fix**: Når `first_admin` ikke findes OG `admin_email` udfyldes, oprettes
en ny `logistics_admin` bruger med `invitation_status=pending` + invitations-email
sendes automatisk via Resend.

### 2. Multi-lokation order-medarbejder
- **Backend** (`server.py`):
  - `org_create_user` (POST /api/org/users) — `order`-rolle kan nu modtage
    `location_codes: [...]` array (samme som location_admin) — alle gemmes i
    `assigned_plads_ids`.
  - `org_update_user` (PUT /api/org/users/{id}) — `location_admin` må nu også
    opdatere `location_codes` for sine `order`-medarbejdere (men kun blandt LA's
    egne pladser; cross-scope returnerer 403).
  - `GET /api/plads` — filtrerer på `assigned_plads_ids` for `order`-rolle, så
    en medarbejder KUN ser deres tildelte pladser, ikke andre i samme firma.

- **Frontend** (`App.js`):
  - Når `order`-bruger har 2+ `assigned_plads_ids` → `PladsPickerPage` vises selvom
    `location_code` er sat. Når kun 1 → spring picker over og gå direkte ind.

- **Frontend** (`LocationAdminPage.jsx` EmployeesTab):
  - Single-select dropdown → multi-select checkbox-liste
  - Form-state har `location_codes: []` array
  - Submit sender både `location_code` (primær) og `location_codes` (alle)
  - Toast-besked: "Invitation sendt — medarbejderen har adgang til N lokationer"

### 3. Excel KPI omdøbning + flere fede metrics
"Afventer i alt - live" omdøbt til **"Åbne bestillinger lige nu"** (tydeligere
betydning). Tilføjet 4 ekstra KPI-bokse + en highlights-bjælke:

**KPI-række 1** (eksisterende, omdøbt):
- Bestillinger i perioden
- Afventer (i perioden)
- Åbne bestillinger lige nu
- Værkstedsbesøg

**KPI-række 2** (NY):
- Samlet vægt (kg)
- Gns. vægt pr. ordre (kg)
- Antal materialer brugt
- Antal medarbejdere aktive

**Highlights-bjælke** (NY):
- Top materiale (navn + antal ordrer + vægt)
- Top medarbejder (navn + antal ordrer)
- Travleste periode (bucket + antal)

Frozen-views opdateret fra `ySplit: 6` → `ySplit: 9` så hele KPI+highlights-blokken
forbliver synlig under scroll.

### Tests (10/10 grøn)
`tests/test_iteration35_round9_user_requirements.py`:
- test_create_logistics_partner_without_admin
- test_edit_logistics_partner_adds_admin_and_sends_invite
- test_subsequent_edit_does_not_recreate_admin
- test_seed_customer_with_3_locations
- test_create_employee_with_multiple_locations
- test_order_employee_plads_endpoint_filters_to_assigned
- test_update_employee_locations_via_la
- test_la_cannot_assign_outside_own_scope
- test_excel_helper_aggregates_correctly



### Brugerklager (runde 8 — verbatim)
> "Når en logistik partner inaktiveres i systemet, og man så prøver at logge
>  ind som en location admin eller anden som historisk har refereret til denne
>  logistik partner, så får man en fejl ved login 'blevet suspenseret'."
>
> "Derudover så rengør systemet for dummy-data (kun behold super admin)."
>
> "På super admin siden, under 'kunder & logistik' de 4 kolonner skal kun
>  betragte currently aktive kunder og ikke de inaktive. Det samme skal være
>  tilfældet med data under 'kunde administration' siden."

### 1. Login-fix for inaktiveret logistik-partner
`_is_company_active` returnerede True/False udelukkende baseret på `active`-feltet,
hvilket blokerede login for ALLE inaktiveres firmaer — også logistik-partnere.
Brugerens semantik er at logistik-partner-deaktivering kun er "UI-listing-only";
selve firmaet og deres brugere skal stadig kunne arbejde.

**Fix**: `_is_company_active` tjekker nu `company_type`. For `company_type=logistics`
returneres altid True. KUN `company_type=customer` blokeres ved suspension.

### 2. Database wipe
- Slettet alle non-SA entries i 22+ collections
- Slettet activity_log
- Kun super_admin tilbage (1 user)

### 3. KPI-kort tæller kun aktive
`PlatformStats` (de 4 store kort på SA-siden) regnede tidligere ALLE firmaer/
brugere/lokationer — inkl. inaktive. Nu filtreres på `active === true`:
- **Kunder**: kun aktive `company_type=customer`
- **Logistik-firmaer**: kun aktive `company_type=logistics`
- **Lokationer**: kun pladser tilhørende AKTIVE kunder
- **Medarbejdere**: kun aktive ikke-SA brugere tilhørende AKTIVE virksomheder

`CustomerAdminsPanel` har også fået ændret default `statusFilter` fra `"all"` til
`"active"` så listen som default kun viser aktive kunde-admins.

### Tests (5/5 grøn)
`tests/test_iteration34_login_logistics_inactive.py`:
   * test_logistics_admin_login_when_company_active — sanity
   * test_logistics_admin_login_when_company_inactive — KERNE-FIX: login virker
   * test_customer_admin_login_when_company_active — sanity
   * test_customer_admin_login_blocked_when_company_inactive — kunde-suspension blokerer stadig
   * test_location_admin_login_works_regardless_of_unrelated_logistics_partner — brugerens KONKRETE flow



### Brugerklage (verbatim)
> "På bestillingssiden, når man opretter en bestilling for den ene logistik
>  partner, så vises bestillingen (under 'mine bestillinger' og 'alle
>  bestillinger') for begge logistik partnere. Det skal isoleres så
>  bestillinger der oprettes kun vises for den valgte logistik partner."

### Root cause
Frontend SENDTE `partner_id` ved submit (linje 627 i App.js), MEN backend's
`StructuredOrderCreate`-Pydantic-model accepterede ikke feltet — det blev
silently droppet. Ordrer blev gemt UDEN `partner_id`. Plus
`GET /container-orders/by-location/{code}` havde slet ingen partner-filter,
så alle ordrer for lokationen blev returneret uanset partner-context.

### Fix (3 ændringer i `server.py`)
1. `StructuredOrderCreate.partner_id: str = ""` tilføjet — Pydantic accepterer nu feltet
2. `ContainerOrder.partner_id: str = ""` tilføjet — persisteres på doc'en
3. `submit_customer_order` sætter `partner_id=(order.partner_id or "").strip()`
4. `GET /container-orders/by-location/{code}?partner_id=X` filtrerer strikt
   (exact match — legacy ordrer uden `partner_id` ekskluderes fra filtreret view)

### Frontend (App.js)
   * `fetchOrderHistory` appender `&partner_id=${partnerId}` til URL'en
   * `useEffect` dependency-array udvidet med `partnerId` så historik
     refetches automatisk når brugeren skifter partner

### Tests (7/7 grøn + 21/21 regression = 28/28)
`tests/test_iteration32_strict_partner_order_isolation.py`:
   * test_submit_orders_for_each_partner — partner_id persisteres
   * test_get_with_partner_a_returns_only_a_orders — strict scope A
   * test_get_with_partner_b_returns_only_b_orders — strict scope B
   * test_get_without_partner_id_returns_both_legacy_and_partner_orders — bagudkompat
   * test_legacy_order_without_partner_id_is_excluded_when_filtering — ingen leak
   * test_user_reported_flow_a_order_invisible_to_b — brugerens KONKRETE flow

Regression: iter30 (16/16) + iter31 (5/5) stadig grønt.



### Brugerklage (verbatim)
> "Materialerne på bestillingsiden skal være optioner i 'åbnings- og
>  lukketidspunkter' tab i location admin siden for følgende to:
>  'tilknyt helligdagskalender til materialer' og 'tilknyt åbnings- og
>  lukketidspunkter for ikke-helligdage' i nuværende version referere
>  den til nogle tidligere materialer (de blev slettet på bestillings-
>  siden) så sørg for at optioner reflektere materialer der findes på
>  bestillingssiden on real time."

### Root cause
Schedule-tabbens dropdowns (Helligdagskalender-til-materiale + Åbningstid-
til-materiale) hentede materialer fra `GET /api/locations/{code}/containers`
UDEN `partner_id`. Endpointet returnerede da `location.materials` — den
gamle pre-partner globale liste. Den indeholdt ofte forældede navne fra før
brugeren skiftede til partner-flowet (hvor partner_materials[X] er
sandhedskilden for bestillingssidens visning).

### Fix
`GET /api/locations/{code}/containers` har nu 3-trinns resolution:
1. Med `partner_id` → strict scope = `partner_materials[partner_id]`
2. Uden `partner_id`, hvis pladsen er partner-aware (mindst én partner med
   materialer) → returnér UNIONEN af alle partneres materialer. Legacy
   `materials`-listen ignoreres helt (det er præcis hvad bestillingssiden
   viser når brugeren cykler igennem alle partnere).
3. Uden `partner_id` og ingen partner-data → fallback til legacy
   `materials` (bagudkompat for pladser der aldrig har brugt partner-flowet).

Schedule-tabben (`SchedulesTab`) i `LocationAdminPage.jsx` fetcher ved tab-
mount, så materialer er real-time-friske hver gang LA navigerer til tabben.

### Tests (5/5 + regression 16/16 = 21/21)
`tests/test_iteration31_schedule_tab_material_union.py`:
   * test_with_partner_id_returns_only_that_partner — strict scope bevaret
   * test_without_partner_id_returns_union_when_partner_aware — UNIONEN
   * test_legacy_only_location_still_works — bagudkompat
   * test_partner_aware_legacy_is_completely_ignored — KEY FIX

Regression: iter30 strict-separation (16/16) kører stadig grønt.



### Brugerklage (verbatim)
> "Når jeg skifter mellem distributionspartner, så fejler den stadigvæk.
>  den holder dem ikke helt separeret, det er somom det mikser dem nogle gange.
>  Det der sker for en (feks slette en materiale efter at vælge logistik
>  partner 1) skal ikke ske for en anden logistik partner. Jeg oplever at
>  jeg sletter en materiale for en logistik partner, og når jeg switcher
>  til den anden så sker der enten ikke noget, eller noget forkert."

### Root cause analyse (2 separate bugs)
**Bug #1 (frontend):** `App.js handleAddMaterial / handleEditMaterial /
handleDeleteMaterial` sendte IKKE `partner_id` med i deres axios-kald —
selvom resten af appen var partner-aware. Det betød at:
   * Slet i Partner A view rørte ofte legacy `materials` (gloal) i stedet
     for `partner_materials[A]`, hvilket forklarer "der sker ikke noget".
   * Tilføj havnede i legacy-listen — synligt for ALLE partnere når UI'et
     senere brugte fallback.

**Bug #2 (frontend):** `useEffect` der fetcher materialer ved partnerswitch
faldt tilbage til legacy `location.materials` når en partners liste var
TOM. Det fik materialer fra én partner (eller fra et gammelt global-stage)
til at lække ind i en anden partners view — "mixede dem nogle gange".

**Bug #3 (backend):** `PUT /api/locations/{code}/materials` (rename)
understøttede slet IKKE `partner_id` — selv hvis frontend havde sendt det
ville renamen være sket i legacy-listen.

### Fixes
**Frontend (`App.js`):**
   * `handleAddMaterial`: sender nu `body.partner_id` når en partner er valgt
   * `handleEditMaterial`: sender nu `body.partner_id` i PUT-body
   * `handleDeleteMaterial`: appender `&partner_id=...` til URL'en
   * `useEffect` for partner-switch: FJERNET legacy-fallback. Tom partner-liste
     vises som tom liste — LA skal aktivt tilføje materialer for den partner.

**Backend (`server.py`):**
   * `edit_location_material` (PUT) udvidet med strict `partner_id`-support:
     - Med partner_id: rename inden for `partner_materials[partner_id]`,
       rør IKKE andre partneres lister eller legacy.
     - Validering: 404 hvis old_name ikke findes i partner-listen.
     - Spejler renamen i partner-scopede `container_overrides`.
     - Uden partner_id: legacy-rename som før (bagudkompatibilitet).
   * Eksisterende `add` og `delete` endpoints var allerede korrekt
     implementeret (bugfixed i iter28+29).

### Tests (16/16 grøn)
`tests/test_iteration30_strict_partner_materials_separation.py`:
   * test_add_material_to_partner_a_only — KUN i A
   * test_add_material_to_partner_b_only — A urørt
   * test_add_same_name_to_both_partners_allowed — separation
   * test_add_duplicate_within_same_partner_fails — idempotency
   * test_get_returns_only_partner_a_materials — GET strict-scope
   * test_get_returns_only_partner_b_materials — GET strict-scope
   * test_get_with_legacy_materials_does_not_leak_to_partner — NO fallback
   * test_edit_material_in_partner_a_only — PUT strict-scope
   * test_edit_material_not_in_partner_returns_404 — separation
   * test_edit_same_name_in_both_partners_isolated — same-name handling
   * test_delete_material_in_partner_a_only — DELETE strict-scope
   * test_delete_does_not_affect_other_partner_with_same_name — separation
   * test_delete_not_in_partner_returns_404 — separation
   * test_delete_without_partner_id_does_not_touch_partner_lists — legacy isolated
   * test_user_reported_flow_a_delete_then_switch_to_b — brugerens KONKRETE flow

End-to-end via Playwright + API i `tests/e2e_iter30_partner_separation.py`:
   1. Add "TestMat-A" til Partner A ✓
   2. Add "TestMat-B" til Partner B ✓
   3. Verificer A=["TestMat-A"], B=["TestMat-B"] ✓
   4. Delete "TestMat-A" fra A ✓
   5. Verificer A=[], B=["TestMat-B"] — separation BEVARET ✓



### Krav: Single-sheet Excel rapport
Brugeren klagede over at Excel-eksporten var opdelt i flere faner (Pr. lokation,
Materialer, Medarbejdere, Tidsmønster). Krav: ÉT ark + best-practice styling.

### Implementering
Skiftet fra `xlsx` (SheetJS - kan ikke style i community-edition) til **`exceljs`**
(`yarn add exceljs`) som har fuld støtte for farver, borders, frozen panes,
auto-filter og conditional formatting i browseren.

Ny delt helper: `/app/frontend/src/lib/excelExport.js` — `exportReportXLSX({ data, title, subtitle, includeByLocation, filename })`.

### Indhold på det enkelte ark
1. **Brand-banner** (Title + Subtitle med periode)
2. **4 KPI-bokse** i toppen (Total bestillinger / Afventer perioden / Afventer i alt / Værksted) — store farvede tal
3. **Pr. lokation** (kun CA-rapport) — med totals-række + AutoFilter
4. **Pr. materiale** — med count, vægt, andel (%) + I alt
5. **Pr. medarbejder** — med count, andel (%) + I alt
6. **Tidsmønster** — auto-tilpasset granularitet (time/dag/uge/måned)
7. **Afventende bestillinger** (top-100) — med AutoFilter for hurtig søgning
8. **Footer** — genereringstidspunkt + periode

### Styling-features (alle nye)
- **Frozen header** (`ySplit: 6`) — banner + KPI'er forbliver synlige under scroll
- **Brand-blå banner** (#1E3A8A) med hvid tekst, 18pt bold
- **Sektions-overskrifter** med lyseblå baggrund + brand-blå tekst
- **Tabel-headers** med brand-blå baggrund + hvid bold tekst
- **Zebra-striping** (hver anden række lyse-grå) for læsbarhed
- **Totals-rækker** med lavendel-baggrund + bold
- **Borders** på alle data-celler
- **Tal-formater**: `#,##0` (heltal), `#,##0" kg"` (vægt), `0.0%` (andel)
- **AutoFilter** automatisk på by_location- og pending_orders-tabeller
- **Kolonne-bredder** sat ud fra forventet indhold (38pt for tekst-kolonner, 18pt for tal)
- **Landscape-layout** med fit-to-page-print

### Opdaterede komponenter
- `CustomerAdminPage.jsx` — `exportExcel()` bruger nu `exportReportXLSX` med `includeByLocation: true`
- `LocationAdminPage.jsx` — `exportCSV()` bruger nu `exportReportXLSX` med `includeByLocation: false`
- `SuperAdminPage.jsx` — `exportPladsExcel()` konsolideret til ét ark (Plads-rækker med indrykkede underadresser nedenunder)

### Tests
- **Node-test** (standalone): Bekræfter ExcelJS-output har korrekt antal sheets, frozen views, autoFilter og celle-værdier
- **E2E-test** (Playwright, `/app/tests/e2e_excel_export_iter30.py`): Logger ind som CA → klikker Excel-knap → fanger download → unzipper og verificerer:
  - `xl/worksheets/sheet*.xml` indeholder PRÆCIS 1 fil → ✓ ÉT ARK
  - `"frozen"` i sheet-XML → ✓ Frozen header
  - `"Kunde-rapport"` i sharedStrings → ✓ Title-banner
  - `"Bestillinger i perioden"`, `"Værkstedsbesøg"` → ✓ KPI-labels



### Krav 1 — Customer Admin Toggle Location Admin Attachment
**Backend bugfix**: `_lookup_site_by_code` returnerede ikke `partner_materials`-feltet,
hvilket fik `DELETE /api/locations/{code}/materials?partner_id=X` til at fejle med 404
selv om materialet faktisk lå i DB'en. Fix: feltet er nu inkluderet i returneringen.
13/13 grøn på `test_iteration26_multi_partner_containers.py`.

**Backend bugfix**: `org_update_user` ryddede ikke `location_code` når `location_codes=[]`
blev sendt — LA'en blev derved stadig vist som tilknyttet sin tidligere primære lokation
i `adminsForLoc` UI-filteret. Fix: når listen er tom, sættes BÅDE `assigned_plads_ids=[]`
OG `location_code=""`.

**Frontend UX**: `CustomerAdminPage.jsx` admin-picker er omskrevet fra checkbox-rækker
til fuldt klikbare button-rækker med stærk blå/hvid baggrund (bg-blue-50 = tilknyttet,
bg-white = ikke tilknyttet). Klikker man én gang → "tilknyttet"-toast. Klikker man igen
→ "frakoblet"-toast. Hver række har `data-testid="admin-toggle-{loc_id}-{admin_id}"`.

### Krav 2 — Delta Multi-Publish + 30-dages tab
**Backend**: 
- `POST /api/org/holiday-deltas/{notif_id}/import` accepterer nu enten `calendar_id` (legacy
  single) eller `calendar_ids: [id1, id2, ...]` (multi). Alle kalender-id'er valideres
  UPFRONT — hvis nogen er ugyldige (eller tilhører andet firma), aborter endpoint MED 403
  før mutation (atomic safety).
- Hver succesfuld import appender til `applied_calendar_ids: []` på notifikationen
  (via `$addToSet`), så vi senere kan vise hvor delta'et er publiceret.
- Notifikationens `status` bliver "accepted" efter første publicering, men SELVE
  notifikationen forbliver synlig i den nye 30-dages tab.
- Nyt endpoint `GET /api/org/holiday-deltas/received?days=30` returnerer alle notifikationer
  for LA'en i vinduet, beriget med `applied_calendar_ids` + `available_calendar_ids` +
  liste over LA's egne aktive kalendere — frontend bruger dette til at deaktivere "Allerede
  publiceret" rækker og skjule "Publicér igen" når alle kalendere har det.

**Frontend**:
- Ny tab "Modtagne delta'er" i `LocationAdminPage.jsx` (`data-testid="ladmin-tab-received-deltas"`).
- `ReceivedDeltasTab`-komponent viser kort med status-pille (Afventer/Publiceret/Afvist),
  publiceringskanal-chips og "Publicér igen"-knap når der er kalendere tilbage.
- `DeltaReviewModal` er omskrevet til at bruge multi-select checkbox-liste i stedet for
  enkelt-dropdown. Brugeren kan vælge flere kalendere på én gang. Import-knappens label
  reflekterer dynamisk antallet: "Indsæt i N kalendere".
- Allerede-publicerede kalendere vises i grå med "Allerede publiceret"-tag og kan ikke
  vælges igen (idempotency).

### Tests (89/89 grøn)
- `tests/test_iteration29_delta_multipublish_and_la_toggle.py` — 17 tests · 100% pass
  (CA attach/detach/last-detach-clears-location_code/reattach; delta multi-publish; 
  received endpoint efter publish; legacy single calendar_id bagudkompatibilitet;
  atomic validation; 30-dages window-filter)
- `tests/test_iteration26_multi_partner_containers.py` — 13/13 inkl. nye
  `test_partner_materials_strict_separation` + `test_partner_materials_duplicate_name_allowed_across_partners`
- Andre regression-suites: 22/22 iter18, 22/22 iter19, 11/11 iter20, 4/4 iter25



### To bugs i per-partner setup fixet
- **Dobbelt-tælling fjernet**: Når LA tilføjer container under en partner, øges count nu med præcis +1 (var +2 pga. SUM-bug). Backend bruger nu Copy-on-Write: per-partner count erstatter legacy når sat, ellers fungerer legacy som fallback.
- **Partner-switcher refresher nu altid view til "Vælg materiale"** uanset om man er mid-order eller i "Mine bestillinger". Toast bekræfter skift.
- **Override save bevarer legacy**: Når en partner redigerer en legacy-container, oprettes en NY per-partner override-række — legacy-rækken muteres ikke, så andre partnere fortsætter med at se den originale data.

### Tests
- Backend: 11/11 i `test_iteration26_multi_partner_containers.py` (incl. nye `test_copy_on_write_no_duplicate_count_after_partner_add` + `test_copy_on_write_override_does_not_mutate_legacy`)
- Frontend (iteration_28.json): 3/3 PASS via curl + Playwright på produktionsdata
- KOGE 5499 legacy state genskabt efter test (custom_container_id=123456)


## What's new in 2026-06-15 (iteration_25→27)

### Iteration 27 — Bug fixes til per-partner setup
- Partner-picker spørger nu **HVER GANG** ved 2+ partnere (sessionStorage-auto-restore fjernet).
- Partner-switcher refresher til "Vælg materiale" uanset view; nulstiller ALT bestillings-state.
- Container "Gem" virker nu igen — backend $or-filter inkluderer legacy/globale rækker (uden partner_id) sammen med per-partner rækker, og frontend sender container.partner_id med ved override.

### Iteration 26 — Per-partner container setup
- Hver lokation kan have 2+ logistik-partnere tilknyttet
- Materialer + containere er scopet til (location, partner) via `partner_id`
- Backend $or-filter: legacy data (uden partner_id) er ALTID synlig, så historisk setup bevares
- "Naviger til bestillingsside"-label på LA-side
- Backend endpoint: `GET /api/locations/{code}/partners` (offentligt)

### Iteration 25 — 3 nye features + data-restore
- "Genåbn delta"-genvej i LA-header (med live count-badge via CustomEvent-bus)
- "Copy to rows"-knap i begge kalender-editorer (Helligdage + Åbningstider)
- Customer Admin Reports på tværs af alle lokationer + per-lokation breakdown, Excel/PDF
- `argoroskildeadmin@gmail.com` genskabt; test-skrald (it15-*, it22-*, IT22-Tom-*, etc.) slettet

### Tests
- Backend: 36+ pytests (incl. 8 nye iter26 + 5 iter22 + 4 iter25)
- Frontend: iteration_27.json — 4/4 PASS


## What's new in 2026-06-15 (iteration_23+24 — Brugerkrav-runde 5)

### React DOM crash fixet (insertBefore-fejl)
- 9 duplikerede `<Toaster/>` i `App.js` + 7 i page-komponenter forårsagede `NotFoundError: insertBefore` under route-skift.
- Konsolideret til **én** global `Toaster` i `/app/frontend/src/index.js`.
- `document.querySelectorAll('section[aria-label="Notifications alt+T"]').length === 1` på alle sider.

### Tom helligdagskalender holder sig tom
- Frontend sender nu eksplicit `days: []` når brugeren vælger "Tom kalender" — backend pre-fylder IKKE fra holiday_group.
- "Kopier fra ..." virker uændret.
- "Delta publish" virker mod alle kalendre uanset hvordan de blev oprettet.

### Auto-populate på ordreside
- `Leveringsadresse`, `Åbner`, `Lukker` auto-udfyldes nu UANSET om feltet er read-only/låst.
- Adresse-resolution-kæde: `containerAddress` (låst override) → `data.resolved_delivery_address` (kalenderens fallback) → `data.selected` → `alternatives[0]` (første i biblioteket).
- Container's egne åbnings-/lukketider (hvis sat på override) bevares; ellers udfyldes fra kalenderen.

### Rapport-download virker nu
- `file-saver`-bibliotek tilføjet (iframe-sikker). Fallback til manuel `<a download>` + `window.open(blob)`.
- Begge knapper (Excel + PDF) bruger nu **identisk** `bg-slate-200/dark:bg-slate-700` styling.

### Holiday delta-modal kan lukkes
- X-knap, Escape-tast, og backdrop-klik lukker nu modallen.
- `lastCountRef` forhindrer polling i at åbne den igen — kun et NYT delta åbner pop-up igen.
- Badge nederst-højre er stadig tilgængelig.

### Tests (24 → 26)
- `tests/test_iteration22_address_and_filters.py` (7 ✓): tom kalender + bagudkompatibilitet + status_label + include_cancelled.
- Frontend e2e (iteration_24.json): **5/5 PASS**.


## What's new in 2026-06-15 (iteration_22 — Brugerkrav-runde 4)

### Bestillingssidens filtre er rebuiltet
- "Filtrér på afventende" er nu **uafhængig** af "Alle bestillinger"-mode — kan kombineres frit.
- Pending-filteret behandler `afventer + på vej` som afventende (`!completed`).
- Ny vedvarende toggle "Skjul afhentede stillinger" i hjørnet (localStorage `cf:hideCompletedOrders`).
- Standard-adfærd: `Pr. dato` viser alle statuser; `Alle bestillinger` skjuler fuldførte som standard.
- Sortering: **Afventer → På vej → Fuldført** (fuldførte altid nederst, nyeste først indenfor gruppen).
- Samme filtre + sortering virker på både `Mine bestillinger` og `Alle bestillinger på lokationen`.

### Alternativ leveringsadresse PERMANENT FJERNET
- Dropdown'en `alternative-address-select` er slettet fra Step 3 (`Bekræft og rediger`).
- Toggle "Vil du udfylde adressen selv?" + `manualAlternativeAddress` er fjernet.
- Brugeren bruger udelukkende det forudfyldte adresse-felt + "Ændre til anden adresse" hvis nødvendigt.
- Backend bevarer bagudkompatibilitet: hvis et gammelt klient-API kalder med `alternative_delivery_address_id` ignoreres feltet uden 500.

### Rapport-download repareret
- Excel og PDF (`ReportsSection` i `LocationAdminPage.jsx`) preloader nu xlsx/jspdf/jspdf-autotable ved mount via `useEffect + useRef`, så brugeraktivering bevares når `click()` udløses.
- Nyt `triggerDownload` hjælper-funktion med fallback til `window.open(blobUrl)` hvis browseren blokerer download i preview-iframe.
- Konsol-logger `[exportCSV]` / `[exportPDF]` ved fejl, toast viser præcis fejl.

### Tests
- `tests/test_iteration22_address_and_filters.py` (5 ✓ — backend tolerance + status_label + include_cancelled).
- `tests/test_iteration21_filter_modes.py` (6 ✓ — opdateret `container_id_resolved`-assertion).
- Frontend e2e (testing_agent iteration_22): **3/3 fixes PASS**, native Playwright download events fanget for Excel + PDF.



### Bugfixes
- **Slet-knappen på helligdags-delta virker nu** — også for publicerede delta'er. Backend rydder samtidigt alle relaterede notifikationer hos LA'erne.
- **Excel/PDF download fra Rapportering** virker nu: bruger `Blob` + anchor-download i stedet for `XLSX.writeFile`/`doc.save` der svigtede i nogle browser-sandboxes.

### Super Admin
- **"Helligdagsgrupper" + "Helligdags-delta" slået sammen til ÉN tab** "Administrer helligdagsinformation". Begge sektioner vises nu side om side på ét sted.
- **Publicering med kunde-vælger**: SA klikker Send-ikon → modal viser liste af aktive kunder med søgning + multiselect, ELLER "Publicér til ALLE aktive kunder"-checkbox. Backend POST `/api/superadmin/holiday-deltas/{id}/publish` accepterer nu `{"company_ids": [...]}`. LA'er på fravalgte kunder modtager ikke notifikationen.

### Location Admin
- **"Rapport og statistik" omdøbt → "Rapportering"** (tab-label + heading).
- **Helligdagskalendere er ikke længere årsbaserede**: år-feltet fjernet fra opret-formularen + år-badgen fjernet fra listen. SA-delta publicering bruger stadig delta-baseret merge — eksisterende dage overskrives ikke, kun de operationer LA accepterer indsættes.
- **Delta-popup terminologi** opdateret: "Importér" → "Indsæt i kalender", "Afvis" → "Afvis ændringer", "Senere" → "Beslut senere".
- **Rapportering — nyt format**: KPI-tiles + bestillingstrend-bar + ny **"Materiale detaljer"-tabel** (rang/materiale/antal ture/total vægt/horisontal fordeling-bar) + **"Materiale fordeling"-pie chart** med labels og procentvis fordeling + "Top medarbejdere"-tabel (med horisontal bar). "Workshops" → "Værksteder" overalt.

### Bestillingsside (Ordreflow)
- **Kapacitetsmål kan vælges på "Rediger container"**: ny dropdown i `ContainerEditModal` der trækker fra `/api/org/capacity-measures`. Tom = intet kapacitetsmål.
- **Kapacitetsmål auto-populates** ind på "Bekræft og rediger" som purple chip, i ordreopsummeringen og i "Bestilling modtaget"-success popup. Backend snapshot'er label + volumen på selve `container_orders`-dokumentet, så driveren senere får det direkte (kommer i en fremtidig batch).
- **"VIL DU UDFYLDE ADRESSEN SELV?" feltet fjernet** helt fra Bekræft og rediger-trinnet.
- **"Container"-feltet fjernet** fra Bekræft og rediger (kun "Container-nummer" tilbage).
- **Bestilling modtaget-popup** viser nu opgavetype-label + container-nummer + kapacitetsmål. Adresse skjult ved "Byt container". Værksted-flows ("Til værksted" / "Afhent fra værksted") viser i stedet værksted-navn + værksted-adresse + værksted-telefon.

### Rediger container
- **"Leveringsadresse"-feltet fjernet** helt fra "Rediger container"-modalen. Backend-validering opdateret: kun container-nummer er obligatorisk på container-definitionen; leveringsadressen vælges først på selve bestillingen.

### Tests
- `/app/backend/tests/test_iteration20_user_requirements.py` — 11 tests · 100% pass (delete published delta + cascade notifications, publish scoped til specifik kunde, publish til alle, ContainerOverride uden adresse-krav, capacity-snapshot end-to-end på orders).
- Backend regression: 55/55 grønne på tværs af iteration 18, 19, 20 (individuelle kørsler).


## What's new in 2026-06-14 (iteration_19 — BATCH 2 micro-batches A+B+C færdig)

### Backend
- **Værksteder** (`/api/org/workshops`): CRUD library scopet til ét kundefirma. POST/PUT/DELETE er CA-only; GET er for alle org-roller. Felter: `name` (obligatorisk), `address` (obligatorisk), `phone`, `comment`.
- **Lokationsgrupper** (`/api/org/location-groups`): CRUD library {id, name, locations_count}. Tilknyt en valgfri gruppe pr. plads via nyt felt `location_group_id` på `OrgLocationCreate/Update`. Når gruppe slettes frakobles plads automatisk.
- **Customer-order workshop-snapshot**: `StructuredOrderCreate` udvidet med `workshop_id`, `workshop_name`, `workshop_address`, `workshop_phone`, `workshop_override`. Submit-validering tilpasset: for `tour_type ∈ {flyt, vaerksted, afhent_vaerksted}` springes leveringsadresse-kravet over; for værksted-flows kræves nu workshop_name + workshop_address.
- **Customer-order edit/delete + audit log**: 
  - `PUT /api/customer-orders/{id}` (whitelisted felter, sync'er tour) skriver entries i `customer_orders_history`. 
  - `DELETE /api/customer-orders/{id}` (hard delete + tour-cascade) skriver delete-entry før sletning så audit overlever.
  - `GET /api/customer-orders/{id}/history` returnerer kronologisk audit.
  - Cross-tenant: 403 hvis order tilhører andet firma.
  - Block: ordrer med `status_label ∈ {paa_vej, fuldfoert}` kan ikke længere redigeres/slettes.

### Frontend – Customer Admin (CustomerAdminPage)
- **Ny tab: Lokationsgrupper** (`cadmin-tab-groups`) — opret/rediger/slet grupper {id, name} med `locations_count`.
- **Ny tab: Værksteder** (`cadmin-tab-workshops`) — opret/rediger/slet værksteder med navn/adresse/telefon/kommentar.
- **Location form**: ny `location_group_id` dropdown i både create + edit modal. Liste viser purple gruppe-chip på lokationsrækkerne.

### Frontend – Bestillingsflow (CustomerOrderPage)
- **Opgavetype flyttet til Step 3** (Bekræft og rediger) — placeret lige under Materiale med 4 tiles: Afhentning · Byt container (id=flyt, omdøbt fra "Flyt container") · Til værksted · Afhent fra værksted (ny).
- **Conditional UI**:
  - Når `tour_type ∈ {flyt, vaerksted, afhent_vaerksted}` skjules hele leveringsadresse-blokken (adresse + åbningstider + "Vil du udfylde adressen selv?").
  - Når `tour_type ∈ {vaerksted, afhent_vaerksted}` vises 4 felter: Værksted-dropdown (fra CA-biblioteket) + auto-fyldte Navn/Adresse/Telefon.
  - `Overskriv`-knap toggler workshop-felterne til fri-tekst (amber border) og deaktiverer dropdown.
- Submit-payload udvidet med alle workshop-felter, valideringsklar.
- Order-summary i bunden viser nu Værksted + workshop-adresse + telefon når relevant.

### Frontend – Mine bestillinger
- Hver pending ordre har nu **3 handlingsknapper**: Historik / Redigér / Slet.
- **OrderEditModal**: redigér prioritet (HASTER/NORMAL/SENERE), dato, opgavetype og kommentar. Toast på "no_change".
- **OrderDeleteConfirmModal**: soft-confirm før hard-delete med tour-cascade.
- **OrderAuditModal**: kronologisk diff pr. felt (line-through før-værdi → ny værdi), bruger-navn og tidsstempel.
- Når ordre er taget (claimed_by/on_way/completed) skjules Redigér + Slet — kun Historik vises.

### Tests
- `/app/backend/tests/test_iteration19_batch2.py` — 22 tests · 100% pass (workshops CRUD + LA read-only + adresse-validering; location_groups CRUD + duplicate 409 + locations_count; location_group_id attach/detach; workshop-snapshot på orders; edit/delete + audit + cross-tenant 403).
- Total backend regression: 44/44 grønne (Batch 1 + Batch 2).
- Iteration_19 frontend e2e: CA-side 100% (tabs, groups, workshops). Order-side UI er IKKE manuelt e2e-testet i denne kørsel pga. tom seed-plads (ingen container_instances) — endpoints er fuldt dækket af pytest.

### Backlog herfra (P1/P2)
- **Logistik-partner switcher** ved login: når en bruger er linket til flere logistikpartnere, vis valg-skærm + scope bestillingssiden til den valgte partner.
- **Visual pickup-flag** på containere (bestillingsside efter materialvalg + Mine bestillinger + LA dashboard).
- **Vis Kapacitetsmål** på containere overalt (badge ved container-tile).
- Auto-arkivér inaktive brugere efter 30 dage.
- Kunde-ID på faktura/rapport PDF'er.
- Auto-seed container_instances ved oprettelse af ny plads (UX-gap som testing-agent påpegede).


## What's new in 2026-06-14 (iteration_18 — BATCH 1 ferdig)

### Super Admin
- **Kundeoverblik**: `/api/superadmin/companies` returnerer nu `locations_count`, `partners_count`, og `active_users_incl_partners` pr. kunde. Kortet i UI viser de tre tællere som et grid.
- **Helligdags-delta** (ny tab `data-testid=tab-deltas`): SA kan oprette kladder med ADD/MODIFY/DELETE-operationer pr. helligdag, og publicere dem. Publicering oprettes som en notifikation pr. LA. Genpublicering skipper LAer der allerede har handlet.
  - `POST/GET/PUT/DELETE /api/superadmin/holiday-deltas` (kun draft kan ændres/slettes).
  - `POST /api/superadmin/holiday-deltas/{id}/publish` (fan-out til alle LAer på tværs af kunder).

### Location Admin
- **Persistent delta-popup** (`DeltaNotificationsPopup`): Vises automatisk ved sidereload når der findes ubehandlede helligdags-delta'er. Kan kun lukkes ved Importér eller Afvis (X minimerer til badge).
  - `GET /api/org/holiday-deltas/pending`
  - `POST /api/org/holiday-deltas/{id}/import` (LA vælger kalender + kan toggle individuelle ops fra eller redigere ADD/MODIFY-feltværdier).
  - `POST /api/org/holiday-deltas/{id}/reject`
- **Leveringsadresser er nu et standalone bibliotek** (`label`, `street`, `postcode`, `city`). Ingen materiale-mapping længere — adresser tilknyttes i stedet til en ugedag (obligatorisk) eller en helligdag (valgfri).
- **Helligdagskalender**: pr. dag dropdown `delivery_address_id` (valgfri). Hvis tom falder bestillingen tilbage til ugedagens adresse.
- **Åbnings-/lukketider** (HoursCalendarEditor): `delivery_address_id` er nu **obligatorisk** pr. åben ugedag (lukkede dage skippes). Frontend valideringen viser hvilke ugedage mangler.
- **Kapacitetsmål-bibliotek** (`/api/org/capacity-measures`): {label, volume_m3} CRUD pr. lokation. Vises i en ny tab.
- **Rapport og statistik-tab**: `/api/org/reports/orders` med period-filtre (day/week/month/3months/6months/year/custom), grupperinger (materiale, medarbejder, tidsmønster), 4 KPI-tiles, 4 Recharts-grafer, og PDF/Excel-eksport via `jsPDF` + `xlsx`.

### Bestillings-resolver
- `POST /api/customer-orders/resolve-schedule` returnerer nu `delivery_address` baseret på fallback-kæden: helligdagsdag → ugedag → null. Lukket helligdag returnerer 423.

### Tests
- `/app/backend/tests/test_iteration18_batch1.py` — 22 tests · 100% pass (delivery_address schema, kapacitet, delta CRUD/publish/import/reject, kunde-overblik counts, fallback-resolver, rapport-endpoint).
- Iteration_18 frontend e2e: 100% — alle 13 listede Batch 1 features verificeret på live preview.

### What's next (BATCH 2 — kommer)
- Værksteder (workshops) pr. kunde.
- Lokationsgrupper + flere logistikpartnere pr. lokation.
- Bestillingsflow: visual pickup-flag, kapacitetsmål overalt, "Byt"/"Afhent fra værksted" opgavetyper, simplificeret leveringsadresse-UI.
- "Mine bestillinger": "I dag"-default, "Alle"-filter, advarsler, edit + soft-delete.



### Super Admin · Helligdagsgrupper
- `year` field (separate int + included in display label). `active` flag with toggle endpoint. `holiday_groups[]` list returns `assigned_count` per group.
- POST `/superadmin/holiday-groups/{id}/copy` clones name + holidays verbatim to a target year.
- POST `/superadmin/holiday-groups/{id}/toggle-active` for soft-delete.
- DELETE `/superadmin/holiday-groups/{id}` returns 409 if any company references it (with count in the detail).
- UI: year input, Copy modal, Pause/Activate toggle, Slet button disabled when assigned (with count tooltip), inactive badge + greyed row.

### Location Admin · Helligdagskalendere
- `is_active` + `year` fields. List returns `assigned_count` (rows in `material_calendars` referencing the cal).
- New POST `/org/holiday-calendars/copy-from-group` — creates LA cal pre-filled from a SA group.
- New GET `/org/holiday-groups` — read-only list of ACTIVE SA groups, available to LA/CA (gating so the SA endpoint stays SA-only).
- toggle-active + safer delete (409 when referenced). Only active calendars appear in material assignment dropdowns.
- UI: new-calendar form has Year input + Source select (Blank | Copy SA group | Copy own cal). Per-cal Pause/Trash actions + inactive badge.

### Location Admin · Åbningstidskalendere
- `is_active` flag + new toggle-active endpoint. New POST `/org/hours-calendars/{id}/copy`. Safer delete (409 when assigned).
- UI: Copy button + Pause toggle + assignment-aware delete on each card. Inactive cal hidden from material dropdowns.

### Delivery Addresses cleanup
- Removed per-address `holiday_calendar_id` + `hours_calendar_id` (schema migration via `$unset`).
- Modal no longer shows the override dropdowns. Primary-toggle now shows a confirmation dialog when "stealing" the primary slot from another address.

### Materials soft-delete
- New `inactive_materials: [str]` column on `plads`/`locations` doc.
- POST `/locations/{code}/materials/toggle-active` for soft delete; DELETE blocked (409) when orders/overrides/material_calendars reference the material.
- New GET `/locations/{code}/materials/active` returns only the active list (consumed by the public order page).

### Bestillinger filter (LA)
- Client-side filters on `OrdersTab`: year, month, date basis (afhentning vs bestilling), material, container, employee, free-text search. Active-filter badge + "Nulstil"-button.

### Medarbejdere tab
- Permanent-delete button removed from per-row actions. The Slet-permanent tab remains the GDPR-style purge path.

### Order page (public QR kiosk)
- NEW `manual_alternative_address` (fri tekst). Radio `Vil du udfylde adressen selv?` next to the field — when toggled ON, the free-text + ALL read-only fields (address, open/close hours) become editable. Order can proceed even on CLOSED dates when the manual field is filled. Submit payload now carries both `delivery_address_id`, `alternative_delivery_address_id`, and `manual_alternative_address` for full audit trail.
- New path-based routing `/order/<code>` and `/bestilling/<code>` — QR codes can deep-link straight into the order flow (previously only hash-routing worked).

### Tests
- New `/app/backend/tests/test_iteration17_year_active_softdelete.py` — 22 tests covering all new endpoints + soft-delete invariants + LA→SA group visibility.
- Iteration_14 + 16 updated to match new "block on references" delete semantics.
- Total backend pytest: **66/66 green** across iter 14, 15, 16, 17.
- Testing agent iteration_16 + iteration_17 reports: **100% pass** (frontend e2e on all flows).


### Leveringsadresser (Delivery Addresses) — Location Admin
- New collection `delivery_addresses` per (company_id, location_code) with
  fields: `id, label, street, postcode, city, materials[], primary_for[],
  holiday_calendar_id?, hours_calendar_id?, created_at, updated_at`.
- "One primary per material" invariant maintained server-side: setting one
  address primary for material X atomically unsets X on every other address
  at the same plads (via `$pull`).
- CRUD endpoints under `/api/org/delivery-addresses` (list, POST, PUT,
  DELETE) + `/set-primary` atomic action.
- Resolution endpoint `GET /api/delivery-addresses/resolve` (PUBLIC, used
  by QR kiosk + order page) returns `{primary, alternatives, selected,
  is_closed, is_holiday, holiday_name, open_from, open_to, source}`.
  Priority: per-address calendars > material_calendars; holiday entry
  on the date trumps weekday schedule.
- LocationAdminPage: new tab "Leveringsadresser" between "Åbnings- og
  lukketidspunkter" and "Logistik-partnere" with CRUD modal,
  primary-toggle pills, and materialedækning matrix showing which
  materials lack a primary.

### Order flow integration (QR kiosk + order user)
- Step 3 (`Bekræft og rediger`): delivery address PRE-FILLED from primary
  for the chosen container's material; READ-ONLY by default with a small
  "Ændre til anden adresse" button that toggles editability.
- Auto-derive `open_from` / `open_to` from resolve endpoint; re-evaluates
  on material change + date change.
- When `is_closed=true` → red banner "LUKKET på den valgte dato" shown,
  "Vælg prioritet" button disabled, alternative-address dropdown appears
  listing other addresses linked to the same material.
- Order submit now persists `delivery_address_id` (primary) +
  `alternative_delivery_address_id` (when used) + `original_customer_address`
  (the primary's address line, captured at submit time for audit/history).
- Container-level override `locked_address` still takes precedence — when
  true, the "Ændre til anden adresse" toggle is hidden / the field stays
  permanently read-only (driver / location admin policy).

### Tests
- `/app/backend/tests/test_iteration16_delivery_addresses.py` — 19 tests
  covering CRUD, primary invariant, cross-tenant guards, resolve endpoint
  (no calendar / weekday / holiday / per-address override), and order
  submit persistence.
- Total backend suite: 45/45 green (iteration_14 + 15 + 16).
- Frontend e2e via testing agent iteration 15: CRUD + primary toggling +
  materialedækning + Step-3 pre-fill all verified.


### Bugfix: `PUT /api/superadmin/companies/{id}` accepts `holiday_group_id: null`
- Before: the handler used `update = {k:v for k,v in raw.items() if v is not None}`
  which silently dropped any field sent as `null`. Result: the frontend's
  "Ingen gruppe" option could not clear a customer's holiday-group assignment.
- Fix (server.py `sa_update_company`, ~L5404):
  1. Switch payload extraction to `body.model_dump(exclude_unset=True)` so the
     handler can distinguish "field not provided" from "field provided as null".
  2. Allow-list `holiday_group_id` in a `nullable_fields` set so explicit
     `null` makes it through to MongoDB `$set` (clearing the assignment).
  3. All other fields keep their existing "None means no-op" semantics — no
     behavioural regression for other endpoints / consumers.
- Regression test: `/app/backend/tests/test_iteration15_holiday_group_null_clear.py`
  (4 tests — set, clear, partial-update-preserves, set→clear→set round-trip).
- Iteration_14 suite (22 tests) re-run after the fix → all green.


### Container visibility filter
- Containers that are missing required fields (custom_address OR
  custom_container_id) are now hidden from non-admin callers on
  `GET /api/locations/{code}/containers`. Anonymous QR customers and
  order-role users only see fully-configured containers.
- Each returned container carries a new `complete: bool` flag.
- The endpoint now reads the `Authorization` header via FastAPI
  `Header(alias="Authorization")` and uses `_can_see_incomplete_containers`
  to decide visibility — super_admin / matching customer_admin /
  matching location_admin all get the full list (incl. incomplete).

### Default container count = 0
- `_container_count_for` default changed from 6 → 0. New pladser start
  with zero containers per material and the admin adds them one at a
  time via "+ Tilføj container".
- `_container_count_for` and `container_overrides` queries inside the
  containers endpoint now use `_raw_db` so the anonymous QR flow works
  again (the previous version was returning `[]` for unauthenticated
  callers because the tenant filter mismatched).

### "Tilføj container" — empty defaults + auto-locks
- ContainerEditModal on a fresh slot (`has_override === false`):
  * address: ""           (was: plads default address)
  * container_id: ""
  * locked_address: TRUE  (default)
  * locked_container_id: TRUE (default)
  * locked_hours: FALSE   (default)
- Admin can flip any of the 3 locks via the modal before saving.

### Material delete bug fix
- `handleDeleteMaterial` no longer references the undefined
  `showConfirm` / `hideConfirm` globals. It now opens an in-app
  `SoftConfirmModal` driven by `confirmDeleteMaterialName` state.

### Location Admin Bestillinger — Container-nummer column
- `get_orders_by_location` now does a bulk lookup of container
  overrides and exposes `container_id_resolved` on every order
  (= per-order override if set, else saved default, else "").
- LocationAdminPage OrdersTab renders a "Container-nummer" column
  showing the resolved id in mono-spaced text. Custom (tilpasset)
  orders show their per-order id.

### Testing
- 34/34 backend tests passing on iteration_13 (11 new) + iteration_12
  assertions updated to use `before+1` rather than the now-incorrect
  hardcoded 7/8.


## What's new in 2026-06-12 (this session)

### SuperAdmin: separate logistics-partner library
- Companies created via the "Tilføj logistik partner" tab now carry
  `from_library=True` and are hidden from the "Kunder & Logistik" tab.
- Endpoint `GET /api/superadmin/companies` excludes library entries by
  default. Pass `?include_library=true` for the library panel only.
- Customer admins still see ALL logistics companies (incl. library) via
  `GET /api/org/logistics-companies`, so they can link library partners.

### Backend role enforcement (option b — server-side)
- New `_require_admin_for_location(code, payload)` helper that authorises
  the caller as `super_admin`, `customer_admin` (same company), or
  `location_admin` (managing that plads).
- All container/material write endpoints now invoke this guard:
  * `POST /api/locations/{code}/containers/add`
  * `PUT  /api/locations/{code}/containers/override`
  * `DELETE /api/locations/{code}/containers/slot?material=&container_label=`
  * `POST /api/locations/{code}/materials`
  * `PUT  /api/locations/{code}/materials`
  * `DELETE /api/locations/{code}/materials`
- Order-role users get 403 on all of the above.

### Container "Lås container-nummer"
- 3rd lock flag added to `ContainerOverride.locked_container_id`.
- When True, the order flow ignores any per-order `custom_container_id`
  the user submits (defense-in-depth, frontend also disables the input).

### Container override required fields
- `PUT /api/locations/{code}/containers/override` now rejects (400) if the
  merged `custom_address` or `custom_container_id` is empty.

### Order page (CustomerOrderPage) UX changes
- New "Tilføj tilpasset bestilling" button on step 2 (visible to all
  roles). Sets `isCustomRequest=true` and skips straight to step 3 with
  every field blank + editable + required.
- "+ Tilføj container" and per-container Rediger/Slet icons are hidden
  for non-admins (visible only when adminMode=true).
- Both admin buttons sit side-by-side on step 2.
- Soft-confirm modal (`SoftConfirmModal`) now gates the "+ Tilføj
  container" and "Slet container" actions.
- Step 1 "Vælg materiale": material edit/delete buttons + "Tilføj nyt
  materiale" form are gated on adminMode (employees can only choose).
- Step 3 "Container-Nummer" field is now READ-ONLY pre-filled with the
  default unless the user picked the custom flow (then editable+required).
- Removed the "Grundoplysninger gemmes ikke" info-box, the
  "Lader du feltet tomt..." hint, and the "Tilbage til start" success-
  screen button.
- The "Låst" badge on container cards (step 2) is removed.

### Test surface
- 23/23 backend pytest tests passing on iteration_12. Covers role-
  enforcement matrix (super/customer/location admin/order), library
  filter logic, lock-id round-trip, submit-time defense.



### Global data wipe
- All non-super_admin data wiped per owner request. Only
  `doganmiketuran@gmail.com` (super_admin) remains. Auto-seed of
  `superadmin@platform.com` + legacy demo pladser/drivers has been
  removed from backend startup AND the frontend `/api/seed` auto-call.
- Wipe script: `/app/scripts/wipe_data.py`. Run any time to reset.

### Location admin multi-location support
- A single `location_admin` can now manage MANY pladser at once via
  `assigned_plads_ids: [code, code, ...]`. The customer_admin grants
  access via checkboxes (Tilføj location admin tab).
- Backend `org_create_user`, `org_update_user`, `org_list_users`,
  `org_delete_user` and `org_resend_invitation` updated to use the union
  of `caller.location_code + assigned_plads_ids` for ownership checks.
- LocationAdminPage UI groups employees by location, shows a
  location-dropdown when creating employees, supports a multi-location
  filter on the employee + order tables.

### Direct "Slet medarbejder fuldt" (bug fix)
- `DELETE /api/org/users/{id}` no longer requires the user to be
  inactivated first. The frontend EmployeesTab has a red trash icon per
  row that opens a custom `ConfirmDeleteModal` (no more window.confirm
  popup-blocker issues).

### "Gå til bestillingsside" button (location admin)
- New header button. When the admin manages more than one plads, a
  PickLocationModal is shown. Selection is persisted in
  sessionStorage `ladmin_order_loc` then App.js re-renders the
  CustomerOrderPage with `adminMode=true`.

### Order page (CustomerOrderPage)
- "+" button on step 2 calls the new endpoint
  `POST /api/locations/{code}/containers/add` which increments the
  `container_counts` collection (no more hardcoded 6).
- Per-container "Rediger" pencil button opens a `ContainerEditModal`
  for base-definition editing — address, container number, opening
  hours, and (for admin only) lock checkboxes for address/hours.
- Container-id and address inputs on step 3 NO LONGER persist to
  `container_overrides`. The order-time container number lives only on
  `container_orders.container_id_override` and on the resulting tour's
  `container` field. Defaults stay intact.
- Step 3 honours `locked_address` / `locked_hours` — those inputs
  become read-only when locked by the admin.

### Super Admin UI cleanup
- Tab renamed: `Kunde-administratorer` → `Kunde Administration`.
- The "Aktive medarbejdere pr. kunde" license-overview panel ONLY
  appears under the new "Kunde Administration" tab now (was on every
  non-logistics tab).

### Backend model + endpoint additions
- `ContainerOverride.open_from`, `open_to`, `locked_address`, `locked_hours`
- `container_counts` (new collection, persists per-material count)
- New endpoint `POST /api/locations/{code}/containers/add`
- `ContainerOrder.container_id_override` (per-order container number)

### Frontend test ID additions
- `tab-admins`, `license-overview-panel`, `add-location-btn`,
  `edit-location-{id}`, `assign-admin-{id}`, `admin-toggle-{loc}-{adm}`,
  `loc-mode-existing`, `loc-mode-new`, `loc-code-{code}`,
  `add-employee-btn`, `emp-location-select`, `delete-employee-{id}`,
  `confirm-delete-modal`, `confirm-delete-btn`,
  `ladmin-go-to-order-btn` (+ mobile variant),
  `add-container-btn`, `container-edit-btn-{i}`,
  `container-edit-modal`, `cont-edit-id`, `cont-edit-address`,
  `cont-edit-lock-addr`, `cont-edit-lock-hrs`, `cont-edit-save`


- Backend (`/app/backend/`)
  - `auth.py`: JWT, bcrypt, pydantic models, FastAPI dependencies, contextvars
  - `server.py` (extended):
    - `TenantAwareDB` / `TenantAwareCollection` wrappers
    - `TenantContextMiddleware`
    - Migration on startup (default company, super-admin seed, backfill `company_id="default"`)
    - `/api/auth/*` (login, me, logout, change-password)
    - `/api/superadmin/*` (companies + users CRUD, role + active toggle)
    - `/api/genbrug/*` (orders CRUD, scoped by company)
- Frontend (`/app/frontend/src/`)
  - `auth/AuthContext.jsx` + `auth/api.js` (axios bearer interceptor)
  - `pages/LoginPage.jsx` (unified single login page)
  - `pages/SuperAdminPage.jsx` (companies + users management)
  - `pages/GenbrugPladsPage.jsx` (recycling orders dashboard with status flow + search)
  - `App.js` minimally extended: role-based routing injected at the top of `App()`
    - `super_admin` → SuperAdminPage
    - `genbrug_plads` → GenbrugPladsPage
    - `logistics_admin` → existing AdminPage (auto entered)
    - `driver` → existing driver flow with auto-filled name (only asks for vehicle)
    - `order` → existing customer-order flow

## Test results
- 32/32 backend pytest tests pass (auth, super-admin, tenant isolation, genbrug, legacy)
- Login UI verified via screenshot
- Super Admin panel (companies + users tabs) verified via screenshot

## Prioritized backlog (next phases)
### P1 (production hardening)
- Brute-force protection on `/api/auth/login` (lockout after 5 failed attempts)
- Refresh-token rotation; shorten access token to 15 min
- Stricter password policy (≥ 8 chars, complexity)
- HttpOnly cookie option for JWT instead of (or in addition to) localStorage

### P2 (UX polish / features)
- Edit-company UI flow uses same modal (currently works, could add slug regen)
- Genbrug Plads: image upload, weight tracking, statistics dashboard
- Super-admin: bulk user invite via CSV
- Audit log of cross-tenant actions

### P3 (architectural)
- Split `server.py` (~5150 lines) into routers (auth_router.py, drivers.py, tours.py, ...)
- Explicit wrapping of `aggregate` / `find_one_and_*` on `TenantAwareCollection`
- Per-collection migration script for adding indexes on `company_id`

## Updates (2026-02-18)

### Cross-Company READ Merge (`Company.serves_company_ids`) — NEW
Drivers / order-users / genbrug-users of a "serving" company now see
**merged data** (tours, pladser, locations, container orders, ...) across
their own company AND every company in their company's
`serves_company_ids` list.

Use case: FORSYNING HELSINGØR drives for Vestforbrænding. Super Admin
checks "Vestforbrænding" inside the FORSYNING company-edit modal under
"Udfører ture for (klient-firmaer)". FORSYNING's drivers now see both
companies' tours and pladser in one merged list — no manual switcher
needed.

* **Model**: `Company.serves_company_ids: List[str]` (auth.py).
* **Backend**:
  - New `current_extra_visible_company_ids` ContextVar.
  - `TenantAwareCollection._inject_filter` uses
    `{"company_id": {"$in": [primary, *extras]}}` whenever the extras
    list is non-empty. Inserts still go to the single primary cid.
  - `TenantContextMiddleware` populates the extras only for non-admin
    roles (driver / order / genbrug_plads); logistics_admin /
    super_admin keep their existing per-request switcher behaviour.
  - `PUT /api/superadmin/companies/{id}` validates IDs, strips
    self-loops, and accepts `[]` to clear.
  - `GET /api/superadmin/companies` now defaults
    `serves_company_ids: []` on legacy docs missing the field.
* **Frontend**: SuperAdminPage CompaniesPanel edit modal now renders an
  "Udfører ture for (klient-firmaer)" checkbox list of all OTHER
  companies. Visible only when editing an existing company.

### Tests
- `backend/tests/test_serves_company_merge.py` (9 pass)
- 62/62 backend regression green (multi-tenant + suspension +
  logistics-switcher + serves-merge), 1 unrelated skip.


A `logistics_admin` user can now manage tours / pladser / drivers / container
orders for **multiple companies** at once, while strictly preserving tenant
isolation for every other role.

* **Model**: new `managed_company_ids: List[str]` field on `User` (auth.py).
  Empty for every role except `logistics_admin`.
* **Backend**:
  - `create_access_token` embeds `managed_company_ids` in the JWT.
  - `TenantContextMiddleware` honors an optional `X-Acting-Company-Id`
    request header. For `logistics_admin`: the value must be the user's own
    company OR be in `managed_company_ids` (JWT or fresh DB lookup), else
    **403 'Du har ikke adgang til denne virksomhed'**. For `super_admin`:
    the header may point to any company. For any other role: header is
    ignored (driver/order/genbrug cannot escalate).
  - New `GET /api/auth/managed-companies` returns the list of companies the
    current user may switch to (own + managed). Reads fresh from DB so a
    Super Admin re-assignment takes effect on next page reload — no
    re-login required.
  - `POST/PUT /api/superadmin/users` accept `managed_company_ids`.
    Role-changes that move a user *away* from logistics_admin now
    automatically clear stale entries (defense-in-depth).
* **Frontend**:
  - `AuthContext` tracks `actingCompanyId`, persists it in localStorage
    (`containerflow_acting_company_id`), and sets/unsets the
    `X-Acting-Company-Id` axios default header.
  - `AdminPage` header shows a company switcher dropdown (Building2 icon)
    when the admin manages more than one company. Selecting another company
    instantly refetches pladser, tours, daily overview, statistics,
    container orders, etc — without a page reload.
  - `SuperAdminPage` user form: when role = logistics_admin, a multi-select
    checkbox list "Administrerer også (klient-firmaer)" lets the Super
    Admin assign client companies.

### Tests
- `backend/tests/test_logistics_admin_company_switch.py` (14 pass + 1 skip)



### Production-ready features (this iteration)
- **Company subscription / suspension system** — Super Admin can suspend or
  reactivate any non-default company via a Power/PowerOff toggle button on the
  company card in SuperAdminPage. When suspended:
  - `_is_company_active` (server.py L4013) returns False (30s in-memory cache,
    invalidated on PUT `/api/superadmin/companies/{id}`)
  - `TenantContextMiddleware` blocks every non-super-admin request to that
    company with HTTP 403 + Danish error message
  - `/api/auth/login` returns 403 with the same error so suspended users get
    a friendly message in the LoginPage error box
  - Super Admin bypasses the check entirely
  - The `default` company is hardcoded active AND backend now rejects
    `PUT /api/superadmin/companies/default {active:false}` with 400
    (defense-in-depth)
- **Nginx + HTTPS configs** — `/app/deploy/nginx/containerflow.conf` (HTTP) and
  `containerflow-ssl.conf` (HTTPS w/ certbot), `install_vps.sh` VPS bootstrap
  script.
- **Automatic MongoDB backups** — `/app/scripts/backup_mongo.sh`,
  `restore_mongo.sh`, `setup_backup_cron.sh` (daily 03:00 + 30d local rotation).
- **Google Drive backup destination** (2026-02-18) — daily cron uploads each
  archive to a service-account-shared Drive folder organized by date
  (`ContainerFlow-Backups/YYYY-MM-DD/<db>-HHMMSS.archive.gz`), prunes
  Drive copies older than 30 days, and the restore script accepts
  `drive:latest`, `drive:YYYY-MM-DD`, or `drive:id:<id>` to pull a backup
  directly from Drive.
  - Modules: `gdrive_uploader.py` (upload/list/prune), `gdrive_download.py`
    (latest/by-date/by-id), `requirements.txt`, `.env.example`, `README.md`.
  - Auth: Google Service Account JSON at `/app/secrets/google_drive_sa.json`
    (path overridable via `GOOGLE_DRIVE_SA_JSON_PATH`).
  - Config lives in `/app/scripts/.env`; Drive upload is **non-fatal** —
    if it fails, the local copy is still kept and the next cron run retries.
  - Local copy is **always** kept regardless of Drive status
    (`GDRIVE_UPLOAD_ENABLED=0` skips Drive entirely).

### Tests
- `backend/tests/test_company_suspension.py` (7/7 pass)
- `backend/tests/test_multitenant_auth.py` (32/32 pass)
- `backend/tests/test_hq_site_and_plads_merge.py` (14/14 pass) — Genbrug HQ/Site separation + Plads Merge

## What's been implemented (2026-02-21) — Tasks (a), (b), (c)
- **(a) Genbrug HQ vs Site separation** (P0)
  - Added `is_hq_admin: bool` and `assigned_plads_ids: List[str]` to User model
    (`auth.py`), returned in `/api/auth/login` and `/api/auth/me`.
  - `/api/genbrug/plads-rapport` now filters tours by the user's assigned plads
    names when caller is a `genbrug_plads` site user (`is_hq_admin=false`).
    Site user with empty `assigned_plads_ids` sees `[]`. HQ admin is unfiltered.
  - SuperAdminPage user form (`/app/frontend/src/pages/SuperAdminPage.jsx`):
    when role = `genbrug_plads`, a new "HQ Administrator" checkbox + a
    multi-select of pladser scoped to the user's company are shown.
  - `GenbrugPladsPage.jsx`: site users see an amber "Site-bruger visning" banner;
    HQ admins see a "HQ" tag next to the company name and a new "Priser" button
    that routes to the existing `PrijsPage` (with a back arrow).
  - Data hygiene in `sa_update_user`: clears `is_hq_admin` / `assigned_plads_ids`
    when role changes away from genbrug_plads; rejects setting these fields on
    non-genbrug users.

- **(b) Plads Merge (Slå sammen)** (P1)
  - New endpoint `POST /api/superadmin/plads/merge` with body
    `{source_id, target_id}` returning `{success, moved:{tours, container_orders,
    genbrug_orders, tour_prices, addresses, user_assignments}}`.
  - Moves all references by NAME (`tours.plads`, `container_orders.plads`,
    `genbrug_orders.plads`, `tour_prices.plads`) and by id (`plads_addresses.plads_id`,
    `users.assigned_plads_ids`), then deletes the source plads.
  - Validations: 400 for same source/target, 404 for missing IDs, super_admin only.
  - UI: purple `GitMerge` icon on each plads card opens a confirmation modal that
    requires typing "SLET" to confirm.

- **(c) Plads PDF & Excel Export** (P1)
  - SuperAdmin → Plads panel: two new buttons (Excel + PDF).
  - Excel (`xlsx` lib): two sheets — "Pladser" (master list grouped by company)
    + "Underadresser" (all sub-addresses).
  - PDF (`jspdf` + `jspdf-autotable`): landscape A4, grouped by company, columns
    Navn / By / Adresse / Kode / Underadr.-count.
  - Both respect the current search/company filter in the panel.

### Remaining backlog
- P2: Search box on Driver plads picker
- P2: Order History page for `order` users
- P2: Move "Containere"/"Bestillinger" management entirely into the Employee
  (`order`) UI (now that they are removed from the LocationAdmin page)
- P2: Add Customer ID (e.g. K001) to invoice/rapport PDFs
- P2: Logistics-Admin landing page: surface a read-only "Tilknyttede kunder"
  panel listing every customer this logistics co serves (we already enrich
  tours with customer_name; show the same info on the LA dashboard)
- P3: Auto-archive inactive users after 30 days
- P3: Activity log advanced filtering (role, date, IP)
- P3: Split `server.py` into routers
- P3: Move `is_hq_admin` + `assigned_plads_ids` into JWT claims to avoid extra
  user lookup on every `/api/genbrug/plads-rapport` request.

## What's been implemented (2026-06-11) — Iteration 9: SuperAdmin 4th tab — "Tilføj logistik partner"

Per user feedback: logistics-partner CRUD must live in its OWN tab, completely
separated from customer creation.

- **SuperAdmin nu med præcis 4 tabs**:
  1. Kunder & Logistik (uændret — kun "Ny kunde"-knap, "Ny logistik partner"-knappen er FJERNET)
  2. Ejere (uændret)
  3. Kunde-administratorer (uændret)
  4. **Tilføj logistik partner** (NY)

- Ny `LogisticsPartnersPanel` komponent i `SuperAdminPage.jsx`:
  - Søgbar tabel med firma / ref-kode / admin / telefon / oprettet / status
  - "Tilføj logistik partner"-modal med email-invitations-flow (intet adgangskode-felt)
  - Edit-knap (admin email/navn disabled, kun firma + telefon + status redigerbar)
  - Gensend-invitation-knap pr. række når admin er pending
  - Status-cascade: når firmaet er sat inaktivt, vises admin-rækken som "Inaktiv" og resend skjult

- Customer admin's link-flow uændret: `/api/org/logistics-companies` returnerer
  fortsat hele kataloget med `linked` flag — disse partnere skifter blot
  hvilken UI de oprettes fra.

- Backend uændret (samme `/api/superadmin/companies` POST endpoint accepter
  `company_type=logistics`-payload som før).

- Testing: 3 nye pytests + alle 20 regression-tests fra iteration 7+8 passer (23/23 backend). Playwright: 14/14 frontend asserts pass.

## What's been implemented (2026-06-11) — Iteration 8: Batch 1 corrections + Batch 2 + Batch 3

### Batch 1 corrections (per user feedback after iteration 7)
- **SuperAdmin customer card**: trash + power-toggle icons REMOVED. Only Stats + Edit remain. Deactivation now lives inside the Edit modal (existing Status checkbox).
- **Two distinct create buttons**: "Ny kunde" (green) + "Ny logistik partner" (blue) — both open the same modal but with the right type pre-selected. Logistics partner creation also uses the email-invitation flow (no password input — same UX as customer creation).
- **Cascaded inactive status**: when a customer firm is set inactive, the first_admin display in BOTH the customer card AND the Kunde-administratorer tab now shows "INAKTIV" (badge + banner). Gensend-invitation button is hidden when the firma is inaktiv.
- **CustomerAdminPage location_admin form**: password field removed. Backend `org_create_user` enforces invitation-flow when role is `location_admin` or `order`. Rows now show invitation status badge (Afventer/Aktiv/Inaktiv) + Mail-icon resend button for pending.

### Batch 2 — Lokation Admin overhaul (`/app/frontend/src/pages/LocationAdminPage.jsx`)
- 4 tabs: **Medarbejdere · Bestillinger · Logistik-partnere · Slet permanent**
- **Medarbejdere**: trash icon GONE. Edit + Aktivér/Inaktivér toggle + Resend (if pending). Form: Navn / Email / Telefon / Ansættelsesdato. Default filter shows only active employees; "Vis også inaktive"-knap viser også inaktive. No password input — invitations only.
- **Bestillinger**: lokationsbaseret dashboard. 4 status-tiles (afventer / accepteret / afhentet / I alt) der også fungerer som filter. Tabellen viser ordredato, materiale, container, leveringsadresse, bestilt-af, status. Multi-tenant isolated.
- **Logistik-partnere**: read-only liste over partnere tildelt denne lokation af kunde-administratoren. Ingen tilføj/fjern.
- **Slet permanent**: kun INAKTIVE medarbejdere kan slettes her. Deactivate-first policy enforced af backend (DELETE returnerer 400 hvis bruger stadig er aktiv).

### Batch 3 — Medarbejder/order user UI (`/app/frontend/src/App.js` CustomerOrderPage)
- **Header**: viser "Logget ind som <navn>" + dedikeret Log-ud-ikon (data-testid `header-logout-btn`) i højre side.
- **Leveringsadresse OBLIGATORISK**: rød asterisk + rød border når tom. Submit med tom adresse viser toast "Leveringsadresse er påkrævet" og hopper tilbage til trin 3. Backend afviser ligeledes med 400 hvis der er Authorization-header.
- **Ordre-success-skærm**: 3 knapper — "Opret ny bestilling" / "Tilbage til start" (resetter form, logger IKKE ud) / "Log ud" (eksplicit logout).
- **"Mine bestillinger" vs "Alle bestillinger"** toggle på history-view. Default = mine. I "Alle" vises hver ordre med "Bestilt af <navn>" + tidspunkt.
- **Action logging**: `/api/customer-orders/submit` capter nu created_by_user_id/created_by_name/created_by_email fra JWT (når authenticated). Lokation Admin's Bestillinger-tab bruger disse til "hvem og hvornår"-kolonne.

### Backend ændringer (`/app/backend/server.py`)
- `org_create_user`: location_admin/order roller går altid gennem invitations-flowet (password optional). password_hash="" indtil invitation accepted.
- `org_update_user`: ny endpoint til at redigere medarbejdere (navn/email/phone/employment_date/active).
- `org_resend_invitation`: regenererer token + sender invitation til en specifik bruger.
- `org_delete_user`: deactivate-first policy. 400 hvis aktiv.
- `/api/org/locations`: returnerer nu `logistics_partners: [{id, name}]` per lokation.
- `/api/container-orders/by-location/{code}`: enriches each order with `created_by_name`, `created_by_email`, `status_label` (afventer/accepteret/afhentet/annulleret).
- `/api/customer-orders/submit`: optional JWT-aware. Når authenticated → captures user + enforces leveringsaddresse.
- `Tour` model: optional `customer_name` + `customer_code` fields (already added in iteration 6).

### Testing
- New pytest: `/app/backend/tests/test_iteration8_batch2_batch3.py` — 10/10 PASS.
- Regression: `/app/backend/tests/test_invitation_and_reset_flow.py` — 10/10 PASS.
- Testing agent (iteration_8.json): **100% backend (20/20) + 100% frontend**, 0 bugs found.

## What's been implemented (2026-06-11) — Iteration 7: Batch 1
**Invitation + password-reset infrastructure + SuperAdmin UI refactor.**

- **Resend e-mail service** integrated (`/app/backend/email_service.py`).
  Free-tier API key in `.env`. `EMAIL_OVERRIDE` env var redirects all
  outbound mail to a single inbox during testing (Resend sandbox limitation).
  When the user later verifies a custom domain in Resend, unset `EMAIL_OVERRIDE`
  and update `SENDER_EMAIL` — no code change needed.

- **Token-based onboarding**: new `invitation_tokens` collection. Two kinds:
  `invitation` (new user → set first password) and `reset` (existing user →
  glemt-adgangskode). Both 72h TTL, single-use, auto-invalidate older tokens
  of the same type on regeneration.

- **New auth endpoints (all public):**
  - `POST /api/auth/forgot-password` — always 200 (no enumeration). Emails
    a 72h link if the address matches an active user; emails the original
    invitation if the user is still pending.
  - `POST /api/auth/reset-password` — consumes token + sets password.
  - `POST /api/auth/accept-invitation` — consumes token + sets password and
    flips `invitation_status` to `active`.
  - `GET /api/auth/verify-token` — pre-validation for the UI (no consume).

- **Auth model changes:** `User` gained `invitation_status` ("pending"/"active"),
  `employment_date`. `Company` gained `admin_phone`. `CompanyCreate` now
  requires `customer_id` (Pydantic validation).

- **Backend hardening:**
  - Login refuses pending users with a friendly Danish 403 message.
  - `/api/superadmin/users` rejects anything but `role=super_admin` with 403
    + Danish detail.
  - `POST /api/superadmin/companies` requires `customer_id` (with cross-firma
    uniqueness check), accepts `admin_name`/`admin_email`/`admin_phone` (no
    password) and auto-sends invitation.
  - `POST /api/superadmin/companies/{id}/resend-invitation` regenerates token
    + flips admin back to pending.
  - `POST /api/org/users` (used by customer_admin and location_admin) now
    supports the invitation flow by default for `location_admin` and `order`
    roles. Password is now optional; when omitted the user receives an invite.
  - `PUT /api/org/users/{id}` allows lokation-admin to edit
    name/email/phone/employment_date/active without touching password.
  - `POST /api/org/users/{id}/resend-invitation` regenerates a token and
    re-sends it for any in-scope subordinate user.

- **Frontend:**
  - `LoginPage`: input type=text (allows ø/æ/å), "Glemt adgangskode?" link
    with inline forgot stage + "Mail sendt" confirmation.
  - New `SetPasswordPage` (used for both `/set-password?token=...` and
    `/reset-password?token=...` via App.js path-detection at top of router).
  - `SuperAdminPage`:
    - 3rd tab "Kunde-administratorer" — read-only overblik with
      status + per-row "Gensend invitation".
    - Old "Owners" label renamed to "Ejere" (everything dansk).
    - Old "Aktivitet" panel replaced by **license-overblik** "Aktive
      medarbejdere pr. kunde" (columns: Kunde / Kunde-ID / Status / Aktive
      medarb).
    - Customer card shows status badge (Afventer/Aktiv), admin phone,
      oprettet-dato, active employee count, and "Gensend invitation" button.
    - Ny kunde modal: `customer_id` required (\*), `admin_phone` added,
      `admin_password` REMOVED.
    - Ny ejer modal: dropdown for role/company gone (always super_admin),
      only Email/Navn/Telefon/Adgangskode fields visible.

- **DB cleanup**: per ejerens request all non-super_admin users were wiped
  along with all companies/locations/tours/orders/tokens. Only the three
  super_admins remain (see `/app/memory/test_credentials.md`).

- **Regression coverage**: 10 new tests in
  `/app/backend/tests/test_invitation_and_reset_flow.py` (all passing).
  Testing agent confirmed 100% backend + 100% frontend (iteration_7.json).

## What's been implemented (2026-02-23) — 5-Level hierarchy follow-ups

- **(P0) BUG FIX — Employee (`order`) login "location not found"**:
  Legacy `locations` collection was migrated into `plads`, but
  `/api/locations/code/{code}` still queried `locations` only. Added
  `_lookup_site_by_code(code)` helper (server.py ~L3389) that checks `plads`
  first (by `location_code` / `code`) and falls back to legacy `locations`.
  Applied to `/api/locations/code/{code}`, `/api/locations/{code}/containers`,
  `/api/locations/{code}/containers/override`, `/api/locations/{code}/materials`
  (GET/POST/PUT/DELETE), `/api/container-orders` and
  `/api/customer-orders/submit`. Materials writes route to whichever
  collection currently owns the doc (`_materials_write_target`). New
  regression suite: `/app/backend/tests/test_location_lookup_plads_fallback.py`
  (3/3 passing).

- **(P0) LocationAdmin UI** (`/app/frontend/src/pages/LocationAdminPage.jsx`):
  Removed "Containere" + "Bestillinger" tabs and the tab bar itself. Page now
  shows ONLY the employees section with an info banner clarifying that
  containers/orders are managed by employees on the order UI.

- **(P0) CustomerAdmin Logistics Partner UI**
  (`/app/frontend/src/pages/CustomerAdminPage.jsx`): The "Tilknyt" modal no
  longer asks for admin name / email / password. Customer admins (Jørgen /
  Lone) can only assign an already-existing logistics company. User
  provisioning is now exclusively the System Owner's responsibility (per
  the ContainerFlow architecture deck).

- **(P1) Driver UI — visual customer separation** (`App.js`):
  • `/api/tours` (driver role) now enriches every tour with `customer_name`
    and `customer_code` based on the tour's `company_id`. Added these as
    optional fields on the `Tour` Pydantic model so they survive
    serialization.
  • New `customerFilter` state + `customerOptions` memo: when the selected
    plads has tours from more than one customer, a sticky pill-tab row
    appears with "Alle kunder", optional "Eget firma", and one tab per
    customer (ARGO / MARTO / …).
  • Both HÆNGER and SOLO tour rows now show a small blue customer badge
    next to the fraction name when the tour belongs to a different
    customer than the driver's own company.



═══════════════════════════════════════════════════════════════════════════════
## Phase 9.1 — CO2-refaktorering: Materialet ejer CO2-kategorien (2026-06-18)
═══════════════════════════════════════════════════════════════════════════════

### Brugerkrav
- Fjern "CO2-Type"-dropdown fra ordre-bekræftelse ("Bekræft og bestil").
- Knyt CO2-kategori til materialet i "Vælg materiale"-step i stedet.
- CO2-rapport (diagrammer + Excel-eksport) skal være synlig for BÅDE
  `customer_admin` OG `location_admin`.
- Kun NYE ordrer bruger den nye logik (ingen migration af historik).
- Nye materialer KRÆVER en CO2-kategori; eksisterende kan opdateres manuelt.

### Backend ændringer (server.py)
- Nyt felt `material_co2_categories` på plads-dokumentet (dict: material_name → co2_type_id).
- `POST /api/locations/{code}/materials` accepterer `co2_category_id`.
- `PUT /api/locations/{code}/materials` accepterer `co2_category_id` (med eller uden rename).
- `GET /api/locations/{code}/materials` + `.../active` returnerer `material_co2_categories`.
- `DELETE /api/locations/{code}/materials` rydder også CO2-mapping.
- `_lookup_site_by_code` returnerer nu `material_co2_categories`-feltet.
- `submit_customer_order`: Hvis `co2_type_id` IKKE er medsendt slås CO2 automatisk
  op via materialets kategori (bagudkompat: eksplicit id overstyrer).
- `GET /api/org/reports/orders` (LA-endpoint) returnerer nu også
  `total_co2_kg`, `by_co2_type`, `co2_over_time`, `total_weight_kg`.
- Ugyldig `co2_category_id` afvises (400) ved POST/PUT.

### Frontend ændringer (App.js)
- Step 3 ("Bekræft og bestil"): CO2-type dropdown FJERNET.
- OrderEditModal: CO2-type dropdown FJERNET.
- Step 1 ("Vælg materiale"):
  - Hvert materiale-kort viser CO2-kategori-chip (`material-co2-chip-N`).
  - "Tilføj nyt materiale"-form udvidet med obligatorisk CO2-kategori-dropdown
    (`new-material-co2-select`) — submit-knappen er disabled hvis ikke valgt.
  - Inline "Rediger"-form udvidet med valgfri CO2-kategori-dropdown
    (`material-edit-co2-N`).
- Nyt state: `materialCo2Map`, `newMaterialCo2Id`, `editMaterialCo2Id`.

### Frontend ændringer (LocationAdminPage.jsx)
- 5. KPI-tile "CO2 (kg)" (`tile-co2`) tilføjet ved siden af Total/Værksted/Afventer/Haste.
- 2 nye charts:
  - `ladmin-co2-over-time` — LineChart over CO2-udvikling i perioden.
  - `ladmin-co2-by-material` — BarChart + top-6 tabel over CO2 pr. materiale.
- Begge charts renderes betinget (kun når der findes CO2-data).

### Frontend (excelExport.js)
- Excel-eksport indeholder allerede generisk "Samlet CO2"-KPI + "CO2-aftryk pr. materiale"-
  sektion — fungerer automatisk for LA nu hvor backend-data er tilgængelig.

### Tests
- `/app/backend/tests/test_phase9_co2.py` opdateret til den nye material-linked
  CO2-logik. **18/18 grøn**.
- Testing agent iter31: 23/23 backend (18 intern + 5 live URL) + 100% frontend
  data-testids verificeret.

### Filer
- Modificeret: `/app/backend/server.py`, `/app/frontend/src/App.js`,
  `/app/frontend/src/pages/LocationAdminPage.jsx`.
- Test opdateret: `/app/backend/tests/test_phase9_co2.py`.
- Rapport: `/app/test_reports/iteration_31.json`.

═══════════════════════════════════════════════════════════════════════════════


═══════════════════════════════════════════════════════════════════════════════
## Phase 11 — Bestillingstidspunkt + claim-isolation + Planlægning-redesign (2026-06-18)
═══════════════════════════════════════════════════════════════════════════════

### Brugerkrav
1. Vis bestillingsdato + bestillingstid (created_at), afhentningsdato, kapacitetsmål
   og opgavetype som kompakt info-blok på alle bestillinger (admin, chauffør, kunde).
2. Vægt + CO2 KUN for opgavetypen 'normal' (afhent container).
   For 'flyt' / 'vaerksted' / 'afhent_vaerksted' må vægt/CO2 ALDRIG sættes — ikke i UI, ikke i DB.
3. DB-migration: nulstil eksisterende ikke-normale ordrer.
4. 'Tilføj tur manuelt' fjernes fra chauffør-siden — kun synlig for admin.
5. Helt om-bygget 'Planlægning'-side: split-view med ikke-tildelte ture til
   venstre + chauffør-liste m. kapacitets-bar til højre.
6. Pre-tildelte ture er KUN synlige for tildelt chauffør.
7. Claimet tur er KUN synlig for claimende chauffør (forsvinder fra andre).
8. 'Tilbage'-knap nulstiller turen helt (claim, on_way, completed, vægt).
9. 'På vej'-knap kan KUN aktiveres én gang — ikke toggle.
10. Chauffør kan skifte hænger fra headeren.
11. Hænger-kapacitet håndhæves: max samtidige ture = capacity + 1.
12. Færdige ture skjules som default; 'Vis færdiggjorte' toggle.
13. Moderniser farver (grøn fjernet fra kunde-vælger, baggrund matcher LA-side).
14. Real-time polling hvert 5. sekund.

### Backend ændringer (`server.py`)
- `submit_customer_order`: CO2-snapshot KUN hvis tour_type == "normal".
- `submit_customer_order`: `assigned_logistics_company_ids` falder tilbage på
  `location` (vigtigt da public QR-flow har ingen tenant context).
- `update_container_order`: Hvis tour_type != "normal" tvinger den
  weight_kg=0, co2_kg=0, co2_factor=0, co2_type_id="", co2_type_name="".
- `update_tour`: Tvinger weight=0 + co2_kg=0 hvis tour_type != "normal".
- Mirror order from tour-update: kun ved tour_type == "normal".
- Mirror update bruger nu `_raw_db` (tenant-bypass) så driver kan opdatere
  kundens ordre uden at tenant-filter blokerer.
- `_lookup_site_by_code`: returnerer nu også `material_co2_categories`.
- GET `/api/tours` (driver-visning): claim-isolation tilføjet — drivers
  ser ikke længere ture claimet af andre.
- `_user_to_public`: returnerer nu også `active_vehicle_id`, `active_trailer_id`, `plate`.

### Frontend ændringer (`App.js`)
- Ny `OrderInfoLine`-komponent: kompakt info-blok m. ikoner for
  bestillings-tidspunkt + afhentningsdato + kapacitet + opgavetype.
  Bruges i: Customer "Mine bestillinger", MobileTourCard, Planlægning split-view.
- `MobileTourPanel`:
  - `handleRelease`: nulstiller alle status-felter + weight=0 (kun for normal).
  - `handleCompleteClick`: springer vægt-prompt over for ikke-normale opgavetyper.
  - "På vej"-knap disabled efter første klik.
- Driver header:
  - Ny `trailer-picker-btn` dropdown — chauffør skifter hænger uden at logge ud.
  - Kunde-vælger nu i neutrale slate-farver (var emerald/grøn — usynlig).
  - Light-mode baggrund: `bg-slate-50` (matcher LA-side, ikke ren hvid).
- "Vis færdiggjorte ture"-toggle (`driver-toggle-completed-btn`) + tom-state
  "Alle dagens ture er fuldført 🎉" med call-to-action.
- "Tilføj tur"-fane FJERNET fra driver-tabs.
- CO2-chip på ordrer skjult hvis tour_type != "normal".
- Polling-interval: 5 sek (var 10 sek).

### Ny Planlægning-side (App.js)
- 2 sub-tabs: "Tour-tildeling" (default) + "Plads & fridag" (legacy).
- **Tour-tildeling split-view**:
  - Venstre (60%): Ikke-tildelte ture m. customer/plads-filter + nulstil.
  - Højre (40%): Chauffører m. avatar, vogn, hænger, kapacitets-bar,
    aktive ture som chips, "fuld"-advarsel hvis activeCount ≥ capacity+1.
  - Workflow: Klik en tur → marker (orange ring) → klik chauffør → tildelt.
  - Polling refresh hvert 5. sek.

### Frontend ændringer (`pages/LocationAdminPage.jsx`)
- 5. KPI-tile "CO2 (kg)" tilføjet i Rapport-tab (fra Fase 9.1).

### Manuelle ture (App.js)
- Tildelings-dropdown ERSTATTET med read-only badge + info-banner der peger
  på Planlægning-fanen.

### Tests
- `/app/backend/tests/test_phase11_orders_visibility.py` — 12/12 grøn.
  Dækker: ny info-blok, vægt/CO2-regler pr. opgavetype, claim-isolation,
  pre-tildelings-synlighed, 403 ved forsøg på at claime andens pre-tildelte tur.
- Alle øvrige regression suites (Fase 2–10): grøn.
- Testing agent iter_32: fandt 1 CRITICAL bug (`trailersList` scope issue).
- Testing agent iter_33: bug fixed, Planlægning split-view fuldt synlig + alle data-testid'er verificeret.

### DB Migration
- `/app/scripts/migration_phase11_cleanup.py` kørt — nulstillede vægt/CO2 på
  alle ordrer hvor tour_type != "normal".

### Filer
- Modificeret: `/app/backend/server.py`, `/app/backend/auth.py`,
  `/app/frontend/src/App.js`, `/app/frontend/src/pages/LocationAdminPage.jsx`.
- Tilføjet: `/app/backend/tests/test_phase11_orders_visibility.py`,
  `/app/scripts/migration_phase11_cleanup.py`.
- Rapporter: `/app/test_reports/iteration_32.json`, `/app/test_reports/iteration_33.json`.

═══════════════════════════════════════════════════════════════════════════════


═══════════════════════════════════════════════════════════════════════════════
## Phase 12 — Driver UI overhaul + Manuel tidsregistrering + Admin Planlægning rename (2026-06-18)
═══════════════════════════════════════════════════════════════════════════════

### Brugerkrav — SEKTION 1 (chauffør)
- 1.1 Vis bestillingstidspunkt på hver tur (allerede klaret via OrderInfoLine i fase 11).
- 1.2 Ruteoptimering SLUKKET som standard; chaufføren skal selv aktivere.
- 1.3 Korte tabs/knapper: 'Lokationer'-label på plads-dropdown. 'Ture'-tabbaren fjernet (kun én fane).
- 1.4 Ind/Ud-toggle-knap erstatter Start/Slut-felter. Altid synlig 'Manuel tidsregistrering'-knap åbner modal (dato/start/slut/årsag).
- 1.5 Datofelt ALTID synligt (flyttet ud af toolbarExpanded så det ikke kan minimeres væk).
- 1.6 Tur-vinduet: Auto-luk efter 'På vej' klik. Chat-knap fjernet. 'Tilbage' omdøbt til 'Fortryd'. Kun 3 knapper.
- 1.7 Vægt skjult for ikke-normale opgavetyper (allerede via Fase 11).
- 1.8 Billede-ikon (kvittering-liste) fjernet fra både desktop + mobile toolbar.

### Brugerkrav — SEKTION 2 (logistik admin)
- 2.1 'Plads & fridag'-tab fjernet fra Planlægning.
- 2.2 'Tour-tildeling' omdøbt til 'Planlæg ture'.
- 2.3 'Planlæg ture' fetcher uden source-filter → viser ALLE bestillinger (manuel + argo + customer_order).
- 2.4 Tildelings-blokering fjernet — admin må tildele ubegrænset til chauffør (visning af kapacitet beholdes som info).
- 2.5 Hænger-validering KUN på chauffør-claim (eksisterende, verificeret).

### Backend (`server.py`)
- Ny model `ManualTimeEntry` + helper `_compute_duration_minutes` (overnight-håndtering).
- `POST /api/driver/time-entries`: opretter/opdaterer (idempotent) dag-niveau-post.
- `GET /api/driver/time-entries`: returnerer kun egen drivers entries.

### Frontend (`App.js`)
- Ny `ManualTimeEntryModal` komponent (~135 linjer).
- Driver header omstruktureret:
  - Ny "altid synlig" top-bar (`driver-always-visible-bar`) med datofelt+pile, punch-in/ud-knap, manuel-knap.
  - `manualTimeModalOpen` state.
  - Gamle start-time-input / end-time-input / report-date-input / tab-trips / receipt-list-btn elementer fjernet.
- Plads-dropdown viser nu "Lokationer".
- Route-optimering: ny `routeOptEnabled` state (persistent i localStorage 'cf:driver:routeOpt'), default false. Manuel klik aktiverer + indlæser.
- MobileTourPanel: Chat-knap fjernet. 'Tilbage' → 'Fortryd'. På vej-klik auto-lukker panelet (setTimeout 150ms).
- Admin Planlægning sub-tabs: kun "Planlæg ture" (det andet er fjernet).
- Nyt `planningTours` state — fetcher ALLE source-typer for Planlægning-fanen, mens `adminTours` (manuel+argo) er reserveret til Manuelle ture-fanen.
- Capacity-blokering på admin-tildelings-side fjernet (admin må tildele uanset chaufførens load).

### Tests
- `/app/backend/tests/test_phase12_time_entry.py` — 9/9 grøn.
- Alle Fase 2/3/4/5/6/8/9/10/11/12 pytest-suiter stadig grøn.
- Testing agent iter_34: 100% pass — backend 9/9, frontend 17/17 krav verificeret end-to-end.

### Bugfix
- ILK Logistics Admin password (`ilkdistadmin@gmail.com`) genseed'et til `TestPass2026!` (drift-issue fra tidligere iterationer).

### Filer
- Modificeret: `/app/backend/server.py`, `/app/frontend/src/App.js`.
- Tilføjet: `/app/backend/tests/test_phase12_time_entry.py`.
- Rapport: `/app/test_reports/iteration_34.json`.

═══════════════════════════════════════════════════════════════════════════════


## Fase 15.8 — Mine ture-bug + Tildelt af-chip + Planlægning-filter (2026-02-19)

### Brugerklage
> "kan jeg stadig ikke se 'tildelt af XXX' informationen på en tur"
> "når jeg vælger 'mine ture' ser jeg ingen ture i nuværende version"
> "implementér søg+udvid/skjul alle på Tildelte ture pr. chauffør"

### Bugfix #1 — `selectedDriver?.id` var altid null i driver-flowet
- `selectedDriver` blev ALDRIG sat efter login i driver-UI'en — kun i admin-flows.
- Alle "Mine ture"-filtre brugte `myId = selectedDriver?.id || ""` → tomt id → byAssign matched ingen → admin-tildelte ture med driver_id sat blev ikke detekteret som "mine".
- **Fix**: `myId = selectedDriver?.id || authUser?.id || ""` (alle 5+ steder).

### Bugfix #2 — Mine ture "__MINE__" blev nulstillet straks efter klik
- En useEffect validerede `selectedPlads` mod pladsList og kaldte `setSelectedPlads("")` for ikke-eksisterende pladser → virtuel `"__MINE__"` blev øjeblikkeligt slettet.
- **Fix**: Tilføjet `if (selectedPlads === "__MINE__") return;` i begge validation-effects.

### Bugfix #3 — `assigned_by_name` lagrede email i stedet for navn
- JWT payload manglede `name` → fallback til `email` → DB-værdi blev `"ilkdistadmin@gmail.com"`.
- **Fix**: Slå op i `users`-collection efter `display_name`/`name` før email-fallback (`bulk_assign` + `update_tour`).
- **Backfill**: 6 eksisterende ture konverteret fra email → "ILK Dist Admin".
- "Tildelt af X"-chip gjort visuelt prominent: solid indigo baggrund + UserCheck-ikon + hvid skrift (var subtilt indigo-tekst på 20% baggrund).

### P0-feature — Søg + Udvid alle/Skjul alle i Planlægning
- Nyt fritekst-felt over "Tildelte ture pr. chauffør" — søger på materiale, tur-nummer, chauffør-navn, plads, adresse, kunde, assigned_by_name.
- "Udvid alle"-knap → rydder `planningCollapsedDrivers`-set.
- "Skjul alle"-knap → tilføjer alle chauffør-id'er til samme set.
- Når søgning matcher en chauffør, vises ALLE deres ture; ellers vises kun matchende ture.

### Filer
- `/app/frontend/src/App.js`: 6+ steder fikset (linje 11529, 11643, 11671, 11992, 12767, 13960, 13979, 14040, 14291) + ny søg+expand UI i Planlægning (linje 7895-7995) + `__MINE__`-header-display + chip styling (3 visninger).
- `/app/backend/server.py`: `bulk_assign` (linje 1377) og `update_tour` (linje 2003) bruger nu DB-lookup for display_name.
- `/app/backend/tests/test_phase15_8_assigned_by_display_name.py`: ny pytest, grøn.

### Validering
- Live screenshot: testx-chauffør ser nu 5 ture under "Mine ture" med "Tildelt af ILK Dist Admin"-chip på hver admin-tildelt tur.
- Admin Planlægning viser søgefelt + Udvid alle + Skjul alle; søg på "TUR-0118" filtrerer ned til 1 chauffør med 1 tur.
- Backend regression: test_phase14_edit_tour + test_phase15_2_admin_assigned_visibility + test_phase15_8 — alle grønne.


## Fase 15.10 — Sektion-headers + "På vej" bug på tildelte ture (2026-02-20)

### Brugerklage
> "ja det vil jeg gerne have" (sektion-skel)
> "når jeg vælger 'på vej' på tildelte ture sker der ikke noget? fiks dette"

### Bugfix — "På vej" gjorde intet på admin-tildelte ture (403 silent)
- Frontend sendte `claimed_by_id: selectedDriver?.id || ""` ved on_way-claim. Da `selectedDriver` var null i driver-flowet (samme rod som Fase 15.8) blev claimed_by_id="" sendt.
- Backend tolkede `claimed_by_id===""` + tour.assigned_by_id sat som "fortryd-tildeling"-forsøg → 403 "Denne tur er tildelt af administrator". Errortoast'en blev dog ikke vist i driver-UI'en, så fra brugerens synspunkt skete der "ingenting".
- **Fix**: Alle 8 write-steder i App.js bruger nu `selectedDriver?.id || authUser?.id || ""` for `claimed_by_id`. Verificeret via curl: gammel adfærd → 403, ny adfærd → 200.

### P2-feature — Sektion-headers ("HASTER" / "Mine tildelte ture" / "Ledige ture")
- Soloturlisten partitioneres på render-tid via `classifyTour()`:
  - **HASTER** (rød) — `priority === "urgent"` eller remark indeholder "haster"
  - **Mine tildelte ture** (indigo) — driver_id eller claimed_by matcher login-id'et
  - **Tildelt til andre** (grå) — har en owner men ikke mig (sjælden i driver-view, hvis det sker er det defensiv)
  - **Ledige ture** (grøn) — ingen owner
- Hver header viser ikon + label + antal i sektion. Headers vises kun ved overgang (ikke duplikeret).

### Filer
- `/app/frontend/src/App.js`:
  - 8 claimed_by_id-write-steder fikset (linje ~12021-12148) via replace_all.
  - Solo-tour-render refaktoreret: indre IIFE for sektion-grouping + hoisted `renderSoloTour()`-helper (linje ~14807-15068).

### Validering
- Live screenshot: testx-driver ser nu "HASTER 1" → "MINE TILDELTE TURE 5" headers med korrekte chips og sortering.
- curl-test bekræfter at gammel "" claim_id → 403, ny authUser-fallback → 200.


## Fase 15.11 — "Fortryd" på admin-tildelte ture (2026-02-20)

### Brugerklage
> "Fortryd-knappen skal også vises for tildelte ture (når man trykker 'på vej' men fortryder), skal man kunne trykke 'fortryd' og status ændres til 'venter', dog skal den stadig være tildelt den samme chauffør."

### Implementering
**Frontend (`App.js`):**
- Fjernet `!tour.assigned_by_id`-betingelsen fra Fortryd-knappen — den vises nu også på tildelte PÅ VEJ-ture.
- Bekræftelses-dialogen tilpasses: "Fortryd kørsel? Turen skifter til VENTER men forbliver tildelt dig" (vs. fri tur: "Vil du give turen tilbage?").
- Toast-besked: "Kørsel fortrudt — turen er tilbage på VENTER" (vs. "Turen er nulstillet og givet tilbage").
- Den lille "Tildelt af X — kontakt din logistikadmin"-banner vises stadig som information, men spærrer ikke længere knappen.

**Backend (`server.py`):**
- Linje 1869-: Erstattet `wants_unclaim` blok med `wants_unassign_self` — kun eksplicit clear af `driver_id` af driveren selv blokeres nu. Almindelig clear-claim er tilladt.
- Linje 1960-: I "explicit unclaim"-grenen (`update.claimed_by == ""`) — bevares `assigned_by_*` og `driver_id` hvis caller er den tildelte chauffør (`is_driver_self_revert`). Admin's frigør-flow rydder stadig hele tildelings-sporet som før.

### Verificeret
- Pytest `test_phase15_11_driver_fortryd_keeps_assignment.py`: passes ✓
- Live UI screenshot: Træ-tur (testx, PÅ VEJ) viser nu "Fortryd"-knap sammen med "På vej ✓" og "Afslut".
- API-flow: PUT on_way=true → 200 PÅ VEJ; PUT claimed_by="" → 200, driver_id+assigned_by_* bevaret, on_way=False.


## Fase 15.12 — Sektion-headers med antal, isoleret "Mine ture" + prioritets-chip (2026-02-20)

### Brugerønsker
- Hver sektion skal vise antal i parentes: "Haster (1)", "Mine ture (7)", "Ledige ture (4)"
- Inden for sektionen sorteres kronologisk: PÅ VEJ → `on_way_time` asc, VENTER → `order_date` asc
- Global "Mine ture"-fane skal IKKE vise Ledige ture — kun mine + HASTER-undtagelse (kun hvis fri eller tildelt mig)
- Lokationssider beholder alle 3 sektioner
- Tilføj generel prioritets-chip på hver tur: "Haster" / "Normal" / "Senere"

### Implementering
**Frontend (`App.js`):**
- **Sortering**: `sortedTours` opdateret — efter sektion-tier (urgent → tildelt → fri) tilføjet kronologisk sub-sort. PÅ VEJ-ture matches på `on_way_time`, VENTER på `order_date`.
- **"Mine ture"-filter**: `filteredTours` for `selectedPlads === "__MINE__"` erstattet med en strikt regel:
  ```
  isMine OR (isUrgent AND NOT claimedByOther AND NOT assignedToOther)
  ```
  Ingen "Vis afventende"-toggle længere; ledige frie ture vises kun på lokationssiderne.
- **Sektion-headers**: Label-format ændret til "(N)" — fx "Mine ture (7)". Tæller pr. sektion via `sectionCounts` reduktion.
- **Prioritets-chip**: Ny helper `getPriorityChip()` + `PRIORITY_CHIP_MAP` med 3 grupper (Haster rød, Normal blå, Senere grå). Chip tilføjet på MobileTourCard + HAENGER inline + SOLO inline med Flag-ikon.
- Tilføjet `Flag`-import fra `lucide-react`.

### Filer
- `/app/frontend/src/App.js`: ~70 linjer ændret i 5 sektioner (line ~177, 12809, 12907, 14856, 14881, 3697, 14725, 15027).

### Verificeret
- Live screenshot: "Mine ture (8)"-badge → "Haster (1)" og "Mine ture (7)" sektion-headers. Chronologisk: 10:16 (Pap 44444) før 23:47 (Træ 3333). Hver tur viser Haster/Normal-chip.
- Ingen Ledige ture-sektion i Mine ture-fanen.


## Fase 15.13 — Strict Mine ture, Ture hos andre, Senere→Lav + Data wipe (2026-02-20)

### Brugerkrav
1. **Mine ture (global)**: Fjern HASTER-undtagelsen. Vis KUN ture tildelt/taget af login-chaufføren.
2. **Lokationssider**: Tilføj 4. sektion "Ture hos andre chauffører" — pre-collapsed, read-only, kun aktive ture for valgt dato.
3. **"Senere" → "Lav"**: Omdøb UI-label overalt (DB-værdi `priority="low"`/`"senere"` uændret).
4. **Data wipe**: 0 bestillinger total (inkl. container-side). Slet alle chauffør-konti. Behold logistik-admin + container-side data (kunder, pladser, containere, priser, ikke-driver-users).

### Implementering
**Frontend (`App.js`):**
- **Mine ture-filter**: Fjernet `urgentUntakenOrMine` exception ved `__MINE__`-view. Returnerer kun `isMine`.
- **Defensiv filter relakseret**: I `fetchTours` skjules ikke længere ture hos andre chauffører — de tagges via `_is_other_driver`-flag. Orphan-ture (on_way uden ejer) skjules fortsat.
- **classifyTour omprioriteret**: `_is_other_driver` returneres FØR `haster`-check. HASTER-sektionens adfærd er dermed bevaret (kun mine/frie urgent vises der).
- **Ny 4. sektion**: "Ture hos andre chauffører" pre-collapsed (`otherDriverSectionOpen` state, localStorage-persisteret). Filtrerer kun aktive + dagens dato. Read-only kort uden action-knapper. "Hos {ownerName}"-chip + warning-tekst om ikke at bestille ny tur.
- **"Senere" → "Lav"**: Ændret labels i `PRIORITY_CHIP_MAP` (low + senere), priority-vælger i OrderForm (`<h3>LAV</h3>` + `label: "LAV"`).

**Database wipe:**
- Slettet: `tours` (221), `users.role=driver` (3), `driver_sessions` (5), `driver_time_entries` (13), `chat_messages`, `driver_push_subscriptions`, `tour_history`, m.fl.
- Bevaret: `companies` (4), `plads` (11), `containers`, super_admin, logistics_admin (2), customer_admin (2), location_admin (3), order (3).
- ILK Admin-password nulstillet til `TestPass2026!`.
- `/app/memory/test_credentials.md` opdateret.

### Verificeret
- Live screenshot: ilkdistadmin landings-statistik viser 0 Total ture / 0 Fuldførte / 0 Total kg / 0 Chauffører / 0 Aktive — wipe komplet.
- Frontend kompilerer rent.


## Fase 15.14 — Multi-tenant strikt isolation + Kundefirma-tag + Konfigurerbar lønperiode (2026-02-20)

### Brugerkrav
1. **Multi-tenant isolation**: Chauffører må ALDRIG se ture rettet til et andet logistik-firma, uanset om driver_id matcher eller om deres firma "betjener" kunden generelt. Filtreringen skal være på `tour.assigned_logistics_company_ids` matchende driver's `company_id`.
2. **Kundefirma-tag**: Synligt chip på hver tur-kort der viser "Kundefirma: ARGO" (eller tilsvarende) så chauffører kan se hvilken kunde turen tilhører, når deres firma servicerer flere kunder.
3. **Konfigurerbar lønperiode pr. logistik-partner**: Default 20.-19. men hver logistik-partner kan vælge selv (1-28). Slutdagen beregnes automatisk som dag før næste periodes start.

### Implementering

**Backend (`auth.py` + `server.py`):**
- `Company` model: Ny `payroll_start_day: int = 20` field. `CompanyUpdate` model: nu også `payroll_start_day: Optional[int]`.
- **STRAMMET driver-visibility filter** (linje 1163-1182 i server.py): driver_id-undtagelsen kræver nu også `assigned_logistics_company_ids: la_company`. Selv hvis en City Container-tur har driver_id sat til en ILK-chauffør, vises den ikke længere.
- Nye endpoints på `api_router`:
  - `GET /api/company/payroll-settings` — returnerer `{company_id, company_name, payroll_start_day}` for caller's logistik-firma (logistics_admin eller super_admin via X-Acting-Company-Id)
  - `PATCH /api/company/payroll-settings` — opdaterer `payroll_start_day`. Validering: 1-28.
- Pytest `test_phase15_14_multitenant_isolation.py` — opretter 2 logistik-firmaer + indsætter en City-tur med driver_id sat til en ILK-chauffør → verificerer at ILK-chauffør IKKE ser den. **PASSES**.

**Frontend (`App.js`):**
- Kundefirma-tag (`Building2` ikon, lilla, "tour.customer_name") tilføjet på alle 3 tur-visninger (MobileTourCard, HAENGER inline, SOLO inline).
- Ny "Indstillinger"-fane på Logistik Admin-siden: `AdminSettingsPanel`-komponent med input (1-28), live preview af periode-interval, Gem/Fortryd-knapper.
- `payrollStartDay`-state i AdminApp + useEffect der fetcher ved mount.
- `getCycleInfo()` i Arkiv-fanen erstattet til at bruge dynamisk `payrollStartDay` (var hardkodet 19/20).

### Verificeret
- ✅ curl-test: GET/PATCH/validering virker. ILK firma kan ændre dag 20→25→20.
- ✅ Live screenshot: "Indstillinger"-fanen synlig; sætter dag 25 → toast "Lønperiode opdateret"; preview viser "fra dag 25 til dag 24".
- ✅ Pytest multi-tenant isolation: PASS.


## Fase 15.15 — Lønperiode-cyklus (Månedlig/14-dages/Ugentlig) + Arkiv-refleksion (2026-02-20)

### Brugerkrav
1. Udvid lønperiode fra kun "startdag i måned" til **3 valgfri cyklus-typer**: Månedlig, 14-dages, Ugentlig.
2. Ugentlig + ankerdato (fx en tirsdag) → periode skal være tirsdag-til-mandag, dynamisk.
3. Arkiv-fanen skal reflektere konfigurationen øjeblikkeligt — i forrige iteration opdaterede den ikke korrekt.

### Implementering

**Backend (`auth.py` + `server.py`):**
- `Company`-model udvidet med:
  - `payroll_cycle_type: str = "monthly"` (`monthly`/`biweekly`/`weekly`)
  - `payroll_anchor_date: str = ""` (ISO `YYYY-MM-DD`)
  - `payroll_start_day` bevares (kun relevant for `monthly`)
- `PATCH /api/company/payroll-settings` understøtter nu alle 3 felter. Validering: cyklus-type whitelisted, startdag 1-28, ankerdato `YYYY-MM-DD`.

**Frontend (`App.js`):**
- `AdminSettingsPanel` har nu 3 knapper (Månedlig/14-dages/Ugentlig). Conditional UI:
  - Monthly → tal-input (1-28)
  - Weekly/Biweekly → dato-picker for ankerdato
  - Live forhåndsvisning der viser ugedag (fx "tirsdag → mandag")
- `payrollSettings`-state løftet til `AdminApp`. `AdminSettingsPanel` modtager `onSettingsChanged`-callback → opdaterer parent øjeblikkeligt så Arkiv reflekterer ændring uden refresh.
- `getCycleInfo()` omskrevet:
  - Monthly: som før (start-dag i M → start-1 i M+1).
  - Weekly: 7 dage fra ankerdato, dynamisk cykling.
  - Biweekly: 14 dage fra ankerdato.
- Arkiv-grupperne får nu labels som "Uge Fra 23. jun." for weekly, "14-dages fra X" for biweekly, eller "juni 2026" for monthly.

### Verificeret
- ✅ curl: GET/PATCH/validering for alle 3 typer.
- ✅ Live screenshots:
  - Indstillinger med Ugentlig + 09/06/2026 → preview "tirsdag → mandag"
  - Arkiv-fanen viser nu "Uge Fra 23. jun." (23 = tirsdag, 29 = mandag) — uge-gruppering, ikke længere månedlig.
  - Skift tilbage til Månedlig → Arkiv genopretter månedlig gruppering.

---

## Fase 15.16 — "Estimat" vs "Opgave" + dobbeltbestillings-blok (2026-02-21)

### Brugerkrav
1. Tilføj toggle i Tilpasset bestilling: **Estimat** (kun materiale + antal + dato) vs **Opgave** (standard).
2. Tilføj sub-tab **"Planlæg ressourcer"** i Admin-UI som lister estimat-bestillinger grupperet pr. dato.
3. Bloker dobbeltbestillinger: hvis SAMME container (location_code+material+container_number) har en ikke-fuldført bestilling med SAMME `tour_type`, så skal en ny POST returnere **409**. Forskelligt `tour_type` på samme container er OK. Bestillingsdato har ingen betydning.

### Implementering

**Backend (`/app/backend/server.py`):**
- `POST /api/customer-orders/submit`:
  - Hvis `tour_type="estimat"` → spring leveringsadresse/værksted/container-validering over; kræv kun materiale + `estimated_count > 0`; gem `tour.estimated_count`.
  - Dobbelt-blok: query `container_orders` på `{location_code, material, container_number, tour_type, status NOT IN [completed, cancelled]}` → 409 hvis match. Tidligere kørte vi mod `tours.container` hvilket ikke kunne håndtere låste container_id-overrides.
- `GET /api/customer-orders/check-duplicate?location_code=...&material=...&container_number=...&tour_type=...` (refaktoreret) — returnerer `{blocked, order_id, tour_id, order_date, tour_type}`. Legacy `container_id`-parameter bevaret som fallback.
- Estimat-tours gemmes med `tour_type="estimat"` og `estimated_count`-felt på touren.

**Frontend (`/app/frontend/src/App.js`):**
- `OrderForm`: `customRequestMode` state styrer toggle mellem "estimat" og "opgave". Estimat-formular har testids `estimat-form`, `estimat-material`, `estimat-count-input`, `estimat-submit-btn`.
- `refreshBlockedByContainer` omlagt: kalder nu `GET /api/container-orders/by-location/{code}`, grupperer på `container_number`+`material`. Map nøglet på `container_number`-string (matcher `c.label`) i stedet for `c.container_id`.
- Container-grid (step 2) viser amber-ring + chips (`container-blocks-{i}`) på containere med aktive bestillinger; chip-titel viser order_date pr. blokering.
- `EstimateOverviewPanel` (Planlæg ressourcer sub-tab) henter `GET /api/tours?tour_type=estimat&limit=500`, grupperer pr. dato, viser totalt antal containere + materiale-fordeling.

**Tests (`/app/backend/tests/test_phase15_16_estimat_and_duplicate_block.py`):**
- 3 pytests: dobbelt-blok 409, forskellig tour_type OK, completed → ny POST OK; estimat minimal felter; estimat kræver materiale + count > 0.
- Indlæser nu både `backend/.env` og `frontend/.env` for `REACT_APP_BACKEND_URL`. Cleanup bruger `id`-liste (ikke det ikke-eksisterende `container_no`-felt).

### Verificeret (iter_39)
- ✅ Backend pytest 3/3 GREEN på `test_phase15_16_estimat_and_duplicate_block.py`.
- ✅ Live API-test: SAME container+tour_type → 409; DIFFERENT tour_type → 200; completed → ny POST → 200.
- ✅ Frontend "Planlæg ressourcer" sub-tab live-verificeret som logistics_admin — EstimateOverviewPanel renderer estimater grupperet pr. dato.
- ✅ Code-verified testids: `estimat-form`, `estimat-count-input`, `estimat-submit-btn`, `container-blocks-{i}`.

### Test-data
- Ny test-chauffør oprettet: `testdriver@default.local` / `Driver2026!` (tilknyttet ILK logistik-firma).



---

## Fase 15.17 — Planlæg ressourcer UX-forbedringer (2026-02-21)

### Brugerkrav
1. **Bug:** Estimat-bestillinger landede på "Planlæg ressourcer"-tabben uden det `estimated_count` brugeren havde indtastet.
2. **Filtre:** Tilføj dato-filter (default = i dag, knapper for I dag/I morgen/Alle datoer + dato-picker), kunde-filter (default Alle), lokation-filter (default Alle).
3. **Estimat-input:** Tællertallet i bestillingsflowet skal IKKE defaulte til 1 — feltet skal være tomt og man skal kunne indtaste tallet manuelt uden at trykke increment.
4. **Tabel-design:** Fjern unødvendige mellemrum, tilføj klare overskrifter (Dato / Tur-nr. / Materiale / Antal / Lokation / Kunde / Bestilt af) så brugeren ved hvad de kigger på.

### Implementering

**Backend (`/app/backend/server.py`):**
- `Tour`-Pydantic-modellen udvidet med `estimated_count: int = 0`. Tidligere ignorerede `extra="ignore"` feltet under serialisering så frontend modtog tour-dokumenter uden tællerværdien (root cause på fejl #1).

**Frontend (`/app/frontend/src/App.js`):**
- `OrderForm.estimatedCount` initial state ændret fra `1` til `""` (tom streng). Inputfelt accepterer nu frit tal-input via tastatur (regex-strip non-digits) og validerer kun ved submit. `placeholder="Indtast antal"`.
- `PlanningResourcesView` (Planlæg ressourcer) fuldt omskrevet:
  - 3 filtre i én vandret bjælke: **Dato** (knapper I dag / I morgen / dato-picker / Alle datoer), **Kunde** (dropdown, default "Alle kunder"), **Lokation** (dropdown, default "Alle lokationer"). Knappen "Nulstil filtre" vises kun når et filter er aktivt.
  - Default-filter er dagens dato → kun dagens estimater vises ved åbning. Sættes dato til i morgen → kun morgendagens estimater vises. "Alle datoer" rydder filteret.
  - Tabel med 7 kolonner: **Dato** · **Tur-nr.** · **Materiale** · **Antal** · **Lokation** · **Kunde** · **Bestilt af**. Header sticky-stil med uppercase tracking. Rows har hover-highlight (amber). Antal-kolonnen højrejusteret + amber-farve.
  - Header viser nu `{n} estimater` + `Total: {sum} container(e)` baseret på *filtrerede* poster.

### Verificeret
- ✅ Backend pytest 3/3 GREEN på `test_phase15_16_estimat_and_duplicate_block.py` (regression).
- ✅ Live API som ILK logistics_admin: `GET /api/tours?tour_type=estimat` returnerer nu `estimated_count`, `customer_name`, `plads`, `created_by_name` på alle estimater.
- ✅ Live UI screenshot: tabellen viser "Tegl × 5 — Blishøj 1 — Helsingør Forsyning — Boliggården Location Admin" på 20. juni 2026 med I dag-filter aktivt.


---

## Fase 15.18 — Estimat-visning på Mine bestillinger (2026-02-21)

### Brugerkrav
1. På "Mine bestillinger" må Estimat-bestillinger IKKE vise: "Opgavetype", "Afhentes", "Status" (Afventer/Taget/På vej/Fuldført), "Container-nr. ikke angivet".
2. Estimat skal kun vise: Adresse, Materiale, Kommentar (kun hvis udfyldt af bruger), Antal containere estimeret, Bestilt kl., Bestilt af.
3. Antal containere skal IKKE landere i kommentar-feltet — det skal være et selvstændigt felt. Kommentar = kun brugerens egen tekst.
4. Tilpasset bestilling (både Estimat og Tilpasset Opgave) skal have synlig visuel markering (badge + farve).

### Implementering

**Backend (`/app/backend/server.py`):**
- `ContainerOrder`-modellen udvidet med `estimated_count: int = 0`.
- `submit_customer_order`: `doc["estimated_count"] = int(order.estimated_count or 0)` sættes for estimat-ordrer FØR `container_orders.insert_one(doc)`. Samme felt fortsat på `tours`.
- Engangs-DB-cleanup kørt: alle `container_orders` (og `tours`) med tour_type='estimat' og comment-regex `^Estimat\s*[—\-]\s*\d+` blev ryddet (16 ordrer + 5 tours samlet). Backfilled `estimated_count` på 5 gamle estimat-ordrer ud fra parset comment-tekst.

**Frontend (`/app/frontend/src/App.js`):**
- `OrderForm.estimat-formular`: tilføjet `Kommentar (valgfri)`-textarea (testid `estimat-comment-input`). Submit-POST sender nu `comment: (comment || "").trim()` — INGEN auto-prefix.
- "Mine bestillinger"-kort: `isEstimat` + `isCustom`-flag styrer betinget rendering:
  - **Container-nr.-linjen** (incl. "Container-nr. ikke angivet"-fallback): kun !isEstimat
  - **Status-badge** ("Afventer"/"Taget"/"På vej"/"Fuldført"): kun !isEstimat
  - **OrderInfoLine** med Opgavetype + Afhentes: erstattet med kompakt "Bestilt kl. / Bestilt af"-linje for estimat
  - **Driver-info-blok** (Chauffør/Taget/Startet/Færdig): kun !isEstimat
  - **Hovedgrid**: For estimat vises kun Adresse, Antal containere estimeret (amber font-black, testid `estimat-order-count-{idx}`), Kommentar (kun hvis trimmet ikke-tom), Oprettet-tidspunkt. Almindelige ordrer beholder fulde grid (Opgavetype, Prioritet, CO2, Vægt etc.).
  - **Badges**: `Estimat` (amber bg, testid `order-badge-estimat-{idx}`) eller `Tilpasset` (purple bg, testid `order-badge-custom-{idx}`).
  - **Kort-baggrund**: amber-950/30 + amber-ring for estimat; purple-950/20 + purple-ring for tilpasset opgave; slate-800 default.

### Verificeret (iter_40)
- ✅ Backend pytest 6/6 GREEN: `test_phase15_16_estimat_and_duplicate_block.py` (3 tests, regression) + ny `test_phase15_18_estimat_my_orders.py` (3 tests).
- ✅ Code-review af App.js bekræfter alle 5 UI-krav implementeret korrekt med data-testids.
- ✅ Live API-verificeret: estimat med `comment=""` gemmes som tom; estimat med `comment="Test"` gemmes uden auto-prefix; `estimated_count` propageres til både container_orders og tours.
- ✅ DB-cleanup verificeret: 0 estimat-ordrer har tilbageværende auto-comment.

---

## Fase 15.19 — Estimat-isolation + Filtrér-popover (2026-02-21)

### Brugerkrav
1. Estimat-bestillinger må KUN eksistere ét sted i systemet: under "Planlæg ressourcer" på logistics_admin-siden. De må IKKE optræde i: "Ikke-tildelte bestillinger", driver views (HASTER/Mine ture/Ledige ture/Ture hos andre chauffører/lokationsvisning), eller andre tour-lister.
2. Fjern "Tur-nr."-kolonnen fra Planlæg ressourcer-tabellen.
3. Tilføj kompakt filtrering på "Ikke-tildelte bestillinger" (Materiale, Opgavetype, Prioritet + eksisterende Kunde/Lokation) — pladsbesparende.

### Implementering

**Backend (`/app/backend/server.py`):**
- `get_tours` har nu default-eksklusion: hvis caller IKKE eksplicit passer `tour_type`, sættes `query["tour_type"] = {"$ne": "estimat"}`. Explicit `?tour_type=estimat` virker stadig (bruges af Planlæg ressourcer). `?tour_type=all` springer filteret over (escape hatch til rapporter).

**Frontend (`/app/frontend/src/App.js`):**
- `visibleTours` (driver) får defense-in-depth filter: `.filter(t => (t.tour_type || "") !== "estimat")`.
- `allUnclaimed` (admin planning) filtrerer estimater fra på client-side.
- Planlæg ressourcer-tabel: "Tur-nr."-kolonne fjernet. Tilbageværende kolonner: Dato · Materiale · Antal · Lokation · Kunde · Bestilt af.
- "Ikke-tildelte bestillinger"-header: ny "Filtrér"-knap (lucide `Filter`-ikon) der toggler et popover-panel. Aktiv filter-tæller vises som lille badge på knappen. Popover indeholder 5 selects: Kunde / Lokation / Materiale / Opgavetype / Prioritet med data-testids `planning-filter-{customer,plads,material,tour-type,priority}`. "Nulstil alle"-knap kun synlig når et filter er aktivt.

### Verificeret (iter_41)
- ✅ Backend pytest 10/10 GREEN: 4 nye `test_phase15_19_estimat_isolation.py` + 3 Phase 15.16 + 3 Phase 15.18 regression.
- ✅ Live API som ILK admin: `/api/tours` returnerer 7 tours (0 estimater); `/api/tours?tour_type=estimat` returnerer 6 estimater.
- ✅ Frontend admin UI: Filtrér-popover åbner med alle 5 selects + active-count badge. Planlæg ressourcer-tabel viser præcis 6 kolonner uden Tur-nr.
- ✅ Backend driver-isolation: testdriver@default.local får 0 estimater via GET /api/tours.


---

## Fase 15.20 — Bestillingsdato + Inkludér estimater toggle + Estimat-edit (2026-02-21)

### Brugerkrav
1. Omdøb "Afhentes" → "Bestillingsdato" i `OrderInfoLine` (samme datakilde `order_date`, kun ny label). Fjern det tidligere "Bestilt"/"Bestilt kl."-felt (created_at) fra linjen. `created_at` vises stadig andre steder ("Oprettet:"-stamp nederst på kortet) — det røres IKKE.
2. Tilføj "Inkludér estimater"-toggle på "Mine bestillinger" + "Alle bestillinger (denne lokation)". Default OFF (estimater skjult); ON → estimater vises NEDERST i listen.
3. Edit-modal på estimat-ordrer skal kun vise 4 felter: Materiale, Antal containere estimeret, Bestillingsdato, Kommentar. Ingen Prioritet/Opgavetype/Leveringsadresse/Værksted.

### Implementering

**Frontend (`/app/frontend/src/App.js`):**
- `OrderInfoLine` (line ~204): "Bestilt"-blok (created_at) fjernet helt. "Afhentes"-blok omdøbt til "Bestillingsdato" (samme `order_date`-source, samme Calendar-ikon).
- Estimat-kort: kompakt "Bestillingsdato"-line erstatter den tidligere "Bestilt kl."-line. Bunden af kortet beholder uændret "Oprettet:"-stamp (created_at).
- `visibleHistory` (line ~1207): splittes nu i `estimates` og `nonEstimates`. Default returneres kun `nonEstimates`; toggle ON sorterer `nonEstimates` først (status-ranked) og `estimates` (order_date desc) bagefter — concat'es.
- "Inkludér estimater"-toggle (custom switch, role=switch, aria-checked) i toolbaren over listen. Active-badge "Vises nederst" vises kun når toggle ON.
- `OrderEditModal` (line ~3206): `isEstimat`-flag styrer betinget rendering. For estimat vises 4 felter (`edit-estimat-material`, `edit-estimat-count`, `edit-estimat-date`, `edit-estimat-comment`); resten af modalen renderes ikke. `_doSave`-funktion har egen kortsluttet estimat-flow med PUT-payload `{material, estimated_count, order_date, comment}` + validering.
- Planlæg ressourcer-tabel: kolonne-header "Dato" → "Bestillingsdato".

**Backend (`/app/backend/server.py`):**
- `EDITABLE_ORDER_FIELDS` (line ~12362): `material` + `estimated_count` tilføjet.
- `PUT /api/customer-orders/{id}` (line ~12446): tour_update spejler `material` → `fraction` og `estimated_count` → `estimated_count` (int-coerced) på den linkede tour. Audit log bevares uændret.

### Verificeret (iter_42)
- ✅ Backend pytest 12/12 GREEN: 10 eksisterende + 2 nye `test_phase15_20_estimat_edit.py`.
- ✅ Backend live API: PUT /api/customer-orders/{estimat_id} med `{material:'Beton', estimated_count:12, order_date:'2026-07-15', comment:'Test'}` opdaterer container_orders OG tours korrekt.
- ✅ Frontend live screenshot: "Inkludér estimater"-toggle default OFF (6 bestillinger vist, 0 estimat-badges); klik toggle → "Vises nederst"-badge dukker op, antal stiger til 7 og estimat-badge vises. "Bestillingsdato 20.06" vises som ÉT datofelt; "Oprettet: 20.6.2026, 12:53:06" stadig nederst.
- ⚠️ Carry-over: test_credentials drift (ILK admin + Boliggården password hashes blev resat under testing-agent-run for at låse op).


---

## Fase 15.21 — UI-oprydning på Logistics Admin (2026-02-21)

### Brugerkrav
1. Fjern "Hurtigt overblik"-blokken fra 5 tabs: Manuelle ture, Chauffører, Genbrugspladser, Priser & Rapport, Indstillinger. Behold på Planlægning.
2. Fjern "Tildeling er flyttet"-advarselsbanner helt fra Manuelle ture.
3. Fjern den indledende sætning "Pladser oprettes ikke længere her" fra Genbrugspladser-infoboksen. Behold resten af teksten (med småjustering: "adressen, GPS..." → "noget skal opdateres").

### Implementering

**Frontend (`/app/frontend/src/App.js`):**
- Quick Stats-blokken (line ~7311): conditional ændret fra `activeTab !== "overview" && !== "archives" && !== "statistics"` (negativ liste) til `activeTab === "schedule"` (kun positiv). Resultat: vises kun under Planlægning.
- Manuelle ture (line ~7368): hele `tours-assignment-notice`-banner-div fjernet. Sektionen starter nu direkte med Filter-controls.
- Genbrugspladser (line ~9172): første `<p className="font-semibold">📍 Pladser oprettes...</p>` slettet. Anden `<p>`-blok beholdt med opdateret slutsætning ("kontakt kunde-admin hvis noget skal opdateres").

### Verificeret
- ✅ grep-check: `Tildeling er flyttet` har 0 refs i App.js. `Pladser oprettes ikke længere` har 0 refs.
- ✅ `Hurtigt overblik` findes nu kun ÉT sted (inde i `activeTab === "schedule"`-blokken).
- ✅ Live screenshot af Manuelle ture (logget ind som ILK admin): siden starter direkte med "Filtre"-boks → "Vælg Genbrugsplads"-tabel. Ingen "Hurtigt overblik" h2, ingen "Tildeling er flyttet"-banner.


---

## Fase 15.22 — Arkiv: År-gruppering (2026-02-21)

### Brugerkrav
På Logistics Admin → Arkiv (Dagrapporter PDF) skal månederne grupperes pr. ÅR så listen ikke vokser uendeligt. Nuværende år vist åbent; tidligere år kollapsede (klik på årstal for at se).

### Implementering

**Frontend (`/app/frontend/src/App.js`):**
- Eksisterende `monthKeys` (sorteret desc) grupperes nu efter år via regex `/^(\d{4})/` mod `cycleKey`-prefixet. `yearGroups[yr]` indeholder array af mkeys for det år.
- Aggregeret `yearTotals[yr]` (completed, minutes, days, weight) beregnes på tværs af årets perioder så års-headeren viser samlet status.
- Ny ydre `<details>`-wrapping per år (`data-testid="archive-year-{yr}"`). `open={isCurrent}` styrer at nuværende år starter foldet ud og tidligere år foldet ind. "NUVÆRENDE"-badge på dette års header.
- Indre måneds-`<details>` beholder samme adfærd (åben/lukket pr. mkey), nu indrykket inde i års-wrapperen.

### Verificeret
- ✅ Live screenshot (ILK admin → Arkiv): "2026 · NUVÆRENDE · 2 perioder" som ydre header med aggregerede badges (11 contai., 39t 45m, 4 dage, 258 548 kg). Juli/Juni 2026 vises som indre detalje-blokke med CSV/ZIP-knapper og chauffør-tabeller.
- ✅ Når der senere kommer 2025-data, vises 2025 som kollapset year-block under 2026.


---

## Fase 15.23 — Fjern HASTER in-app toasts på chauffør-siden (2026-02-21)

### Brugerkrav
Fjern system-toast/popup på chaufførsiden der advarer om hasteture. Ingen in-system notifikationer.

### Implementering

**Frontend (`/app/frontend/src/App.js`):**
- `fetchTours`-callback (line ~12770): hele HASTER-detection-blokken fjernet. `toast.error("🚨 HASTER...")`, `new Notification(...)` og `navigator.vibrate(...)` er væk. `lastKnownHasterRef`-state ryddes stadig så fremtidige genaktiveringer ikke bumser ved gen-tilføjelse.
- Driver-session useEffect (line ~12885): `Notification.requestPermission()`-prompt fjernet — chauffører får ikke længere "🔔 Notifikationer aktiveret"-toast eller browser-permission-prompt.

### Hvad bevares
- Visuelle HASTER-chips på tour-kort (rød `priority='urgent'`-badge) — det forbliver helt uændret.
- Server-side web-push (`POST /api/push/send`) ved nye haster-ture er bevaret (det er extern OS-baseret notifikation, ikke en in-app toast). Hvis du også vil have den fjernet, sig til.

### Verificeret
- ✅ grep-check: 0 in-app `toast.*HASTER`-referencer i App.js.
- ✅ `Notification.requestPermission()`-prompt fjernet.
- ✅ Frontend lint: ingen nye fejl introduceret.


---

## Fase 15.23b — Fjern web-push helt på chauffør-flowet (2026-02-21)

### Brugerkrav
Slå OS-niveau web-push notifikationer helt fra på chauffør-siden — chauffører skal udelukkende få info via app-UI'et.

### Implementering

**Frontend (`/app/frontend/src/App.js`):**
- `subscribeToPush` (line ~12609) erstattet: kalder ikke længere `POST /api/push/subscribe`. I stedet forsøger den at AF-abonnere på enhver eksisterende `pushManager.getSubscription()` så browsers ikke længere modtager push.
- HASTER-web-push i admin's bulk-tour-add (line ~5683) fjernet — `axios.post(`${API}/push/send`, ...)`-kald er væk.
- Web-push i admin chat-besked (line ~6024) fjernet — chat-beskeder ankommer kun via in-app chat-UI.

**Backend:** Push-endpoints (`/api/push/subscribe`, `/api/push/send`) er bevaret men ikke længere kaldt fra noget UI-flow. DB-tjek viser ingen aktive subscriptions at rydde.

### Verificeret
- ✅ grep-check: 0 referencer til `push/send` eller `push/subscribe` i App.js.
- ✅ Eksisterende push-subscriptions: 0 (alle collections tomme).
- ✅ Chauffør modtager nu UDELUKKENDE informationer via app-UI'et — ingen browser/OS-notifikationer.


---

## Fase 15.24 — HASTER-sektion isolation i "Mine ture" + pulserende ring (2026-02-21)

### Brugerkrav
1. På chauffør-siden, i den globale "Mine ture"-dropdown-option: HASTER-sektionen må KUN vise hasteture der er tildelt eller taget af login-chaufføren. Ledige hasteture og hasteture hos andre chauffører må IKKE vises. Lokationssider er uændrede.
2. "Tildelt/taget af mig" inkluderer BÅDE admin pre-tildelt (`driver_id === myId`) OG aktivt taget (`claimed_by_id/claimed_by` matcher mig).
3. Pulserende ring på aktive hasteture (visuel forstærkning af HASTER-chippet).

### Implementering

**Frontend (`/app/frontend/src/App.js`):**
- `classifyTour` (line ~15969): ny `isMineViewGlobal`-flag (true når `selectedPlads === "__MINE__"`). Når true klassificeres en haster KUN som "haster" hvis turen er mine (`mine === true`). Ellers falder den gennem til normal "mine"/"fri"-klassifikation — og fanges af upstream `_isMineTour`-filteret som strict allerede ekskluderer non-mine ture i `__MINE__`-visningen. Sammen giver det belt-and-suspenders-isolation.
- TourCard root-div (line ~4088): tilføjet conditional `ring-2 ring-red-500 animate-haster-pulse` className når `isHaster && !tour.completed && !tour.on_way`. På-vej hasteture beholder deres orange stil uden konkurrerende rød ring; afsluttede hasteture viser ingen pulse.

**CSS (`/app/frontend/src/index.css`):**
- Nyt `@keyframes haster-pulse`-keyframe: 0%/100% solid rød box-shadow, 50% udflydende fade → smooth pulse hver 1.8s med `cubic-bezier(0.4, 0, 0.6, 1)` easing.
- `.animate-haster-pulse`-klassen bruger keyframet med `infinite` looping.

### Hvad bevares uændret
- Lokationssider (fx Blishøj 1): HASTER-sektion viser fortsat ALLE hasteture på pladsen, uanset tildeling.
- Ture hos andre chauffører-sektion: kommer fortsat i sin egen read-only collapsible.
- Visuelt design af HASTER-sektion-headeren: rød ramme, AlertTriangle-ikon, count-badge — uændret.

### Verificeret
- ✅ Code review: classifyTour respekterer kun-mine-haster-regel i `__MINE__`-visning; `_isMineTour` upstream-filter sikrer kun mine tours overhovedet når sektioneringen.
- ✅ CSS-keyframe tilføjet i index.css.
- ✅ Login som testdriver bekræftet på preview URL.


---

## Fase 15.25 — HASTER-matrix (Mine vs ikke-mine) + badge-pulse (2026-02-21)

### Brugerkrav (visning-matrix)
| Side / Tur-status | HASTER knyttet til mig | HASTER IKKE knyttet til mig |
|---|---|---|
| **Global "Mine ture"** | Vises i "Mine ture"-sektionen (ÉN samlet sektion, øverst) | Vises slet ikke |
| **Lokationsside (Blishøj 1)** | Vises i "Mine ture"-sektionen (øverst) | Vises i "Hasteture"-sektionen (uændret) |

Pulserende rød ring rundt om HASTER-badge (ikke hele kortet).

### Implementering

**Frontend (`/app/frontend/src/App.js`):**
- `classifyTour` (line ~15969) opdateret med matrix-logik:
  - `mine === true` → "mine" (uanset urgent — også mine HASTERS lander her)
  - `mine === false && isUrgent === true` →
    - global "Mine ture": "fri" (filtreres væk upstream af `_isMineTour`)
    - lokationsside: "haster"
  - Andet → "fri"
- `sortedTours` (line ~13995) sorterer ALLEREDE urgent først → mine HASTERS placeres automatisk ØVERST inden for "Mine ture"-sektionen via gennemstrømnings-rækkefølgen i `mainTours`.
- TourCard root-div: pulse fjernet (ring rundt om hele kortet var for invasivt).
- HASTER-badge `<span>` (line ~4286-4292): conditional `ring-2 ring-red-400 animate-haster-pulse` påsat når `isHaster && !completed && !on_way`. Kun selve badget får ringen — kortet forbliver ellers normalt.

**CSS:** `@keyframes haster-pulse` allerede oprettet i Fase 15.24, genbruges.

### Hvad bevares uændret
- Lokationssidernes "Hasteture"-sektion: viser fortsat ledige hasteture (uændret).
- "Ture hos andre chauffører"-sektion: read-only, kun på lokationssider, uændret.
- Sektionsoverskrift "Mine ture (n)" beholdes i global "Mine ture"-visning (bruger valgte (b) — visuel konsistens).

### Verificeret
- ✅ grep-check: `animate-haster-pulse` påsat KUN HASTER-badge (linje 4286), ikke længere på card root.
- ✅ Code review: matrix-logik korrekt mappet. mine hasters → "mine"-bucket; non-mine hasters → "haster"-bucket (kun lokation); ikke-urgent → "fri" eller "mine".
- ✅ Sortering: `sortedTours.sort` har urgent first (line ~13997) → mine HASTERS øverst i Mine ture-sektionen.


---

## Fase 15.26 — Sektions-header de-duplikering + case-insensitive HASTER + chip-pulse (2026-02-21)

### Brugerkrav
1. Hver sektion ("HASTER", "Mine ture", "Ledige ture") må kun have ÉN header der vises ÉN gang, efterfulgt af ALLE ture i sektionen.
2. Antallet i parentes skal matche det reelle antal ture under headeren.
3. Pulserende rød ring KUN på HASTER-chippet (ikke status-badget).

### Rod-årsag på header-duplikering
Det tidligere render-loop iterérede flade `mainTours` og emit'ede en header hver gang `classifyTour` skiftede. Da `sortedTours`-sorteringen interleaver kategorier (fx mine-haster → ledig-haster → mine-onway), endte loop'et med at re-emit "Mine ture (n)"-headeren flere gange.

### Implementering

**Frontend (`/app/frontend/src/App.js`):**
- Section-render-loop omskrevet (line ~16030): grupperer FØRST `mainTours` ind i `grouped = { haster: [], mine: [], fri: [] }`. Render dernæst sektionerne i fast rækkefølge `["haster", "mine", "fri"]` med ÉN header pr. sektion + ALLE dens ture. Tur-nummerering (`globalIdx`) er fortsat global så chaufføren ser 1, 2, 3, ... på tværs af sektioner.
- `isHaster` i TourCard (line ~4039) gjort case-insensitive: `priority.toLowerCase() === "haster"` så `"Haster"`-værdier også registreres.
- `classifyTour` (line ~15983) gjort case-insensitive på samme måde.
- Pulse-effekten flyttet fra status-badget (right-side) TIL priority-chippet i kortet (line ~4137): `(isHasterChip && !tour.completed) ? "ring-2 ring-red-400 animate-haster-pulse" : ""`. Pulse vises uanset om turen er VENTER eller PÅ VEJ (kun fjernet ved FÆRDIG).

### Verificeret
- ✅ Live screenshot på Blishøj 1-lokationsside som testdriver: "MINE TURE (2)" header vises ÉN gang. Pap (HASTER mine) + Beton (mine, on_way) listet under. "LEDIGE TURE (1)" separat sektion uden duplikat. Antal matcher.
- ✅ I tidligere screenshot var det "MINE TURE (3)", "MINE TURE (5)", "MINE TURE (5)" gentagne — nu reduceret til ÉT header pr. sektion.
- ✅ Case-insensitive isHaster ensures status-badget viser HASTER eller PÅ VEJ korrekt (tidligere viste VENTER for priority="Haster" tour).


---

## Fase 15.27 — Sektion-rækkefølge + forstærket HASTER-puls på mine ture (2026-02-21)

### Brugerkrav
1. **Sektion-rækkefølge på lokationssider**: Mine ture skal stå øverst, HASTER-sektion under (omvendt af tidligere).
2. **Forstærket puls på mine HASTER-ture**: når en HASTER-tur er Mine (uanset om det er global Mine ture eller lokationsside), skal kort-rammen + venstre kant pulsere kraftigere end den nuværende lille chip-puls. Ikke-mine HASTERS i HASTER-sektionen beholder den eksisterende lette puls.

### Implementering

**Frontend (`/app/frontend/src/App.js`):**
- Section-render-loop (line ~16030): `sectionOrder` ændret fra `["haster", "mine", "fri"]` til `["mine", "haster", "fri"]`. Ved hver sektion sendes nu `isMineSection` (true når `sec === "mine"`) til `renderSoloTour`.
- `renderSoloTour` (line ~16159): nyt 3. argument `isMineSection = false`. Case-insensitive `_soloIsHaster`-flag tilføjet. Beregner `showMineHasterPulse = _soloIsHaster && isMineSection && !completed`. Når true: `border-l-red-500 animate-haster-border-pulse` påsættes kort-rammen; ellers fallback til `statusStyle.border`.
- Priority-chip i renderSoloTour (line ~16247): pulse-class er nu kontekst-afhængig:
  - Mine HASTER: `animate-haster-pulse-strong` (større ring + glow + lille scale)
  - Ikke-mine HASTER: `animate-haster-pulse` (eksisterende let puls)

**CSS (`/app/frontend/src/index.css`):**
- `@keyframes haster-pulse-strong`: 1.2s puls med box-shadow expansion + `scale(1.04)` på 50%-keyframe → mere "alarmagtig" effekt.
- `@keyframes haster-border-pulse`: 1.5s puls på `border-left-color` + venstre side box-shadow (12px blur, rgba(239,68,68,0.55)) → kantstribet pulserer rødt-orange.

### Verificeret (live)
- ✅ Lokationsside Blishøj 1 som testdriver: sektion-rækkefølge MINE TURE (3) → Haster (1). Pap (mit HASTER) har border-pulse + strong chip-pulse. Ledig Haster i sektion 2 har standard light chip-pulse.
- ✅ 1 border pulse + 1 strong chip pulse + 1 light chip pulse på sider med 1 mit HASTER + 1 ledig HASTER.
- ✅ Mine ikke-HASTER ture (Beton, Indendørs Træ) viser standard orange PÅ VEJ-kant uden pulse.



---

## Fase 18.14 — Trin B: Mobile "Ture"-fane hero-block (2026-02-28)

### Brugerkrav
Færdiggør den mobile 3-tab refactor (Tid / Ture / Profil). Trin A (Tid + Profil overlays + bottom-nav) var allerede landed. Trin B introducerer et nyt visuelt header-block til "Ture"-fanen MED ZERO funktionsændring: Hero Card + Stat Cards + Progress Card + Mine ture/Lokationer switcher + hurtig søgning.

### Implementering
**Frontend (`/app/frontend/src/App.js`):**
- Nyt `md:hidden`-block indsat lige efter `</header>` (line ~17764). Vises kun når `activeTab === 'ture'`.
- Hero Card: gradient bg, scope-label ("MINE TURE" / "AKTIV LOKATION"), scope-navn, tur-tæller + samlet kg, settings-knap der åbner eksisterende `setToolbarExpanded(true)` for plads-/chauffør-redigering.
- 4 Stat Cards (grid-cols-4): I alt, På vej, Færdige, Afventer — alle beregnet fra eksisterende `filteredActive`, `filteredOnWay`, `filteredCompleted`, `filteredWaiting`.
- Progress Card: % færdige + orange→grøn progress bar når 100%.
- Switcher pill: "Mine ture" knap kalder `setSelectedPlads("__MINE__"); setMineSelectedPlads("")`. "Lokationer" knap kalder `setToolbarExpanded(true)` for plads-vælger.
- Hurtig søgning: input deler state med eksisterende `tourSearch` / `setTourSearch` — synkroniseret mellem hero og sticky toolbar.
- `min-h-screen`-wrapper fået `pb-20 md:pb-0` så bottom-nav ikke skjuler sidste tur.

### Verificeret
- ✅ Webpack compiled with only pre-existing warnings (ingen nye fejl).
- ✅ Live screenshot på mobile viewport (390×844) som driver "ferdal" på Ture-fanen:
   - Hero: "MINE TURE" / "Mine ture" / "7 ture · 104565 kg samlet"
   - Stats: 7 I alt, 1 På vej, 6 Færdige, 0 Afventer
   - Progress: 86% (orange bar med "6 ud af 7 ture er afsluttet")
   - Switcher og søge-input synlige og funktionelle
- ✅ ZERO logik-ændring — alle handlers (setSelectedPlads, setToolbarExpanded, setTourSearch) er eksisterende state-settere.
- ✅ Eksisterende sticky-controls + tour-list nedenfor rendrer uændret.

### Filer ændret
- `/app/frontend/src/App.js` (line ~17634 wrapper pb, line ~17764 nyt hero-block ~150 linjer)
- `/app/memory/test_credentials.md` (tilføjet driver `ferdalturan / Trinb2026!` til lokal test)


---

## Fase 18.15 — Trin B revideret efter brugerfeedback (2026-02-28)

### Brugerkrav
Bruger var utilfreds med initial Trin B-implementering:
1. "IND"-knap på Tid-tab var KLIKBAR på fremtidige datoer (skulle være restricted som desktop-version).
2. Ture-tab visuelt rod (mit hero-block + eksisterende internal hero ovenpå hinanden, duplicate UI).
3. "Rediger oplysninger" på Profil REDIRECTEDE til Ture-tab — skulle redigere inline på Profil.

### Implementering
**Frontend (`/app/frontend/src/App.js`):**

1. **Tid-tab punch-knapper låst til today** (line ~18060):
   - `disabled={isClockedIn || !isToday}` for IND.
   - `disabled={(!isClockedIn && !isOnPause) || !isToday}` for UD.
   - `disabled={!isToday}` for pause-knap.
   - Title-attribut: "Stempling kan kun ske på dags dato — skift dato til i dag" for alle.

2. **Ture-tab visuel rebuild** (line ~17774):
   - Erstattet hero-block med fuld design-match til brugerens screenshot:
     - Brand strip (logo + chauffør-navn + bell-knap)
     - Beskeder/Log ud knapper (genbruger `setShowChat`, `handleLogoutDriver`)
     - Stor grøn hero card: SVG-ring (radius 38, circumference 239), pct, "GOD DAG · {navn}", "{remaining} tur tilbage", badges {total} ture + vægt (kg/t auto-format), Næste-warning chip med AlertTriangle
     - 3 stat cards: Vægt (grøn, kg/t auto-format), Ture (X/Y), Timer (timer:min fra timeEntries)
     - Mine ture card: scope-navn + dato (dansk weekday) + "X aktiv" badge + grøn progress bar + "X af Y · pct%"
     - Søgning + Afventende-toggle (genbruger `tourSearch`, `setShowPendingInList`)
     - Mine ture/Lokation switcher (genbruger `setSelectedPlads`, `setToolbarExpanded`)
     - Optimer rute-knap (genbruger `handleOptimizeRoute`)
     - TUREOVERSIGT-header med tæller
   - Eksisterende mobile header inde i `<header>` (line 17712) får `${activeTab === 'ture' ? 'hidden' : ''}` så ingen duplikat.
   - Sticky controls (line 18425) får `${activeTab === 'ture' ? 'hidden md:block' : ''}`.
   - Driver-hero-card (line 19140), progress-bar (line 19209), Actions Bar (line 19268), driver-tour-search-wrap (line 19454) får alle samme klassebetingelse — duplikatet er væk på mobil-Ture.

3. **Profil-tab inline pickers** (line ~18311):
   - Ny `[profilPicker, setProfilPicker]` state (`'vehicle' | 'plads' | null`).
   - Vehicle-row + Plads-row åbner inline picker under rækken (intet redirect).
   - Vehicle picker scroller `vehiclesList`; Plads picker viser "Mine ture (alle pladser)" + `pladsList`.
   - Hver option har `Check`-ikon hvis valgt; klik kalder eksisterende `setVehicleReg` / `setSelectedPlads`.
   - "Rediger oplysninger"-knap toggler picker (åbner 'vehicle' default; lukker hvis åben). INGEN `setActiveTab('ture')`.

### Verificeret (live screenshots)
- ✅ Tid-tab på fremtidig dato (02 jul.): IND er disabled med tooltip "Stempling kan kun ske på dags dato".
- ✅ Ture-tab: Brand strip + Beskeder/Log ud + grøn hero "0% · GOD DAG · FERDAL · 1 tur tilbage · 1 ture · 732 kg" + Næste-warning + 3 stats (732 kg / 0/1 / 0:00) + Mine ture card med "1 aktiv" badge + Afventende toggle + switcher + TUREOVERSIGT. Ingen duplikat-hero nedenfor.
- ✅ Profil-tab: Klik på "Rediger oplysninger" → forbliver på Profil + viser inline vehicle picker. `[data-testid="profil-tab"]` til stede, `[data-testid="ture-tab-hero"]` IKKE til stede.
- ✅ Webpack kompilerede med kun pre-existing warnings (ingen nye fejl).

### Filer ændret
- `/app/frontend/src/App.js` (Tid punch-disabling, Ture-tab fuld rebuild, Profil inline pickers, hide duplicate sections på mobil-Ture).


---

## Fase 18.16 — Trin B finpudsning (2026-02-28)

### Brugerkrav (5 punkter)
1. Vogn-nummer ændring under "Rediger oplysninger" virkede ikke intuitivt (label tom — viste —).
2. Ture-sektionen: turene var stadig i det gamle dark-mode format.
3. Tid-sektionen: manuel håndtering af time events manglede (fandtes i tidligere version).
4. Pause-flow: skulle ikke vise "GENOPTAG"-mulighed — kun "Afslut pause" der automatisk laver "ind work" igen.
5. Webversionen: ændringer skulle også gælde på desktop, ikke kun mobil.

### Implementering (`/app/frontend/src/App.js`)

1. **Vehicle picker label fix** (line ~18338):
   - Label-funktion ændret fra `v.registration_number || v.vehicle_number || v.name || "—"` → `v.number || v.registration_number || v.vehicle_number || v.name || \`Vogn ${id6}\``.
   - DB-tjek bekræftede `vehicles`-collection bruger feltet `number` (fx "AB 12 345").
   - Picker har nu Truck-ikon ved hver option, større padding (12px), Check-ikon ved valgt, toast.success ved skift.

2. **Tour cards i nyt look** (line ~18086):
   - Eksisterende Tours Section (line 19356) skjules helt når `activeTab === 'ture' || 'tid' || 'profil'`.
   - Ny "ture-list-cards"-container rendrer `visibleTours` som rene hvide rækker: farvet status-dot (orange/grøn/rød/grå) + fraction (bold) + sub-info (plads · kunde · adresse · vægt) + status-badge (Færdig/På vej/Haster/Venter).
   - HASTER-rækker pulserer med rød ring-shadow + animation.
   - Tap på rækken kalder `setSelectedTourForPanel(tour)` → åbner eksisterende MobileTourPanel med fulde detaljer + alle actions (genbruger eksisterende handlers — claim, complete, edit, scan, delete, on_way).
   - Pause-rækker rendres med eget orange Pause-design.
   - Tom-state hvis ingen ture matcher; "Vis X færdiggjorte"-toggle hvis showCompletedDriver er false.

3. **Manuel tidsregistrering på Tid-tab** (line ~18255):
   - Ny knap "Dagens stempling · Manuel" tilføjet under pause-knappen.
   - Klik kalder `setShowTimeOverview(true)` — åbner eksisterende modal med "Tilføj manuel"-funktionalitet.

4. **Pause-flow simplificeret** (line ~18209):
   - Når `isOnPause === true`: IND/UD-knapperne SKJULES helt — kun pause-knappen vises (større, full-width).
   - Pause-knappens onClick er async: når isOnPause så `await handlePunch("ud")` (luk pause) → `await handlePunch("ind", { sliceType: "work" })` (auto-genstart arbejde). Brugeren ser ét klik = pause slut + arbejde genstartet.
   - Når isOnPause === false: vis IND/UD som før, pause-knap viser "Start pause".

5. **Desktop/web visibilitet**:
   - `md:hidden` fjernet fra: ny Ture overlay, Tid overlay, Profil overlay, og bottom-nav.
   - Ture overlay wrapper med `max-w-screen-md mx-auto` så den ikke strækkes på desktop.
   - Eksisterende UI-blokke (sticky-controls, app-header, driver-hero-card, progress-bar, Actions Bar, driver-tour-search-wrap, Tours Section) får alle: `${activeTab === 'ture' || 'tid' || 'profil' ? 'hidden' : ''}` — gemmes på BÅDE mobil og desktop når en ny tab er aktiv.
   - App-container wrapper: `pb-20` (uden md:pb-0) så bottom-nav ikke skjuler indhold på desktop.

### Verificeret
- ✅ Mobile (390×844): Brand strip + Beskeder/Log ud + grøn hero "0% · GOD DAG · FERDAL · 1 tur tilbage · 1 ture · 802 kg" + Næste-warning + 3 stats + Mine ture card med "1 aktiv" + Afventende + switcher + TUREOVERSIGT med kort tour-række (orange dot + "PAP" + "Blishøj 1 · Helsingør Forsyning · test · 802 kg" + "På vej" badge).
- ✅ Desktop (1280×800): Samme layout, centeret med max-w-screen-md. Bottom-nav synlig nederst. Tid-tab har den nye "DAGENS STEMPLING · MANUEL"-knap.
- ✅ Profil vehicle picker: vehiclesList vises korrekt med "AB 12 345"-labels (fra `v.number`).
- ✅ `mobile-bottom-nav` data-testid findes på desktop.
- ✅ Webpack compiled cleanly (kun pre-existing warnings).


---

## Fase 18.17 — Trin B finpudsning runde 2 (2026-02-28)

### Brugerkrav (5 punkter)
1. "Lokation"-knap på Ture-tab reagerede ikke ved klik (åbnede usynlig toolbar).
2. Tid-tab brugte UTC-dato → "i dag" var forkert omkring midnat CEST (brugeren på 30. juni, men IND-knap mente det var 29.).
3. "Dagens stempling · Manuel" + "Afslut dag" skulle samles i en dropdown / kebab-menu.
4. "Afslut dag" skulle TILLADE backdated, kun BLOKERE fremtidige datoer.
5. Desktop: knapper var alt for brede / lange og Ture-tab var snæver i midten — alt skulle ligne mere naturligt.

### Implementering (`/app/frontend/src/App.js`)
1. **Lokation inline picker** (line ~18042):
   - Ny `[turePladsPickerOpen, setTurePladsPickerOpen]` state.
   - "Lokation"-knap kalder nu `setTurePladsPickerOpen(v => !v)` i stedet for `setToolbarExpanded` (som var skjult).
   - Inline picker rendrer under switcher: "Mine ture (alle pladser)"-option + alle `pladsList`-items med Check-ikon ved valgt.
   - Picker lukker automatisk når en option vælges.

2. **Lokal dato i Tid-tab** (line ~18187):
   - Erstattet `new Date().toISOString().slice(0, 10)` med `getLocalDateStr()`.
   - Ny `isFutureDate = reportDate > todayStr` til brug i Afslut dag-disabling.

3. **Tid dropdown-menu** (line ~18377):
   - Ny `[tidMenuOpen, setTidMenuOpen]` state.
   - Erstattet to separate "Manuel" + "Afslut dag" knapper med en enkelt "Flere handlinger"-knap (MoreVertical-ikon).
   - Klik åbner panel med to options som menu-rækker: "Dagens stempling · Manuel" (Calendar-ikon, grøn) + "Afslut dag" (CheckCircle2-ikon, rød).
   - Hver option har titel + undertekst + ChevronRight.

4. **Afslut dag backdated** (samme blok):
   - `disabled={isEndingShift || isFutureDate}` — kun blokerer fremtid.
   - Undertekst: "Luk dagen — også bagudrettede" (eller "Ikke muligt for fremtidig dato" når blokeret).
   - Backend har ingen date-restriction så backdated punch-out + PDF-generering virker uændret.

5. **Desktop layout-justeringer**:
   - Tid-overlay: indhold wrapped i `<div className="max-w-md mx-auto">`.
   - Profil-overlay: indhold wrapped i `<div className="max-w-md mx-auto">`.
   - Ture-overlay: container changed fra `max-w-screen-md` til `max-w-3xl` (912px) — fylder mere uden at strækkes overbredt.

### Verificeret (desktop 1280×800)
- ✅ Ture-tab: Klik "Lokation" → inline picker viser "Mine ture (alle pladser)" + "Blishøj 1" + Check-ikoner. Naturlig bredde.
- ✅ Tid-tab: Viser "30 jun." (i dag korrekt på lokal tid). "Stemplet ind kl. 00:30" beregnes korrekt.
- ✅ Tid dropdown: "FLERE HANDLINGER"-knap → åbner panel med "DAGENS STEMPLING · MANUEL" + "AFSLUT DAG · Ikke muligt for fremtidig dato"-rækker.
- ✅ Profil-tab: Centeret med max-w-md, knapper ser naturlige ud.
- ✅ Webpack compiled with 1 warning (pre-existing).

### Filer ændret
- `/app/frontend/src/App.js` (5 strategiske patches — picker state, dato-fix, dropdown menu, Afslut dag rules, max-w wrappers).


---

## Fase 18.18 — Trin B fuldførelse (2026-02-28)

### Brugerkrav (3 punkter)
1. Tilføj ALLE detaljer pr. tur i nyt design (opgavetype, kapacitet, prioritet, kunde, bestillingsdato, kvitteringer, container-nr, etc.).
2. Fjern "Beskeder"-knap under Ture (bell-ikon øverst dækker det).
3. Tilføj dato-navigation (frem/tilbage + dato-input) — manglede fra forrige version, vigtigt for at se "Afventende" på specifikke datoer.

### Implementering (`/app/frontend/src/App.js`)

1. **Fulde tur-detaljer via MobileTourCard** (line ~18145):
   - Erstattede mine simple rene rækker med eksisterende `<MobileTourCard>` komponent.
   - Wrappet i mørk `#0f172a` container med rounded border for at matche dark-mode kortets visuelle stil.
   - Genbruger alle handlers (`handleUpdateTour`, `handleDeleteTour`, `handleToggleOnWay`, `handleToggleComplete`, `setSelectedTourForPanel`).
   - Live verificeret: kort viser nu fraction (PAP), adresse, opgavetype (Afhent container), prioritet (Normal), kunde (Helsingør Forsyning), bestillingsdato, oprettelses-info, bestilt-af, tid (00:39), kundeordre-link, "Åbn kort"-link, status-badge (PÅ VEJ), action-knap.

2. **Beskeder-knap fjernet** (line ~17855):
   - Erstattet to-kolonners "Beskeder + Log ud" række med ny 4-kolonners "dato-prev + dato-input + dato-next + Log ud" række.
   - Bell-ikonet i brand-strip har allerede chat-funktion via samme `setShowChat(true)` + unread-badge.

3. **Dato-navigation** (line ~17855):
   - 3 nye elementer: ChevronLeft-knap (`navigateDate(-1)`), `<input type="date">` bundet til `reportDate`/`setReportDate`, ChevronRight-knap (`navigateDate(1)`).
   - Knapper har 44px bredde, dato-input fleksibel midte, Log ud-knap til højre.
   - Genbruger eksisterende `navigateDate`-funktion så date-skifte trigger samme reload-logik (loadTours, timeEntries, etc.) som forrige version.

### Verificeret (mobile 390×844)
- ✅ Date input vises og kan navigeres med Chevron-knapper. Navigerede til 30. juni 2026 → viste "Tirsdag Den 30. Juni 2026".
- ✅ MobileTourCard rendres med alle detaljer: PAP-fraction, "Afhent container", "Normal"-prioritet, "Helsingør Forsyning"-chip, "Bestillingsdato 30.06", "Oprettet den 29.06 09.33", "af Helsingør Forsyning Boliggårde...", "00:39 →" tid, "Kundeordre fra Blishøj 1" link, "Åbn kort", PÅ VEJ status-badge, orange action-circle.
- ✅ Beskeder-knap fjernet — bell-ikon i brand-strip (top højre) erstatter den med pulsende rød badge ved ulæste.
- ✅ Afventende-toggle synlig og funktionel — viser orange outline når aktiv.
- ✅ Webpack compiled with 1 warning (pre-existing).

### Filer ændret
- `/app/frontend/src/App.js` (Beskeder erstattet med dato-row, MobileTourCard erstatter simple rækker).


---

## Fase 18.19 — Location Admin Rapportering scroll-loop fix (2026-02-28)

### Bugrapport
Brugeren rapporterede at Rapportering-fanen på Location Admin re-loader/scroll-skubber omkring hvert 5. sekund, hvilket gør det umuligt at scrolle ned. Symptom: "scroller og stopper hver 5 sekund... når man scroller bliver det værre". Sker hele tiden uden interaktion.

### Root cause
Forælder-komponentens `allCodes` og `effectiveCodes` arrays blev recomputed på hver render → ny reference hver gang. Disse blev sendt som `locationCodes`-prop til `<ReportsSection>`, hvis `useCallback fetchData` havde `locationCodes` som dependency → fetchData blev recreated hver render → `useEffect(() => fetchData(), [fetchData])` triggerede ny fetch → setData → re-render → ny array reference fra parent → infinite loop med synlige scroll-jumps når Recharts re-renderede.

### Implementering (`/app/frontend/src/pages/LocationAdminPage.jsx`)
1. **Memoize `allCodes`** (line ~3079): Wrapped i `useMemo(..., [locations])` så array-referencen er stabil mellem renders.
2. **Memoize `effectiveCodes`** (line ~3097): Bruger join("|")-streng som stabil deps-nøgle. Wrapped i `useMemo` så reference kun ændres når INDHOLDET faktisk ændres.
3. **Stabil fetchData deps** (line ~3265): `useCallback`-deps ændret fra `[locationCodes, ...]` til `[locationCodes.slice().sort().join("|"), period, start, end]` — primitiv string-sammenligning forhindrer cyklus-fetches selv hvis forælder sender en ny array-reference.

### Verificeret
- ✅ Webpack compiled cleanly (kun pre-existing warnings).
- Forventet effekt: ReportsSection fetcher kun data når brugeren faktisk skifter lokation, periode eller datointerval — ikke ved hver render-cyklus.

### Filer ændret
- `/app/frontend/src/pages/LocationAdminPage.jsx` (3 strategiske useMemo + dep-stabilisering).


---

## Fase 18.20 — Location Admin tab-restrukturering (2026-02-28)

### Brugerkrav
1. Omorganisér primære faner i præcis denne rækkefølge: Bestillinger → Medarbejdere → Åbnings- og lukketidspunkter → Arkiv → Rapportering.
2. Saml sekundære faner i en "Mere"-dropdown: Kapacitetsmål, Leveringsadresser, Modtagne delta'er, Logistik-partnere, Slet permanent.

### Implementering (`/app/frontend/src/pages/LocationAdminPage.jsx`)
- `TABS` array opdateret med ny rækkefølge (Bestillinger først).
- Nyt `MORE_TABS` array for sekundære faner.
- Ny `[moreOpen, setMoreOpen]` state + `moreRef` til click-outside detektering.
- "Mere"-knap med `MoreHorizontal`-ikon + `ChevronDown`-pil; viser aktiv sekundær fane som label hvis valgt (fx "Mere → Kapacitetsmål").
- Dropdown menu: hvid bg, shadow, rounded; hver option har ikon + label + Check ved aktiv.
- Klik udenfor dropdown lukker den (`mousedown`-listener på document).
- `data-testid="ladmin-tab-more"` + `data-testid="ladmin-tab-more-menu"` for testing.
- Eksisterende `data-testid={ladmin-tab-${id}}` bevaret for ALLE faner (også dem i Mere) — tests skal stadig kunne finde dem.

### Verificeret
- ✅ Webpack compiled cleanly med kun pre-existing warnings.
- Rendering-logik (tab-state, content-rendering) er uændret — kun navigationen er reorganiseret.


---

## Fase 18.21 — Location Admin "Mere"-dropdown clipping fix (2026-02-28)

### Bugrapport
Brugeren rapporterede at "Mere"-dropdown viste listen mærkeligt og "sad fast" — scrolling var helt forkert. Selve panelet sad inde i fane-rækkens `overflow-x-auto`-container, hvilket klippede dropdown'en både horisontalt og vertikalt.

### Root cause
Dropdown var `position: absolute` indeni en `overflow-x-auto`-flex-container → blev klippet ved containerens border.

### Fix (`/app/frontend/src/pages/LocationAdminPage.jsx`)
1. Importerede `createPortal` fra `react-dom`.
2. Flyttede dropdown UD af header-DOM-træet og rendrer den via `createPortal(..., document.body)` så ingen forælder kan klippe den.
3. Position: `position: fixed` med beregnet `top/right` fra knappens `getBoundingClientRect()`.
4. Position opdateres live ved `resize` + `scroll` event listeners så menuen følger knappen.
5. Separat `moreMenuRef` så click-outside-detektering virker korrekt mellem knap og portal-menu.
6. Bedre styling: `shadow-2xl`, py-3 på items, ikon med flex-shrink-0, label med truncate, max-width 320px.

### Verificeret
- ✅ Webpack compiled cleanly.
- Dropdown rendres nu fri af overflow-clippet, fastgjort til knappens position, og lukker korrekt ved klik udenfor.


---

## Fase 18.22 — Bestillingsside kompakt design (2026-02-28)

### Brugerkrav
1. Material/container-kasser for store → under halv størrelse.
2. "Søg materiale"-felt for langt.
3. "Ny bestilling" / "Mine bestillinger"-knapper for lange.
4. "Mine bestillinger"/"Alle bestillinger"-historik for store → mere elegant og mindre.
5. Skal også virke godt på mobil.

### Implementering (`/app/frontend/src/App.js`)
- **Tabs** (line ~1994): `flex-1 py-2 text-sm` → `inline-flex px-3 py-1.5 text-xs`. Knapperne tager nu kun deres naturlige bredde.
- **Materiale heading** (line ~2135): `text-2xl mb-1` → `text-lg sm:text-xl mb-0.5`, undertekst `text-xs`.
- **Materiale-søgning** (line ~2140): `w-full px-4 py-3 rounded-xl` → `w-full max-w-xs px-3 py-2 rounded-lg text-sm`.
- **Materiale-grid** (line ~2151): `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3` → `grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2`. Flere kort pr. række.
- **Materiale-card** (line ~2196): `p-4 border-2 rounded-xl` → `p-2.5 border rounded-lg`. Ikon `w-10 h-10` → `w-7 h-7`. Tekst `text-sm` → `text-xs`.
- **Container heading** (line ~2331): `text-2xl mb-1` → `text-lg sm:text-xl mb-0.5`, undertekst `text-xs`. Action-knapper `px-3 py-2 text-sm` → `px-2.5 py-1.5 text-xs`. Label "Tilføj tilpasset bestilling" → "Tilpasset bestilling".
- **Container-grid** (line ~2393): `grid-cols-2 sm:grid-cols-3 gap-3` → `grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-2`.
- **Container-card** (line ~2405): `p-4 border-2 rounded-2xl` → `p-2.5 border rounded-lg`. Ikon `w-12 h-12` → `w-8 h-8`. Heading `text-lg` → `text-sm` med truncate.
- **History-card** (line ~3543): `rounded-xl p-4` → `rounded-lg p-3`. Ikon `w-10 h-10` → `w-8 h-8`. Mb-3 → mb-2.

### Verificeret
- ✅ Webpack compiled cleanly.
- Grid'erne giver 2-6 kolonner afhængigt af viewport (mobile-first responsivt).
- Knapper tager kun deres naturlige bredde — ikke længere stretchet til hele linjen.


---

## Fase 18.23 — Bestillingsside elegant mellem-størrelse (2026-02-28)

### Brugerkrav (justering af forrige version)
1. Knapper "+ Ny bestilling" / "Mine bestillinger" føltes "gemt i hjørnet" — gør dem mere elegant og synlig.
2. Material/container-kasser var for små — find en passende mellem-størrelse.
3. Historik-bestillingsbokse stadig for store.
4. Skal ramme et indbydende look.

### Implementering (`/app/frontend/src/App.js`)
- **Tabs som segmented control**: Pille-form med inline-flex pad-1 + rounded-xl, mørk bg-slate-800/80 baggrund. Aktiv tab har orange bg + shadow-md med farveskygge. Hover: bg-slate-700/50. Større padding (px-5 py-2) + text-sm. Føles som en samlet "switcher" frem for to løse knapper.
- **Material-grid**: `grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3` — passende mellem-størrelse.
- **Material-card**: `p-3.5` padding, `w-10 h-10` ikon med gradient bg + ring, hover: translate-y-0.5 + shadow-lg orange-tint + border-orange-500/70. Tekst `text-sm`. Føles indbydende.
- **Search-felt**: Med Search-ikon præfix, `max-w-md`, `py-2.5`, focus-ring orange-500/20. Elegant og synlig.
- **Container heading**: text-xl/2xl, undertekst text-sm. Action-knapper med `px-3 py-2 shadow-sm hover:shadow-md`.
- **Container-grid**: `grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3`.
- **Container-card**: p-3.5, w-11 h-11 ikon med gradient, rounded-xl, hover lift + shadow.
- **Historik to-kolonners grid på desktop**: `grid-cols-1 lg:grid-cols-2 gap-3` — bedre brug af whitespace, kort vises ikke længere fuld bredde. Hver card: `p-3.5 rounded-xl`, status-ikon `w-9 h-9` med ring-1 farvet, hover: border-slate-600 + shadow-md.
- **Mikroanimationer**: `transition-all duration-150`, hover translate-y-0.5, shadow-grow på cards.

### Verificeret
- ✅ Webpack compiled cleanly.
- Tabs ser nu ud som et samlet segmented control. Cards har lift + shadow ved hover. Historik 2-kolonner på desktop, 1 på mobil.


---

## Fase 18.24 — "Mine bestillinger" → list-view med inline-expand (2026-02-28)

### Brugerkrav
Bestillingshistorik fremgår nu som en kompakt liste i stedet for store kort, så mange bestillinger kan overskues hurtigt. Klik på en række åbner inline-detaljer med ALLE informationer + actions. Funktionalitet uændret.

### Synlige felter i liste-rækken (i flg. brugerens ønsker)
1. **Status-ikon + materiale** (PAP, Pap, etc.)
2. **Container-nr** under material
3. **Opgavetype** (Afhent / Flyt / Til værksted / Værksted retur / Løs afhentning / Estimat)
4. **Prioritet** (Normal/Haster — rød tekst hvis Haster)
5. **Oprettet dato** (kort dansk format)
6. **Bestillingsdato** (kort dansk format)
7. **Status badge** (Afventer/Påbegyndt/På vej/Færdig/Estimat)
8. **ChevronDown** indikator (roterer ved expand)

### Implementering (`/app/frontend/src/App.js`)
- Ny `[expandedHistoryId, setExpandedHistoryId]` state.
- Ydre `<div className="grid lg:grid-cols-2 ...">` ændret til `<div className="rounded-xl border ... divide-y">` (samlet liste-container).
- Hver række: `<div className="transition-colors hover:bg-slate-800/50">` med en `<button>` der toggler `expandedHistoryId`.
- Knap-indhold: status-ikon (w-8), materiale + container-nr, opgavetype + prioritet (sm:+ skjult mobil), oprettet + bestilt datoer (md:+ skjult mobil/tablet), status-badge + chevron.
- Detail-view: ALLE de oprindelige kort-detaljer (chauffør, taget/startet/færdig tider, adresse, vægt, CO2, kommentar, Historik/Redigér/Annullér-knapper) er bevaret 1:1 — vises kun når isExpanded via `hidden`-klasse.
- Responsivt: alle 7 hovedfelter synlige på desktop, mobil viser kun material+container+status+chevron, tablet tilføjer opgavetype/prioritet.
- ZERO funktionsændring: `setEditingOrder`, `setConfirmDeleteOrder`, `setAuditOrder` virker uændret i expanded-view.

### Verificeret
- ✅ Webpack compiled cleanly (1 pre-existing warning).
- Eksisterende `data-testid="history-order-{idx}"` bevaret; ny `history-row-{idx}` på knappen og `history-expanded-{idx}` på detaljer.


---

## Fase 18.25 — Bestillingsside finpudsning runde 2 (2026-02-28)

### Brugerkrav (5 punkter)
1. Inline-expand → MODAL/POP-UP for bestilling-detaljer.
2. "Mine bestillinger" / "Alle bestillinger"-knapper for lange.
3. Dato-felt skulle ikke være centeret midt i skærmen.
4. "Inkludér estimater"-felt for stort.
5. "Tilføj nyt materiale"-kasse fremstod som et rigtigt materiale i grid'et.

### Implementering (`/app/frontend/src/App.js`)
1. **Modal popup**: Erstattet inline-expanded div med fixed-position backdrop + inner panel (max-w-2xl, max-h-90vh). Backdrop: `bg-black/70 backdrop-blur-sm`. Indre panel: bg-slate-900 rounded-2xl. Close-knap øverst til højre (XCircle). Klik på backdrop lukker også. Klik på indre panel stopPropagation så modalen forbliver åben.
2. **Mine/Alle som segmented control**: Erstattet `flex-1 px-3 py-2 text-sm` med kompakt pill-form: `inline-flex p-1 rounded-xl border` med indre `px-4 py-1.5 text-xs`. Aktiv: orange bg + shadow-sm. "Alle bestillinger (denne lokation)" → "Alle bestillinger".
3. **Dato venstre-justeret**: Erstattet `justify-between` (chevron-knapper i ydre ender + dato-input i centreret div) med `flex items-center gap-2` så alle elementer (prev-knap, dato-input, next-knap, weekday-label) ligger samlet venstre. Padding `p-1.5` på knapper, `px-2.5 py-1.5 text-sm` på input. Quick-knapper "I dag"/"I går" også reduceret til `px-3 py-1.5 text-xs`.
4. **Inkluder estimater kompakt**: Erstattet `flex justify-between px-4 py-2.5` med `inline-flex items-center gap-2 px-3 py-1.5` — toggle-switch `h-5 w-9` (var h-6 w-11). Tekst `text-xs` (var text-sm). Tager nu kun naturlig bredde i venstre side.
5. **Tilføj nyt materiale flyttet ud af grid**: Knap er nu i sin egen `<div className="mt-4 flex justify-end">` placeret EFTER materiale-grid'et. Styling: `inline-flex px-4 py-2 bg-emerald-500/15 border-emerald-500/40` med Plus-ikon. Klar visuel adskillelse fra materialer.

### Verificeret
- ✅ Webpack compiled cleanly (1 pre-existing warning).
- Modal er korrekt nested og responder på backdrop-klik + close-knap.
- Alle data-testid'er bevaret. Tilføjet: `history-modal-backdrop-${idx}` og `history-modal-close-${idx}`.
