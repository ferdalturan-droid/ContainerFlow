# Ture: ny arbejdsflade for logistik admin og nye chauffør-kort

Skrevet 2026-10-16. Erstatter "Manuelle ture", Arkiv › Ture og den mørke turliste
hos chaufføren.

## Hvad der var før, og hvorfor det blev lavet om

| Gammel funktion | Hvorfor den fandtes | Problem | Nu |
|---|---|---|---|
| Vælg plads først, så ture | Excel/ARGO-import var pr. plads | Planlæggeren kunne ikke se dagen samlet | Alle ture for dagen, grupperet pr. lokation, filtre for lokation/kunde/chauffør/kilde |
| Kun `source=manual,argo` | Bestillinger blev håndteret i Planlægning | Halvdelen af dagen manglede | Alle kilder (Manuel, Bestilling, ARGO) |
| "Firma tur"-modal | Private ture for slutkunder | Firmanavnet blev gemt i *fraktion*-feltet; ingen materiale, tidsvindue, prioritet eller chauffør | Én "Ny tur"-formular: lokation, firma, opgave, materiale, container, kapacitet, flere stop, aflevering, tidsvindue, prioritet, chauffør, note, gentagelse |
| Tildel-kolonne (skrivebeskyttet: "brug Planlægning") | Tildeling lå ét sted | Ekstra fanehop for den hyppigste handling | Tildel direkte i rækken, i tur-panelet og som massehandling; vises straks i chaufførens app |
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
- `POST /api/tour-messages/{tour_id}` sender en besked. Chaufføren ser den i appen inden for ca. 15 sek. (toast + vibration + tæller på kortet). Web push til chauffører er slået fra (Fase 15.23b). Backend forsøger kun push, hvis en chauffør har et abonnement, og det har ingen i dag.
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


## 2026-10-17: Container eller gods, ny tur v2, ny chaufførside, push

### Hvilke felter en tur har (B2B kontra premium)
| Hvor turen hører til | Type | Felter |
|---|---|---|
| Genbrugsplads-kundens plads (B2B, bestilling eller manuel) | altid **Container** | materiale, container nr., kapacitet, containeropgaver; vægt kræves ved "Afhent container" |
| Partner-firma (option 2) | altid **Container** | som B2B; ingen hængere eller indholdslinjer |
| Premium-firmaets egne lokationer | **Container** eller **Gods og andet** (valgt pr. tur, sidste valg huskes) | Gods: "hvad skal køres" med antal og enhed, opgaver Afhentning/Levering/Afhentning + levering/Flytning/Andet, vægt valgfri, ingen containerfelter |

- Backend håndhæver reglerne i `_normalize_tour_doc`. Frontend viser kun de felter, der giver mening.
- Et premium-firma med kunder får B2B-flowet på kundernes pladser og det generiske flow på egne lokationer.
- Forbindelsen oprettes af kunden (kunde admin › Logistik-partnere) og bruger samme firma-id. Derfor slår `has_connections` straks igennem for både admin og chauffør.

### Ny tur
- **Fremme:** lokation, dato, kunde (fra kunderegistret), type, opgave, indhold, afhentning og aflevering (vej, postnummer og by fra Datafordeler-listen, eller "Tilføj manuelt"), chauffør og note.
- **"Flere detaljer":** tidsrum, prioritet, hængere (premium), container nr. og kapacitet, aftalt pris med valget "ventetid oveni", og gentagelse.
- **Hængere:** ved 2 eller flere hængere vælges en hænger pr. indholdslinje. Prisen sættes enten som aftalt pris for hele turen eller med prisregler på "Antal hængere".

### Chauffør (TURE)
- **Faner:** Mine, Ledige (grupperet pr. lokation plus "Fra tidligere dage") og Færdige.
- **I gang:** en tur der er i gang ligger øverst.
- **Kort:** adressen står først. Én hovedknap: Start, derefter Afslut.
- **Afslut:** vejning sker i panelet. Ved flere læs vejes hvert læs for sig; ved gods er vægten valgfri. Vægte kan rettes pr. læs efter afslutning.
- **Profil:** kunde, vogn, hænger, notifikationer og log ud.

### Push
- **Hændelser:** ny tildeling, besked fra planlægger, ændring, aflysning, og ny haster-tur til chauffører der har stemplet ind.
- **Til og fra:** slået til som standard, og chaufføren slår det fra under Profil.
- **iPhone og iPad:** kræver at appen er lagt på hjemmeskærmen (guide vises).
- **Kode:** `_push_driver`, `_push_new_haster`, `/api/push/*`, `/api/driver/push-settings` og `frontend/src/lib/push.js`.

### Én opgave er én tur, også med flere stop (2026-10-17)
- **Før:** flere afhentningsadresser i "Ny tur" gav én tur pr. adresse (arvet fra "Firma tur"). Hver tur fik alle materialer og den fulde aftalte pris, så gods og pris blev dobbelte. Chaufføren skulle starte og afslutte hver tur, og Rapportering talte dem som flere ture.
- **Nu:** afhentninger og afleveringer gemmes som `stops` på én tur.
  - `address` og `facility` spejler første afhentning og sidste aflevering, så kort, rute, rapporter og PDF virker uændret.
  - Chaufføren krydser hvert stop af i tur-panelet (`POST /api/tours/{id}/stops/{stop_id}/done`) og bliver advaret, hvis turen afsluttes med stop der ikke er krydset af.
  - Planlæggeren kan rette eller tilføje stop; stop der allerede er krydset af, bevares.
- **"Opret som separate ture"** kan stadig vælges, fx ved flere containere hos forskellige kunder, der kan køres af forskellige chauffører.
- **Gentag** opretter fortsat én tur pr. dag. Materialer er linjer på turen og opretter aldrig ekstra ture.
- **B2B-bestillinger** har én adresse og påvirkes ikke.

### Afslut tur: hvad chaufføren registrerer (2026-10-17)
- **Ny tur → "Ved afslutning":** to Ja/Nej-valg, "Skal chaufføren registrere mængde?" og "Skal chaufføren tage billede?". Gemmes som `capture: {quantity, photo}` og kan rettes bagefter. Standard: mængde = ja for container (afhent) og løs afhentning, ellers nej; billede = nej.
- **Mængde i linjens egen enhed:** "Køkkenelementer, 12 paller" spørger om antal paller, ikke kg. Hver linje har en "Som planlagt"-knap. Svarene gemmes i `cargo_lines[i].actual_qty`, og `weight` beregnes kun af kg- og ton-linjer.
- **Billede:** taget med kameraet, komprimeret på telefonen og gemt i `tour_photos` (`/api/tours/{id}/photos`). Planlæggeren ser billederne under "Registrering" i tur-panelet.
- **Blød validering:** mangler noget, der er slået til, får chaufføren en liste og kan vælge "Afslut alligevel". Ture med capture har ikke længere et hårdt vægtkrav. B2B-bestillinger uden capture beholder det gamle krav.
- **Hængere:** forklares nu ("Bruges til afregningen af turen"). Chaufføren bekræfter eller retter antallet; det gemmes i `trailer_count_actual` og bruges i prisen.
- **Driver self-service** i samme ark: ventetid (sendes til godkendelse), afvigelse eller besked med hurtigvalg (fx "Mindre end planlagt", "Kunden var ikke til stede", "Skade/mangler"), som lander i turens beskedtråd. En afsluttet tur kan rettes via "Ret registrering".
- **Planlæggeren** ser planlagt mod registreret pr. linje (orange, når de afviger), "Hængere: planlagt X · kørt Y" og billederne.
- **Kode:** `frontend/src/components/FinishSheet.jsx` og `Registration` i `pages/ToursWorkspace.jsx`; backend `cargo_actuals` i `PUT /api/tours/{id}` og `trailer_count` i `PUT /api/driver/tours/{id}/trailer`.

### Stop med kvittering, serier og robust afslutning (2026-10-18)
- **Stop:**
  - Hvert stop kan have note og kontakt (navn + telefon). Chaufføren ringer direkte fra stoppet.
  - Krydset gemmer fuldt tidsstempel.
  - Ved aflevering kan modtagerens navn skrives.
  - "Kunne ikke" på ét stop (årsagskode + tekst): stoppet bliver rødt, turen kører videre, og planlæggeren får en besked.
  - Chaufføren kan tilføje et stop (ikke på B2B-kundebestillinger). Det markeres "tilføjet af chaufføren" og tæller først i prisen, når planlæggeren har godkendt det i tur-panelet.
  - Planlæggerens rettelser bevarer chaufførens kvittering og afvigelser.
- **Ny tur:**
  - Haster og container nr. står fremme.
  - Mængde er som standard slået til på gods, når en linje har et antal.
  - Kunden vælges fra kunderegistret.
  - Aftalt pris viser totalen ved flere ture.
  - Gentagne ture får `series_id`. I tur-panelet kan man "Gem også for de N kommende ture i serien" (`PUT /api/tours/series/{id}`, aldrig datoen) og "Slet resten af serien".
- **Ture-siden:**
  - Opmærksomhedslinjen viser "N mangler pris" og "N med afvigelse at se på", og begge kan bruges som filter.
  - Rækkerne har chips for Mangler pris, Faktureret, Rettelse venter og Afvigelse.
  - Afvigelser omfatter: registreret mængde ≠ planlagt, mangler mængde eller billede, stop der ikke er krydset af, stop der ikke kunne gennemføres, ekstra stop fra chaufføren, hængere planlagt ≠ kørt og afvigelseskode ved afslutning.
- **Afslutning i ét kald:** `POST /api/tours/{id}/finish` med `op_id` gemmer hængere, mængde/vægt, afvigelseskode, besked og ventetid på én gang og kan sendes igen uden dobbelte handlinger.
- **Offline-kø** (`frontend/src/lib/tourOpQueue.js`): start, stop-kryds, billeder og afslutning gemmes på telefonen uden net og sendes automatisk, når forbindelsen er tilbage. Afviser serveren en handling, får chaufføren besked.
- **Afvigelseskoder** vedligeholdes pr. firma (Økonomi › Indstillinger) og bruges ved forgæves tur, ved stop og ved afslutning.
- **"Ét afslutningsark for alle ture"** (firmaindstilling, slået fra som standard): også B2B-ture bruger afslutningsarket. Vægten er påkrævet som før, løs afhentning vejes pr. læs (med "Gem vægte uden at afslutte"), og vejesedlen kan vedhæftes. Uden indstillingen bruger B2B det hidtidige flow.
- **Chaufføren ser dagens dato ved login** (før kunne sidste sessions dato blive genskabt dagen efter).
- **Tests:** `backend/tests/e2e/` (se WORKFLOW.md).

### Ejerskab følger lokationen (2026-10-18, P0)
- **En tur på en genbrugsplads-kundes plads er kundens tur.** Det gælder uanset om den kom fra bestillingssiden, Excel, Kopiér eller "Ny tur". `company_id` er kundens, `customer_name`/`customer_code` kommer fra kunden, og logistikfirmaet står i `assigned_logistics_company_ids`.
- **Det betyder:** kundens priser gælder, kunden ser turen i sit arkiv, og en koordinator begrænset til kunden ser den.
- **En tur på firmaets egen lokation er firmaets egen tur** (registerkunde, `firma:`-nøgle, kunden ser intet).
- **Før:** "Ny tur" og Kopiér gav logistikfirmaets id. Tour-modellen havde ikke `company_id`, så TenantAwareDB satte firmaets id ved insert. Det gav "Cirklen · Egne ture", kunden både som genbrugsplads-kunde og som "Fra ture" i Kunder & priser, kundens pris der ikke ramte, og koordinator-scope der skjulte turen.
- **Kopiér** sender ikke længere kundenavnet med; backend afgør ejeren ud fra lokationen.
- **Engangsrettelse ved opstart** (`_migrate_tour_owner_from_plads`): ikke-fakturerede, ikke-slettede ture på en kundes plads med et logistikfirmas id bliver kundens. Firmaet beholdes som tildelt, og antallet logges.
- **Undtagelse ("noget på kundens plads, kunden ikke skal se"):** bygges ikke. Brug en egen lokation med samme adresse.

### Én planlægningsside (2026-10-18, P1)
- **"Planlægning › Planlæg ture" er fjernet.** Den gjorde det samme som Ture (tildel ture), men med sin egen dato, sin egen datahentning og rå koder som `afhent_lever`. Den kendte heller ikke stop, prisstatus, afvigelser eller serier.
- **Ture har en visningsknap "Pr. lokation | Pr. chauffør":** samme dato, filtre, rækker og panel. "Uden chauffør" står øverst, og rækkerne viser lokation og kunde. Valget huskes i browseren.
- **"Hurtigt overblik" er nu én linje øverst på Ture:** "X ture · Y færdige · Z kg · N uden chauffør". Kortet "Genbrugspladser" (der talte alle pladser, også kunders) er fjernet.
- **Fanen hedder "Tid & ressourcer"** (Tidsregistrering og Planlæg ressourcer).
- **Gruppens kunde-tekst** viser alle kunder i gruppen (før kun den første tur, fx "Hansen Depot Køge · Helsingør Forsyning").

### Chaufføren og Ny tur, finpudsning (2026-10-18)
- **Næste stop på kortet (P6):** når turen er "På vej", viser kortet det næste åbne stop med adresse, note (gul) og ring-knap, hvis stoppet har telefon. Kort-knappen navigerer til næste stop.
- **Hænger kun når relevant (P7):** afslutningsarket spørger kun om hængere ved planlagt hænger, hænger i profilen eller en hænger foreslået ved start. Ellers gemmes 0 hængere med `trailer_source="none"` (bekræftet).
- **B2B uden modal (P5):** i det gamle vægt-flow står "Hænger: Ja · ret" (forudfyldt) som en linje øverst i vægtarket. Modalen bruges kun, når turen afsluttes uden vægtark.
- **"Venter på net" (P10):** gråt mærke på kortet, når en handling ligger i offline-køen.
- **Rettesteder efter afslutning:** "Ret mængde eller billede" (afslutningsarket) og "Ret tid, hænger eller ventetid (godkendes)". Hænger, tid og ventetid rettes kun det sidste sted.
- **Ny kunde (P2):** "Opret som ny kunde" vises først, når man forlader feltet, med mindst 3 tegn, og ikke mens "Mente du …?" venter på svar ("Nej, det er en ny kunde").
- **Dubletter (P9):** `POST /tours/bulk` svarer 409 med listen, hvis der samme dag findes en ikke-færdig tur med samme plads + container-nr. (container) eller samme adresse + materiale (gods). Ny tur og Kopiér spørger "Opret alligevel?" (`force=true`).
- **Ingen "A → A" (P3):** pilen vises ikke, når aflevering = afhentning.
- **Ingen økonomi-ret (P4):** panelet siger "Bed din administrator om at oprette prisen".

