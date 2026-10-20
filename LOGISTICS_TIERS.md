# Logistikfirmaer: Premium (option 1) og Partner (option 2)

Skrevet 2026-10-16, omskrevet 2026-10-18. Gælder KUN logistikfirmaer -
genbrugsplads-kunder (kundetype "kunde") er ikke berørt.

## Princippet (ny opdeling 2026-10-20 - se BESLUTNINGER_2026-10-19.md afsnit 11)

**Basic (partner, gratis)** er det, genbrugspladsen kræver, at logistikfirmaet
bruger: at køre kundens ture godt. Kunden betaler og inviterer sine
logistikfirmaer, så basic skal være enkelt og uden friktion.

**Premium** er logistikfirmaets egen drift - det, firmaet selv vælger at betale
for: "Kør hele firmaet i ContainerFlow".

| | Premium | Basic (partner) |
|---|---|---|
| Hvem betaler | Logistikfirmaet selv | Genbrugsplads-kunden (partneren får adgang gennem den) |
| Oprettes af super admin under | "Kunder & Logistik" (kundetype *Logistik (premium)*) | "Logistik-partnere" (biblioteket) |
| I databasen | `company_type = logistics`, `from_library` ≠ true | `company_type = logistics`, `from_library = true` |
| Skift type | Super admin: "Nedgradér" på firmakortet | Super admin: "Premium" i partnerlisten |
| Enkelte moduler | – | Super admin: "Moduler" i partnerlisten (`companies.premium_modules`) |

Skift af type beholder firma-id'et. Intet slettes ved nedgradering eller når et
modul fjernes - det skjules og kommer igen.

## Hvad gælder hvor

| Funktion | Basic | Premium |
|---|---|---|
| Bestillinger fra kundernes pladser, Dagsplan, Planlæg, Historik (med Excel-eksport som fakturagrundlag) | ✅ | ✅ |
| Bestil for kunden, annullering, faste tømninger fra kunden | ✅ | ✅ |
| Chauffører, vogne, hængere, chaufførappen, **beskeder** | ✅ | ✅ |
| Antal hængere, ventetid oplyst ved afslutning (står på turen) | ✅ | ✅ |
| Arkiv (dagrapporter, vejesedler), Indstillinger (afvigelseskoder, afslutning) | ✅ | ✅ |
| Team: invitér kolleger (fuld adgang) og disponent-telefon | ✅ | ✅ |
| "Kom godt i gang"-tjekliste i Ture | ✅ | – |
| **Økonomi**: prisaftaler, Rapport/fakturagrundlag med priser, godkendelser | modul | ✅ |
| **Tid & ressourcer**: stempling ind/ud, timer, lønperiode | modul | ✅ |
| **Rapportering** (statistik på tværs af kunder) | modul | ✅ |
| **Koordinatorroller** (rettigheder og kunde-afgrænsning pr. person) | modul | ✅ |
| Egne lokationer, egne ture, egne kunder, Fragt, hængere med indhold, flere stop, Gentag, krav ved afslutning | – | ✅ |

"Planlæg ressourcer" (kundernes estimater) vises også for basic, når kunden har
slået estimater/løs afhentning til - det er kundens behov.

Hvad der er lavet om, fordi tid og Økonomi ikke længere er i basic:
- Haster-besked: et firma uden tidsregistrering sender til alle aktive
  chauffører (før kun dem, der havde stemplet ind).
- Chaufførappen uden tidsregistrering åbner på Ture (ingen "Tid"-fane), og
  "Afslut dag" stempler ikke ud. "Afregning"-boksen vises kun med Økonomi.
- Ventetid ved afslutning står altid på turen (`waiting_reported_min`) og i
  Historik-eksporten; uden Økonomi oprettes ingen godkendelse.
- Historik-eksporten har tur-nr., haster, hængere, ventetid og afvigelse.
- Overgang: et basic-firma, der allerede brugte et modul, beholdt det som enkelt
  modul ved opdateringen (engangsrettelse `_migrate_premium_modules_grandfather`).

## Sådan er det bygget

- **Én liste:** `PREMIUM_CAPABILITIES` (+ `PREMIUM_MODULES`) i `backend/server.py`. `GET /api/logistics/profile` giver `{tier, is_premium, connected_customers, has_connections, capabilities, premium_modules}` til både admin og chauffør. `_company_has(cid, cap)` er den ene regel serveren bruger.
- **Serveren håndhæver det:**
  - `_PREMIUM_ROUTES`: middleware ligesom koordinator-rettighederne. Den svarer 403 med `premium_required` til en partner. GET af egne kunder svarer en tom liste.
  - `_normalize_tour_doc` (nye ture): en partner kan kun oprette ture på kunders pladser, og stop, Gentag, krav ved afslutning og kunderegister fjernes. Fragt og hængere er premium.
  - `update_tour`: premium-felter ignoreres for en partner.
  - Økonomi: `/pricing/options` viser kun tilknyttede kunder. `_check_rule_customers` afviser priser for egne kunder hos en partner (og kunder uden for en koordinators afgrænsning).
  - Pladslister: `_la_plads_query` viser ikke en partner egne lokationer (heller ikke efter en nedgradering).
- **Frontend:** `profile.capabilities` styrer Ny tur, tur-panelet og chaufførens "Tilføj et stop". `options.profile.tier` styrer Økonomi › Egne kunder.
- **Super admin:**
  - `GET` og `PUT /api/superadmin/companies/{id}/logistics-tier` til skift af type.
  - Dialogen viser, hvad der skjules.
- **Tests:** `backend/tests/e2e/flow_tiers.py` og `flow_security.py`.

## Når en ny funktion kun gælder option 1

Tilføj den til `PREMIUM_CAPABILITIES`. Håndhæv den på serveren, enten med en linje i `_PREMIUM_ROUTES` eller en feltregel. Skjul den i frontend med `profile.capabilities.<nøgle>`.

Funktioner, der afhænger af en genbrugsplads-kunde, skal tjekke `has_connections` og kun gælde den konkrete kundes data. Det gælder fx "Kundens kalender først" i Helligdage, "Kunders pladser" og Planlæg ressourcer (kundens funktionsflag).

## GPS på egne lokationer (2026-10-17)

GPS bruges som startpunkt for "Optimer rute" hos chaufføren (sortering efter afstand, km pr. tur).
- **Udfyldes automatisk:** når en lokation gemmes uden GPS, slås adressen op i OpenStreetMap (Nominatim, gratis, kun Danmark).
- **Fallback:** den indbyggede postnummer-tabel (omtrentlig: byens midte). Google Maps er slået fra.
- **Knapper:** "Find fra adressen" og "Vis på kort".
- **Begrænsning:** steder uden rigtig adresse (fx byggepladser) skal have koordinater skrevet ind manuelt.
