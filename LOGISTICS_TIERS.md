# Logistikfirmaer: Premium (option 1) og Partner (option 2)

Skrevet 2026-10-16. Gælder KUN logistikfirmaer — genbrugsplads-kunder
(kundetype "kunde") er ikke berørt.

## De to typer

| | Option 1 — **Premium** | Option 2 — **Partner** |
|---|---|---|
| Oprettes af super admin under | "Kunder & Logistik" (kundetype *Logistik (premium)*) | "Tilføj logistik partner" (biblioteket) |
| I databasen | `company_type = logistics`, `from_library` ≠ true | `company_type = logistics`, `from_library = true` |
| Hvem betaler | Logistikfirmaet selv | Adgang via genbrugsplads-kunden |
| Badge hos super admin | "Logistik · Premium" | "Logistik-partner" |

Begge typer kan tilknyttes genbrugsplads-kunder (kunde admin → Logistik-partnere).
Koden: `_logistics_tier()` / `_logistics_profile()` i `backend/server.py`,
`GET /api/logistics/profile` → `{tier, is_premium, connected_customers, has_connections}`.

## Hvad gælder hvor

| Funktion | Premium uden kunder | Premium med kunder | Partner |
|---|---|---|---|
| Egne lokationer (opret/ret/deaktivér) | ✅ | ✅ | – (kun kunders pladser) |
| Egne ture (manuelle, "firma tur") | ✅ chauffører ser dem under **Egne ture** | ✅ | ✅ vises på kundens plads |
| Chauffør vælger kunde | – (kun Egne ture, ingen valg) | Egne ture + kunderne | Kunderne |
| Kunders genbrugspladser (read-only) | skjult | ✅ | ✅ |
| Bestillinger fra genbrugspladser | – | ✅ for de tilknyttede kunder | ✅ |
| Økonomi: kunder | Slutkunderne fra egne ture ("firma") | + genbrugsplads-kunder | Genbrugsplads-kunder (+ evt. firma-ture) |
| Helligdage: "Kundens kalender først" | skjult (egen kalender bruges) | ✅ — men kun for den kundes ture | ✅ |

Regler bag tabellen:
- **Manuelle ture ejes altid af logistikfirmaet** (`company_id` = firmaet) og
  knyttes til firmaet (`assigned_logistics_company_ids`). De flyttes ikke ind
  hos genbrugsplads-kunden, så en privat "firma tur" aldrig dukker op i
  kundens data. En chauffør der kører for kunde X ser firmaets egne ture på
  X's pladser.
- **Lokationsnavne er entydige** på tværs af alle firmaer, fordi ture peger på
  pladser via navn. Omdøbes en egen lokation, følger firmaets egne ture med.
- I Økonomi er kunden for en egen tur det firma der står på turen
  (`firma:<navn>`), så priser og fakturagrundlag kan laves pr. slutkunde.

## Når en ny funktion kun gælder option 1
Brug `logisticsProfile.is_premium` i frontend (AdminPage i `App.js`) og
`(await _logistics_profile(cid))["is_premium"]` i backend. Funktioner der
afhænger af en genbrugsplads-kunde skal tjekke `has_connections` og kun
gælde for den konkrete kundes data.

## GPS på egne lokationer (2026-10-17)
GPS bruges som startpunkt for "Optimer rute" hos chaufføren (sortering efter afstand, km pr. tur).
- **Udfyldes automatisk:** når en lokation gemmes uden GPS, slås adressen op i OpenStreetMap (Nominatim, gratis, kun Danmark).
- **Fallback:** den indbyggede postnummer-tabel (omtrentlig: byens midte). Google Maps er slået fra.
- **Knapper:** "Find fra adressen" og "Vis på kort".
- **Begrænsning:** steder uden rigtig adresse (fx byggepladser) skal have koordinater skrevet ind manuelt.
