# Logistikfirmaer: Premium (option 1) og Partner (option 2)

Skrevet 2026-10-16, omskrevet 2026-10-18. Gælder KUN logistikfirmaer -
genbrugsplads-kunder (kundetype "kunde") er ikke berørt.

## Princippet

**Alt der gavner genbrugsplads-kunden, er med i kernen** (begge typer). Premium
er vognmandens egen forretning *uden for* genbrugspladserne. Genbrugspladsen
kan ikke købe en ekstra pakke til sin partner - der er intet at købe, fordi alt
der gavner den, allerede er med.

| | Option 1 - **Premium** | Option 2 - **Partner** |
|---|---|---|
| Hvem betaler | Logistikfirmaet selv | Genbrugsplads-kunden (partneren får adgang gennem den) |
| Oprettes af super admin under | "Kunder & Logistik" (kundetype *Logistik (premium)*) | "Logistik-partnere" (biblioteket) |
| I databasen | `company_type = logistics`, `from_library` ≠ true | `company_type = logistics`, `from_library = true` |
| Skift type | Super admin: "Nedgradér" på firmakortet | Super admin: "Premium" i partnerlisten |

Begge typer kan tilknyttes genbrugsplads-kunder (kunde admin › Logistik-partnere).
Skift af type beholder firma-id'et, så tilknytninger, chauffører og ture følger
med. Ved nedgradering **skjules** premium-data (egne lokationer, egne kunder,
nye egne ture) - intet slettes.

## Hvad gælder hvor

| Funktion | Partner | Premium |
|---|---|---|
| Bestillinger fra tilknyttede genbrugspladser, Dagsplan, Planlæg, Historik | ✅ | ✅ (når tilknyttet) |
| Ny tur og Excel-import på kundens plads (container) - bliver kundens tur | ✅ | ✅ |
| Chauffører, vogne, hængere (flåde), beskeder | ✅ | ✅ |
| Tidsregistrering, dagrapporter, lønperiode, Afslut dag | ✅ | ✅ |
| Rapportering, Arkiv (dagrapporter, vejesedler) | ✅ | ✅ |
| Økonomi for kundernes ture: prisaftaler, rapport/fakturagrundlag, godkendelser, helligdage | ✅ (kun tilknyttede kunder) | ✅ |
| Team & rettigheder | ✅ (afgrænsning: kun egne kunder) | ✅ (+ "egne ture og kunder") |
| Indstillinger inkl. afvigelseskoder og chaufførens afslutning | ✅ | ✅ |
| Chaufføren: hængerspørgsmål, ventetid, rettelser, afregningsform | ✅ | ✅ |
| **Egne lokationer** | – | ✅ |
| **Egne ture** (uden plads / på egen lokation), "Egne ture" hos chaufføren | – | ✅ |
| **Egne kunder** (kunderegister, firma-priser, "Egne ture uden kunde") | – | ✅ |
| **Fragt** (ikke-container) | – | ✅ |
| **Hængere med indhold pr. hænger** | – | ✅ |
| **Ture med flere stop**, chaufføren tilføjer stop | – | ✅ |
| **Gentagne ture** (Gentag/serier) | – | ✅ |
| **Krav ved afslutning** (mængde/foto) | – | ✅ |

Hvorfor Økonomi og tidsregistrering er i kernen (undersøgt 2026-10-18):
- Alle logistikfirmaer havde priser før Økonomi ("Priser & Rapport").
- Uden Økonomi har partneren kun Historik-eksporten at fakturere ud fra (ingen haster, ventetid, hænger, afvigelser).
- Ventetid hos kunden dokumenteres kun via Økonomi (rettelse → godkendelse).
- Haster-besked går kun til chauffører, der har stemplet ind. Uden tidsregistrering ville partnerens chauffører aldrig få kundens hastebestillinger.
- På timepris trækkes chaufførens pause fra via stemplingerne.

En partner uden tilknyttede kunder ser en velkomstside på Ture ("opret chauffører, bed kunden tilknytte jer"). En diskret linje nederst i "Mere" nævner Premium.

## Sådan er det bygget

- **Én liste:** `PREMIUM_CAPABILITIES` i `backend/server.py`. `GET /api/logistics/profile` giver `{tier, is_premium, connected_customers, has_connections, capabilities}` til både admin og chauffør.
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
