# Ture: ny arbejdsflade for logistik admin og nye chauffør-kort

Skrevet 2026-10-16. Erstatter "Manuelle ture", Arkiv › Ture og den mørke turliste
hos chaufføren.

## Hvad der var før, og hvorfor det blev lavet om

| Gammel funktion | Hvorfor den fandtes | Problem | Nu |
|---|---|---|---|
| Vælg plads først, så ture | Excel/ARGO-import var pr. plads | Planlæggeren kunne ikke se dagen samlet | Alle ture for dagen, grupperet pr. lokation, filtre for lokation/kunde/chauffør/kilde |
| Kun `source=manual,argo` | Bestillinger blev håndteret i Planlægning | Halvdelen af dagen manglede | Alle kilder (Manuel, Bestilling, ARGO) |
| "Firma tur"-modal | Private ture for slutkunder | Firmanavnet blev gemt i *fraktion*-feltet; ingen materiale, tidsvindue, prioritet eller chauffør | Én "Ny tur"-formular: lokation, firma, opgave, materiale, container, kapacitet, flere stop, aflevering, tidsvindue, prioritet, chauffør, note, gentagelse |
| Tildel-kolonne (skrivebeskyttet: "brug Planlægning") | Tildeling lå ét sted | Ekstra fanehop for den hyppigste handling | Tildel direkte i rækken, i tur-panelet og som massehandling; chaufføren får push |
| "Slet alle i plads" | Rydde en fejlimport | Én knap slettede alt på pladsen | Fjernet. Vælg ture → Slet (med bekræftelse; startede, færdige og kundebestillinger springes over) |
| Pause-rækker (`is_pause`) | Gammel pausemodel | Pauser registreres nu i tidsregistreringen | Skjult i Ture |
| HÆNGER/SOLO-optimering pr. plads | Admin så chaufførens rute | Chaufføren optimerer selv i appen | Fjernet fra admin |
| Audit-log i separat modal | Hvem tildelte hvad | Ingen samlet historik for turen | Tidslinje i tur-panelet: oprettet → tildelt → taget → på vej → færdig/kan ikke |
| Ret via EditTourModal | Rette en tur | Kunne ikke flytte dato eller rette adresse | Ret i panelet: dato, materiale, adresser, container, kapacitet, tid, opgave, prioritet, note |
| Arkiv › Ture | Overblik over historik | Ture hørte ikke hjemme i Arkiv | Ture › Historik |
| 5-sek. polling hele tiden | "Live" data | Kørte også når fanen ikke var åben | 10 sek., kun mens fanen er synlig, og straks ved fokus |

## Navigation (logistik admin)

Faner fremme: **Ture** (start) · Planlægning · Chauffører · Rapportering · Økonomi.
Under **Mere**: Lokationer/Genbrugspladser · Arkiv (PDF og kvitteringer) · Indstillinger.
På mobil: de daglige faner som piller + menu-skuffe med alle. Samme mønster som
Location Admin.

Planlægning beholdes. Den er stedet for kapacitet, tidsregistrering og
ressourceplanlægning. Ture er stedet for dagens drift.

## Beskeder pr. tur

`tour_messages` (backend/server.py, "TUR-BESKEDER").
- `GET /api/tour-messages/unread` giver ulæste beskeder til den der spørger: chauffør → fra planlægger; admin → fra chauffører.
- `GET /api/tour-messages/{tour_id}` åbner tråden og markerer modpartens beskeder som læst. Afsenderen ser "Læst".
- `POST /api/tour-messages/{tour_id}` sender en besked. Planlæggerens besked sendes som web push til chaufføren på turen.
- Adgang kræver, at turen tilhører firmaet. En chauffør kan kun skrive på sine egne eller frie ture.
- Hurtigsvar til chauffør ("Forsinket ca. 15 min", "Ingen adgang" …) og planlægger.

## Chauffør: TURE-fanen

`frontend/src/components/DriverTourCard.jsx` erstatter det mørke `MobileTourCard`:
- Lyse kort med farvet venstrekant pr. status.
- Én hovedknap pr. tilstand: **Start tur** → **Afslut tur**. Afslut åbner panelet, når der skal vejes, så knappen aldrig fejler.
- **Kort** og **Besked** (med ulæst-tæller) ved siden af. Tryk-flader på mindst 44 px.
- Tidsvindue, kapacitet, container, km, kunde og tur-nr. står på én linje. Noten står i en gul boks. Forsinkelse og "Tildelt dig" vises som mærker.
- Den gamle skjulte mørke liste (≈1.100 linjer der blev renderet hvert 5. sek.) er fjernet.

## Rapportering

`GET /api/admin/statistics` viste 0 for logistikfirmaer, fordi den:
1. læste den gamle tomme `drivers`-kollektion (chauffører ligger i `users`), og
2. kun talte ture firmaet selv ejer, ikke kundernes ture tildelt firmaet.

Begge dele er rettet. Desuden:
- Turvarighed regnes nu rigtigt (`on_way_time` manglede i projektionen).
- Ordrer tælles for firmaets kunder.
- Der er en ny live-blok "I dag", som opdateres hvert 30. sekund.
