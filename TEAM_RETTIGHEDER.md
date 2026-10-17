# Team & rettigheder (logistik)

Skrevet 2026-10-17.

En logistik admin kan invitere **koordinatorer** under **Mere › Team & rettigheder**.

## Model

- **Koordinator i databasen:** `role = logistics_admin`, `is_coordinator = true` og `permissions = {nøgle: bool}`. Al eksisterende kode for logistik admin virker derfor uændret.
- **Administratorer:** firmaets oprindelige admins (`is_coordinator` falsk) har altid alle rettigheder.
- **Håndhævelse:** backend håndhæver centralt i `TenantContextMiddleware`. Tabellen `_PERM_ROUTES` kobler rute til rettighed.
  - Undtagelse: `PUT /tours/{id}` tjekkes i `update_tour`. Ændres `driver_id`, kræves "Tildel chauffører"; andre felter kræver "Opret og ret ture".
- **Frontend:** skjuler faner og knapper ud fra `user.permissions` (fra `/auth/me` og login).
- **Hvornår ændringer slår igennem:** senest efter 15 sekunder (cache).
- **Deaktivering:** en deaktiveret koordinator afvises med det samme (401), også med et gammelt token.

| Nøgle | Betyder |
|---|---|
| `tours_edit` | Opret, ret, kopiér, flyt ture; Excel-import; genaktivér |
| `tours_assign` | Tildel og frigiv chauffører |
| `tours_delete` | Slet ture |
| `messages` | Skriv med chauffører (læse kan alle) |
| `planning` | Planlægning og tidsregistrering |
| `drivers` | Chauffører, vogne og hængere |
| `reports` | Rapportering |
| `economy_view` | Se Økonomi (rapport, regler, helligdage) |
| `economy_edit` | Ændre prisregler/indstillinger, rette priser, godkende, fakturere, aftalt pris |
| `locations` | Lokationer |
| `archive` | Arkiv (dagrapporter og kvitteringer) |
| `settings` | Indstillinger |
| `team` | Team & rettigheder, disponent-telefon |

## Regler

- En koordinator med `team` kan kun give rettigheder vedkommende selv har.
- En koordinator kan ikke ændre sine egne rettigheder.
- En koordinator kan ikke ændre en administrator.
- Invitationen kommer som mail (72 timer). En afventende invitation kan trækkes tilbage helt. En aktiv koordinator deaktiveres og kan genaktiveres.
- Skabeloner i UI:
  - Disponent
  - Disponent + overblik
  - Bogholder
  - Alt undtagen økonomi

## Begrænsning til kunder
- En koordinator kan begrænses til bestemte kunder (`customer_scope`). Det kan være genbrugsplads-kunders id'er og/eller `own` (firmaets egne ture og kunder). En tom liste betyder alle kunder.
- Begrænsningen gælder Ture, beskeder, tildeling, ret og slet, samt Rapportering.
- En begrænset koordinator kan kun give adgang inden for sin egen begrænsning.

## "Ring til planlæggeren" (chauffør)

`GET /api/driver/dispatch-contact?tour_id=` returnerer telefonnummeret på den der tildelte turen, hvis vedkommende har et. Ellers returnerer den firmaets disponent-telefon, som sættes på Team-siden. Knappen ligger i beskedarket og i tur-panelet.
