# Prisberegning i ContainerFlow - komplet forklaring

Skrevet 20.10.2026 til en anden AI eller udvikler, der skal forstå, ændre eller fejlfinde
priserne. Del A forklarer reglerne trin for trin, med henvisninger til koden. Del B har over 150
eksempler. De er regnet af den rigtige prismotor og kontrolleret mod håndregnede facitter.

Kilder:
- `backend/pricing.py` er selve motoren. Den består af rene funktioner uden database.
- `backend/server.py` står for afsnittet "ØKONOMI". Det henter turen, reglerne, kalendere og stemplinger og bygger turens fakta.
- `frontend/src/pages/EconomyPanel.jsx` er skærmbillederne.
- `PRICING_SPEC.md` er den forretningsmæssige beslutningslog. Ved tvivl er det denne fil og koden, der gælder.

Eksemplerne i del B kan regnes igen efter en ændring af motoren:

```bash
docker exec -i cf-app-e2e python - < scripts/prisberegning_eksempler.py > /tmp/eksempler.md
```

Scriptet stopper med en fejlliste, hvis motoren ikke længere giver de dokumenterede beløb. Ellers
erstattes eksempeldelen med scriptets output: alt fra den skjulte kommentar lige under indledningen
til Del B og ned.

---

## Del A - Sådan regnes en pris

### A1. Hvem regner, hvem ser

- **Logistikfirmaet ejer priserne.** Prisregler, rapport og godkendelser ligger under "Økonomi" hos logistik-admin.
  - Al økonomi kræver modulet "economy": et premium-firma, eller et basic-firma, som super admin har givet modulet.
  - Et basic-firma med modulet kan kun lave priser for sine tilknyttede genbrugsplads-kunder, ikke for egne kunder.
- **Koordinatorer** styres af rettigheder:
  - "Se priser og økonomi" (`economy_view`) giver læseadgang.
  - "Ændre priser, rette og godkende" (`economy_edit`) giver skriveadgang.
  - En koordinator med kundeafgrænsning ser og prissætter kun sine kunder.
- **Chaufføren** ser aldrig beløb. Chaufføren ser:
  - om turen er fast pris eller timepris (`GET /driver/tour-pricing`);
  - timesatsen;
  - om pause trækkes fra, afrundingen og minimum.
- **Kunden** (genbrugspladsen) ser ingen priser.
- **Alle beløb er ekskl. moms.** Rapporten lægger moms på summen (standard 25 %, kan ændres i Økonomi > Indstillinger).

### A2. Begreber

| Begreb | Betydning | Kode |
|---|---|---|
| Prisregel | Én regel: enten en **grundpris** (`kind: base`) eller et **tillæg** (`kind: surcharge`) | `price_rules`-samlingen |
| Grundpris | Bestemmer prismodellen: fast pris, timepris, pris pr. container eller pris pr. enhed | `pricing.model` |
| Tillæg | Lægges oven på grundprisen og har en kategori. Beløbet er kr, % af grundprisen eller kr/t | `category`, `surcharge.unit/value` |
| Betingelser | Hvilke ture reglen gælder for. En tom betingelse betyder alle ture | `conditions` |
| Specificitet | Point for hvor præcis en regel er. Den mest præcise regel vinder | `pricing.specificity` |
| Prisaftale | Én formular med fælles betingelser, en grundpris, en evt. forgæves-pris og en liste af tillæg. Den gemmes som flere regler med samme `bundle_id` | `pricing_save_bundle`, `_bundle_rule_bodies` |
| Version | En rettet regel får en ny version. Hvilken version en tur bruger, afgøres af hvornår **turen blev oprettet** | `version_from`, `version_to`, `_rule_active_at` |
| Gyldighed | "Kørselsdato fra/til": hvilke **kørselsdatoer** reglen gælder for | `valid_from`, `valid_to` |
| Fakta | Turens oplysninger, som prisen regnes ud fra (kunde, dagtype, tid, hængere ...) | `_PricingContext.attrs` |
| Rettede fakta | Godkendte rettelser eller admin-rettelser af start, slut, hængere, ventetid og pause | `tour.fact_overrides` |
| Aftalt/manuel pris | Et fast beløb for turen, der erstatter reglerne | `tour.price_override` med `mode: "fixed"` |
| Ekstra linjer | Faste linjer oveni, fx "Ekstra rengøring 300 kr" | `price_override.extra_lines` |
| Faktureret | Prisen er frosset som et øjebliksbillede | `tour.price_locked` |

### A3. Overblik: fra tur til pris

```
tur ──► er turen faktureret? ── ja ──► brug det frosne beløb (+ markering "Faktureret")
          │ nej
          ▼
     turens fakta (A4) + tid (A5)
          ▼
     regler i spil: rigtig version (oprettelse) + aktiv + kørselsdato inden for gyldighed (A6)
          ▼
     matchende regler (A7) ──► grundpris = mest specifikke; tillæg = mest specifikke pr. kategori (A8)
          ▼
     grundbeløb efter prismodel (A9)
          ▼
     tillæg regnes af grundbeløbet (A10)
          ▼
     aftalt/manuel pris? ──► erstatter alt undtagen evt. ventetid (A11)
          ▼
     ekstra linjer lægges til (A11)
          ▼
     total = summen af linjerne. Ingen grundpris/tid/antal = ingen total (A12)
          ▼
     "Opret pris"-aftaler for ture uden pris (backfill, A6) og forklaring på "Mangler pris" (A12)
```

Koden: `_PricingContext.price(t)` i `server.py` kalder `pricing.price_tour(attrs, rules, time_info, override)`.

### A4. Turens fakta (`_PricingContext.attrs`)

| Fakta | Hvor det kommer fra | Detaljer |
|---|---|---|
| Kunde (`customer_id`) | `customer_key(t)` | Se tabellen under denne |
| Lokation (`location_code`) | Pladsens `location_code`, slået op på turens `plads`-navn | Hvis turen kommer fra en bestilling, er det præcise plads-navn vigtigere end ordrens QR-kode |
| Leveringsadresse (`delivery_label`) | Bestillingens leveringsadresse som **navn** (fx "HCS A/S Helsingør") | Se rækkefølgen under denne tabel |
| Materiale(r) | Én pr. indholdslinje (`cargo_lines[].text`), ellers `fraction` | Bruges som liste (se A7) |
| Opgavetype | `tour_type` | normal, flyt, vaerksted, afhent_vaerksted, loes_afhentning, afhentning, levering, afhent_lever, flytning, andet. "værksted" skrives "vaerksted" |
| Prioritet | `priority` | urgent, haster og high bliver "haster". low, senere og sidst bliver "lav". Alt andet er "normal" |
| Dagtype | Kørselsdatoen (A4b) + helligdagskalender (A4c) | Hverdag, Lørdag, Søndag eller Helligdag. Typerne udelukker hinanden: en helligdag er altid "Helligdag" |
| Hænger / antal hængere | `_trailer_info(t)` | Se A4d |
| Containerstørrelse | `capacity_label` på turen/ordren | Tekst, fx "Åben container 20 m³" |
| Starttid (`start_min`) | Rettet starttid, ellers `on_way_time` ("På vej") | Minutter efter midnat. -1 hvis den mangler |
| Udfald | Forgæves, hvis turen er markeret "kan ikke gennemføres" og ikke gennemført. Ellers gennemført | |
| Containere | Se A4e | Bruges af "pris pr. container" |
| Enheder | Indholdslinjernes antal pr. enhed | Registreret antal (`actual_qty`) vinder over planlagt (`qty`). Samme enhed lægges sammen |
| Stop | Antal stop på turen | Stop, som chaufføren selv har tilføjet, tæller først når planlæggeren har godkendt dem. Ingen stopliste = 2 (afhentning + aflevering) |
| Ventetid | Kun `fact_overrides.waiting_min` | Se A10. Den ventetid, chaufføren selv oplyser (`waiting_reported_min`), indgår ikke i prisen |
| Pause-rettelse | `fact_overrides.deduct_pause` | Overstyrer reglens "pause trækkes fra" |

**Kunden (`customer_key`).**

| Turens situation | Kunde i prisreglerne |
|---|---|
| Turen hører til en anden virksomhed end logistikfirmaet (B2B: genbrugsplads-kundens plads) | Kundens firma-id (`company_id`) |
| Logistikfirmaets egen tur med et navn fra kunderegistret (`customer_ref_id`) | `firma:<navn fra registret med små bogstaver>` |
| Egen tur med et firmanavn på turen (`private_company` eller `customer_name`) | `firma:<navnet med små bogstaver og enkelte mellemrum>` |
| Egen tur uden navn | Logistikfirmaets eget id ("Egne ture uden kunde") |

Ejerskab følger lokationen. En tur på en genbrugsplads-kundes plads hører til kunden. En tur på en egen lokation hører til logistikfirmaet.

**Leveringsadressen** vælges i denne rækkefølge:
1. alternativ adresse (fra kundens adressebog);
2. manuel alternativ adresse;
3. ordrens leveringsadresse;
4. teksten, matchet mod lokationens adressebog;
5. selve teksten.

Manuelle ture uden bestilling bruger "Modtager"-feltet (`facility`).

#### A4b. Kørselsdatoen (`_service_date`)

Kørselsdatoen styrer dagtypen, gyldigheden ("kørselsdato fra/til") og hvilken periode turen står i i Rapport.

1. **Gennemført tur med "På vej"-tidsstempel** (`on_way_at`) → den danske dato, hvor turen blev **startet**. En lørdagstur, der først afsluttes søndag, er en lørdagstur.
2. **Gennemført tur uden tidsstempel** (ældre ture) → afslutningsdatoen. Er sluttiden (`time`) før starttiden (`on_way_time`), gik turen over midnat, og kørselsdatoen er dagen før.
3. **Forgæves tur** → den dag, den blev markeret forgæves.
4. **Ikke kørt endnu** → den planlagte dato (`date`).

Alle tidsstempler regnes om til dansk tid (`Europe/Copenhagen`, inkl. sommertid).

#### A4c. Helligdage (`holidays_for`)

Indstillingen "Brug kundens helligdage først" (`holiday_source: customer_first`) er standard. Med den bruges den første kilde, der har dage i årets kalender:

1. **Materialets kalender** på lokationen (`material_calendars`, den samme som bestillingssiden bruger).
2. Ellers **lokationens aktive kalender(e)** for året.
3. Ellers **kundens helligdagsgruppe** (sat af super admin).
4. Ellers **logistikfirmaets egen kalender**.

Med indstillingen `own` bruges altid den egne kalender.

Vigtigt: kilderne lægges **ikke** sammen. Har lokationen en kalender for året, bruges kun den, også selvom den egne kalender har flere dage (se eksemplerne i B12).

**Den egne kalender** (`own_holidays`):
- officielle danske helligdage, beregnet for ethvert år ud fra påskedag: nytårsdag, skærtorsdag, langfredag, påskedag, 2. påskedag, Kristi himmelfart, pinsedag, 2. pinsedag, 1. og 2. juledag;
- valgfrie dage: Grundlovsdag, Juleaften og Nytårsaftensdag er slået til som standard. 1. maj kan slås til;
- egne ekstra fridage lægges til, og fravalgte datoer trækkes fra;
- store bededag findes ikke (afskaffet fra 2024).

#### A4d. Hængere (`_trailer_info`)

Én sandhed bruges til pris, rapport og chauffør. Rækkefølgen er:

1. godkendt eller admin-rettet antal (`fact_overrides.trailer_count`);
2. ældre godkendt ja/nej (`fact_overrides.used_trailer`). "Ja" giver chaufførens antal, ellers det planlagte, ellers 1;
3. det antal, chaufføren har oplyst (`trailer_count_actual`);
4. planlagt antal (`trailer_count`);
5. ja/nej på turen (`used_trailer`), hvor ja giver 1.

Et automatisk forslag fra chaufførens profil (`trailer_source: "auto"`, ikke bekræftet) prissættes **med** hænger. Turen får markeringen "Hænger: automatisk, ikke bekræftet", og Rapport har et filter til den, så planlæggeren kan tjekke før fakturering.

#### A4e. Containere

Antallet findes i denne rækkefølge:
1. antal registrerede vægte (`container_weights`);
2. det anslåede antal ved løs afhentning (`loose_estimated_count`);
3. for containerture med indholdslinjer: 1 pr. linje. En linje med enheden stk eller containere tæller sit antal;
4. ellers 1.

"Pris pr. container" bruger mindst 1.

### A5. Tid (kun timepris og kr/t-tillæg)

Koden er `_tour_times`, `_PricingContext._load_times` og `pricing.split_driver_day`.

1. **Turens tid** er fra start til slut:
   - Start er en rettet starttid, ellers "På vej" (`on_way_time`).
   - Slut er en rettet sluttid, ellers "Afslut" (`time`).
   - En forgæves tur slutter, da den blev markeret forgæves.
2. **Over midnat:** er slut før start, lægges et døgn til (start 22:30, slut 01:15 = 165 min).
3. **Samme minut** (rettet 20.10.2026): start = slut er en fejlregistrering. Turen får "Mangler tid" med markeringen "Start og slut er samme minut - ret tiden". Før blev den regnet som 24 timer.
4. **Samtidige ture.** Alle chaufførens gennemførte eller forgæves ture samme kørselsdato lægges på én tidslinje.
   - Tidslinjen deles i stykker ved hver start, slut og pause.
   - I hvert stykke deles minutterne ligeligt mellem de ture, der kører (indstillingen `concurrent_mode: split`, standard). Kunderne betaler altså tilsammen for den tid, chaufføren faktisk brugte.
   - Med `full` får hver tur alle sine minutter.
5. **Pauser** kommer kun fra chaufførens Tid-registrering (stempling med `slice_type: pause`), aldrig fra turen.
   - Pauseminutter, der falder i turens tid, tælles og deles som i punkt 4.
   - De trækkes fra, hvis grundprisen siger "pause trækkes fra" (standard). Turens rettelse "pause tæller/tæller ikke" vinder over reglen.
6. Resultatet pr. tur er:
   - `gross`: rå minutter;
   - `total`: minutter efter deling;
   - `pause`: heraf pause.

Mangler start eller slut, findes der ingen tid. En timepris får så status "Mangler tid".

### A6. Hvilke regler er i spil

En regel kan kun bruges på en tur, hvis alle tre punkter holder:

1. **Rigtig version** (`_rule_active_at`). Turens oprettelsestidspunkt (`created_at`, ellers den planlagte dato) skal ligge i `[version_from, version_to)`. Fra er med, til er ikke med.
   - En regel uden versionsfelter gælder altid.
   - En prisændring rammer derfor ikke ture, der allerede var oprettet eller bestilt.
2. **Aktiv** (`active`).
3. **Kørselsdatoen inden for gyldigheden** (`valid_from`, `valid_to`). Datoerne er inklusive.

**Sådan virker valgene, når man gemmer en regel eller prisaftale** (`effective`):

| Valg | Virkning |
|---|---|
| "Nye ture fra nu" (`now`, standard ved rettelse) | Den gamle version lukkes nu, og en ny starter nu. Eksisterende ture beholder den gamle pris |
| "Fra en dato" (`YYYY-MM-DD`) | Som ovenfor, men skiftet sker ved midnat dansk tid den dato. **Det følger oprettelsen, ikke kørslen**: en tur oprettet før datoen beholder den gamle pris, også selvom den køres efter |
| "Ture kørt fra en dato" (`driven_from`, prisaftaler) | Den gamle aftale får kørselsdato til dagen før. En ny aftale med `valid_from` = datoen gælder alle ture kørt fra datoen, også dem der allerede er oprettet (fx en serie). **Det rigtige valg ved en prisstigning pr. 1. januar** |
| "Også eksisterende ture" (`all`) | Versionen rettes bagudrettet. Fakturerede ture er stadig frosne |
| "Nye + ture uden pris" (`unpriced`, standard for nye prisaftaler) | Gælder fra nu og markeres `backfill_unpriced`. En ældre tur bruger reglen **kun** hvis den ellers ingen pris har. Den får så markeringen "Pris fra aftale oprettet efter turen (gælder ture uden pris)". En tur med pris ændres aldrig |

At slette en regel betyder som standard "Stop fra nu". "Slet helt" (`all`) fjerner den også bagudrettet. At slå en regel til eller fra laver også en ny version fra nu.

### A7. Hvornår passer en regel (`failing_conditions`)

Alle udfyldte betingelser skal passe. En tom betingelse passer altid.

| Betingelse | Passer når | Bemærk |
|---|---|---|
| Kunde | Turens kunde (A4) er i listen | |
| Lokation | Turens lokation er i listen | |
| Leveringsadresse | Navnet er i listen | Små bogstaver og enkelte mellemrum |
| Opgavetype | Opgavetypen er i listen | |
| Prioritet | Prioriteten er i listen | |
| Dagtype | Dagtypen er i listen | En helligdag er ikke en lørdag/søndag |
| Containerstørrelse | Teksten er i listen | Små bogstaver og enkelte mellemrum |
| Materiale, **grundpris** | **Alle** turens materialer er i listen | En betonpris gælder kun rene betonture. "Beton + Træ" kræver en regel med begge |
| Materiale, **tillæg** | **Ét** af turens materialer er i listen | |
| Hænger med/uden | Turen har/har ikke hænger | |
| Antal hængere | Antallet er i listen | "3" betyder 3 eller flere |
| Tidsrum | Turens **start**tid ligger i [fra, til) | Over midnat er tilladt (18:00-06:00). Uden starttid passer et tidsrum aldrig |
| Udfald | Standard er "gennemført" | En almindelig regel gælder **ikke** forgæves ture. Brug "forgæves" eller "alle" |

### A8. Hvilken regel vinder (`specificity`, `select_rules`)

Specificitet er summen af point for de betingelser, reglen har udfyldt:

| Betingelse | Point |
|---|---|
| Kunde | 64 |
| Lokation | 32 |
| Leveringsadresse | 16 |
| Opgavetype | 8 |
| Materiale | 4 |
| Containerstørrelse | 2 |
| Antal hængere | 2 |
| Prioritet | 1 |
| Dagtype | 1 |
| Hænger med/uden | 1 |
| Tidsrum | 1 |
| Udfald forgæves/alle | 1 |

- Point gives pr. **udfyldt betingelse**, ikke pr. værdi. To kunder i listen giver stadig 64.
- Vægtene er valgt, så en betingelse altid slår alle lavere betingelser tilsammen. En kunderegel slår derfor altid en regel uden kunde.
- **Grundpris:** den matchende grundpris med flest point. Står det lige, vinder den **senest rettede** (`updated_at`).
- **Tillæg:** samme princip, men **pr. kategori**. Det giver højst ét tillæg pr. kategori: Weekend, Helligdag, Haster, Hænger, Aften/nat, Ventetid, Ekstra stop og Andet.
  - Et kundespecifikt tillæg erstatter derfor det generelle i samme kategori. Kunden betaler ikke begge.
  - Et kundespecifikt tillæg på 0 kr fritager kunden.
  - Faldgrube: to forskellige gebyrer i kategorien "Andet" kan ikke lægges sammen. Kun det mest specifikke bruges.
- Prisaftaler giver automatisk deres tillæg den rigtige situation (`_CAT_AUTO`):
  - weekend → Lørdag/Søndag;
  - helligdag → Helligdag;
  - haster → prioritet haster;
  - hænger → med hænger, eller et bestemt antal;
  - aften → tidsrum, standard 18:00-06:00.
- Tillæggene arver aftalens betingelser (kunde, lokation ...) med udfald "gennemført". Samme tillægstype to gange i én aftale afvises.

### A9. Grundbeløbet efter prismodel (`price_tour`)

| Model | Beløb |
|---|---|
| Fast pris | Beløbet |
| Pris pr. container | Beløb × max(1, containere) |
| Pris pr. enhed | Beløb × antal i enheden (registreret, ellers planlagt). Uden antal i enheden: status "Mangler antal". Under minimumsbeløbet tilføjes linjen "Op til minimumsbeløb" |
| Timepris | Se nedenfor |

**Timepris** regnes i disse trin:
1. Fakturerbare minutter = tid efter deling (A5), minus pause hvis den trækkes fra.
2. Minutterne afrundes efter reglen:
   - **Ingen afrunding:** hele minutter med Pythons `round`. Halve rundes til nærmeste lige tal (22,5 → 22, 23,5 → 24).
   - **Op/ned/nærmeste til N min:** for "nærmeste" rundes halve op. "Op til 1 min" runder halve minutter op.
3. Minimum minutter løftes **efter** afrundingen. Turen får markeringen "Minimum N min anvendt".
4. Beløb = startgebyr + timepris × minutter / 60.
5. Under minimumsbeløbet tilføjes linjen "Op til minimumsbeløb".
6. Uden tid: status "Mangler tid".

Halve minutter opstår kun, når tiden deles mellem samtidige ture.

### A10. Tillæg (regnes af grundbeløbet)

Grundbeløbet er summen af grundprisens linjer: inkl. startgebyr og evt. "op til minimum". Ved en aftalt pris er det det aftalte beløb.

| Enhed | Beløb |
|---|---|
| kr | Værdien |
| % | Grundbeløb × værdi / 100. Altid af grundbeløbet, **aldrig af andre tillæg**. Flere %-tillæg lægges sammen, de ganges ikke |
| kr/t, ventetid | Ventetiden rundet op til påbegyndt kvarter × værdi / 60 |
| kr/t, andre kategorier | Timepris: de fakturerbare minutter. Andre modeller: turens tid efter deling, **uden** afrunding og pausefradrag. Uden tid: intet tillæg |
| Ekstra stop | Værdi × (stop - inkluderede). Standard er 2 inkluderede. Enheden er altid kr |

- Ventetidstillæg kommer kun med, når turen har ventetid.
- Tillæg beregnes kun, når der er et grundbeløb. Uden grundpris, tid eller antal kommer der ingen tillæg.

**Ventetidens vej til prisen.** Chaufføren angiver ventetid ved afslutning eller som rettelse bagefter.
- **Premium (eller basic med Økonomi):** ventetiden bliver en rettelse til godkendelse.
  - Kort ventetid kan godkendes automatisk (`auto_approve_waiting_min`).
  - Godkendt ventetid skrives i `fact_overrides.waiting_min` og prissættes.
  - Godkendelser advarer, hvis kunden intet ventetidstillæg har (så giver det 0 kr).
- **Basic uden Økonomi:** ventetiden gemmes kun på turen (`waiting_reported_min`) som oplysning til historik og eksport. Der er ingen godkendelse og ingen pris.

### A11. Aftalt/manuel pris og ekstra linjer

`price_override` med `mode: "fixed"` sættes som "Aftalt pris" i Ny tur eller som "Manuel pris" i Økonomi. Med den:

1. Tillæggene beregnes med det faste beløb som grundbeløb.
2. Alle tillæg vises som "… - indregnet i aftalt pris" med 0 kr. Undtagelse: **ventetid**, hvis "ventetid oveni" (`add_waiting`) er valgt. Ventetid kendes ikke, når prisen aftales.
3. Den faste pris gælder også, når ingen regel passer, eller når tid eller antal mangler. Status bliver ok, og markeringen er "Manuel pris". Kun en evt. "Minimum"-markering bevares.

Ekstra linjer (`extra_lines`) lægges til i begge tilstande. Ved "regler + ekstra linjer" (`mode: "rules"`) giver de kun en total, hvis reglerne selv giver en pris.

Admin skal altid skrive en begrundelse. Alt logges i `price_history`.

### A12. Resultat, status og forklaring

- **Total** = summen af linjerne, rundet til øre (`money`: 2 decimaler, halve øre op). Den findes kun ved status ok eller fast pris.
- **Status:**
  - `ok`;
  - `missing_rule` ("Mangler pris");
  - `missing_time` ("Mangler tid");
  - `missing_qty` ("Mangler antal").
- En tur uden total tæller ikke med i Rapportens sum. Den vises med et tal for "mangler".
- **Forklaring på "Mangler pris"** (`explain_missing`):
  - Den aktive grundpris med **færrest** betingelser, der ikke passer, vises. Står det lige, vises den mest specifikke.
  - Teksten nævner hver betingelse, der ikke passer, fx "materiale (turen har Beton + Træ, reglen gælder Beton)" eller "forgæves kørsel (ingen pris for forgæves kørsel)".
  - Regler der er slået fra, indgår ikke.
- **Markeringer** (`flags`):
  - "Minimum N min anvendt";
  - "Manuel pris";
  - "Hænger: automatisk, ikke bekræftet";
  - "Faktureret";
  - "Pris fra aftale oprettet efter turen …";
  - "Mangler start- eller sluttid";
  - "Start og slut er samme minut - ret tiden";
  - "Turen har intet antal i …".

### A13. Fakturering

Når ture markeres som faktureret, gemmes turens pris som et øjebliksbillede i `price_locked`: linjer, total, model, tid og markeringer.

- Prisen ændres herefter ikke af regler, rettelser eller godkendelser.
- Registreringerne kan heller ikke ændres (409): vægt, mængder, tider, hængere, billeder og stop.
- Ture uden pris springes over.
- Man fjerner markeringen for at rette.

### A14. Hvor priserne vises

| Sted | Endpoint | Hvad |
|---|---|---|
| Økonomi › Rapport | `GET /api/pricing/report` | Ture i perioden: kørt af firmaets chauffører, gennemført eller forgæves, filtreret på kørselsdato. Viser linjer, total, moms, fakturerbare timer, "mangler", hængere ikke bekræftet og ventende rettelser |
| Ture-siden | `GET /api/pricing/status` | Pris OK / Aftalt pris / Faktureret / Mangler pris (+ forklaring) / Rettelse venter. Uden beløb. En tur på timepris, der ikke er kørt endnu, er ikke "Mangler tid" |
| Prøv prisen | `POST /api/pricing/simulate` | Et tænkt scenarie med de nugældende regler. Kan også bruge en aftale, der ikke er gemt endnu (kladden vinder ved lighed). Viser, hvilke grundpriser der passer |
| Turens prisopbygning | `GET /api/pricing/tours/{id}` | Linjer, originale og rettede fakta, historik og rettelser |
| Ret pris/fakta | `PUT /api/pricing/tours/{id}/adjust` | Rettede fakta, fast beløb, ekstra linjer, begrundelse |
| Godkendelser | `GET /api/pricing/requests`, `POST …/decide` | Chaufførens rettelser. Kun godkendte påvirker prisen |
| Chaufføren | `GET /api/driver/tour-pricing` | Model, timepris, pause, afrunding, minimum. Aldrig beløb |

### A15. Kendte særheder (vigtige for fejlfinding)

1. **To regler med samme specificitet:** den senest rettede vinder. Det kan se tilfældigt ud. Gemmer man en aftale med præcis de samme betingelser som en eksisterende, svarer editoren 409 og viser konflikten.
2. **Kun ét tillæg pr. kategori.** To "Andet"-gebyrer kan ikke kombineres.
3. **"Fra en dato" følger oprettelsen.** Brug "Ture kørt fra en dato" ved prisstigninger, der skal følge kørselsdatoen.
4. **Lokationens helligdagskalender erstatter den egne** (den lægges ikke sammen med den).
5. **Tillæg i en prisaftale gælder ikke forgæves ture**, fordi de har udfald "gennemført".
6. **Pris pr. time på fast pris** bruger turens tid uden afrunding og uden pausefradrag. Teksten kan vise "45.0 min".
7. **"Ingen afrunding" runder halve minutter til lige tal** (bankers rounding). Det sker kun ved delt tid.
8. **Ventetid i prisen kommer kun fra godkendte rettelser** (`fact_overrides.waiting_min`), ikke fra den ventetid chaufføren selv oplyser.
9. **Tal i beløbsfelter læses dansk:** "1.000" er tusind, "1.000,50" er tusind og halvtreds øre, "1.5" er halvanden.

---

## Del B - Eksempler

Alle eksempler er regnet af `backend/pricing.py` og serverens hjælpefunktioner og kontrolleret mod
håndregnede facitter. Standardturen er en afhentning for Helsingør Forsyning (HF) på lokation 1101.
Materialet er Pap, dagen er en hverdag (tirsdag 20.10.2026), turen starter kl. 08:00 og er gennemført.
Den har ingen hænger, ingen ventetid og ingen ekstra stop. Hvert eksempel nævner kun det, der afviger.

<!-- Genereret af scripts/prisberegning_eksempler.py - 151 eksempler, alle kontrolleret mod prismotoren -->

### B1. Grundlæggende

Én tur, få regler. Standardturen er en almindelig afhentning (opgavetype Afhentning) for Helsingør Forsyning (HF) på lokation 1101, materiale Pap, en hverdag (tirsdag 20.10.2026) med start kl. 08:00, gennemført, uden hænger, ventetid og ekstra stop.

#### E1. Én generel fast pris

**Regler:**
- **Standardpris** - fast pris 950,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Standardpris: 950,00 kr
  - **I alt 950,00 kr** (ekskl. moms)

**Hvorfor:** Reglen har ingen betingelser, så den passer på alle gennemførte ture. Fast pris = beløbet.

#### E2. Ingen regler

**Regler:**
- (ingen regler)

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - **Ingen pris: Mangler pris** (turen tæller ikke med i summen)
  - Markeringer: Ingen grundpris-regel matcher turen
  - Forklaring i Rapport: "Der er ikke oprettet nogen grundpris endnu"

**Hvorfor:** Uden en grundpris kan turen ikke prissættes. Den står som "Mangler pris" og tæller ikke med i rapportens sum.

#### E3. Reglen er slået fra

**Regler:**
- **Gammel pris** - fast pris 950,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0. [SLÅET FRA]

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - **Ingen pris: Mangler pris** (turen tæller ikke med i summen)
  - Markeringer: Ingen grundpris-regel matcher turen
  - Forklaring i Rapport: "Der er ikke oprettet nogen grundpris endnu"

**Hvorfor:** En regel der er slået fra, deltager slet ikke - heller ikke i forklaringen. Derfor siger forklaringen "ikke oprettet nogen grundpris", selvom reglen findes.

#### E4. Kun et tillæg, ingen grundpris

**Regler:**
- **Weekendtillæg** - tillæg (Weekend): 500,00 kr. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Lørdag; start kl. 08:00

**Resultat:**
  - **Ingen pris: Mangler pris** (turen tæller ikke med i summen)
  - Markeringer: Ingen grundpris-regel matcher turen
  - Forklaring i Rapport: "Der er ikke oprettet nogen grundpris endnu"

**Hvorfor:** Tillæg lægges kun oven på en grundpris. Uden grundpris beregnes intet - heller ikke tillægget.


### B2. Overlappende grundpriser (specificitet)

Passer flere grundpriser på samme tur, vinder den mest specifikke. Point: kunde 64, lokation 32, leveringsadresse 16, opgavetype 8, materiale 4, containerstørrelse 2, prioritet 1, dagtype 1, hænger med/uden 1, antal hængere 2, tidsrum 1, udfald (andet end gennemført) 1. Point lægges sammen. Står det lige, vinder den senest rettede regel.

#### E5. Kundepris slår generel pris

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **HF-pris** - fast pris 1.200,00 kr. Gælder: kunde = Helsingør Forsyning. Specificitet 64.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - HF-pris: 1.200,00 kr
  - **I alt 1.200,00 kr** (ekskl. moms)

**Hvorfor:** Begge passer. HF-prisen har 64 point mod 0, så den vinder.

#### E6. Kunde slår lokation

**Regler:**
- **HF-pris** - fast pris 1.200,00 kr. Gælder: kunde = Helsingør Forsyning. Specificitet 64.
- **Lokation 1101** - fast pris 1.100,00 kr. Gælder: lokation = 1101. Specificitet 32.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - HF-pris: 1.200,00 kr
  - **I alt 1.200,00 kr** (ekskl. moms)

**Hvorfor:** Kunde (64) > lokation (32).

#### E7. Kunde slår lokation + materiale

**Regler:**
- **1101 Pap** - fast pris 1.050,00 kr. Gælder: lokation = 1101, materiale = Pap. Specificitet 36.
- **HF-pris** - fast pris 1.200,00 kr. Gælder: kunde = Helsingør Forsyning. Specificitet 64.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - HF-pris: 1.200,00 kr
  - **I alt 1.200,00 kr** (ekskl. moms)

**Hvorfor:** Lokation + materiale = 32 + 4 = 36, kunde = 64. En kundepris slår altid alt, der ikke nævner kunden.

#### E8. Kunde + lokation slår kunde

**Regler:**
- **HF-pris** - fast pris 1.200,00 kr. Gælder: kunde = Helsingør Forsyning. Specificitet 64.
- **HF på 1101** - fast pris 1.150,00 kr. Gælder: kunde = Helsingør Forsyning, lokation = 1101. Specificitet 96.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - HF på 1101: 1.150,00 kr
  - **I alt 1.150,00 kr** (ekskl. moms)

**Hvorfor:** 64 + 32 = 96 mod 64. Den mere præcise aftale vinder, også selvom den er billigere.

#### E9. Opgavetype slår materiale

**Regler:**
- **Byt container** - fast pris 800,00 kr. Gælder: opgavetype = Byt container. Specificitet 8.
- **Pap** - fast pris 700,00 kr. Gælder: materiale = Pap. Specificitet 4.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; opgavetype Byt container; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Byt container: 800,00 kr
  - **I alt 800,00 kr** (ekskl. moms)

**Hvorfor:** Opgavetype (8) > materiale (4).

#### E10. Leveringsadresse slår opgavetype + materiale + størrelse

**Regler:**
- **HCS** - fast pris 1.300,00 kr. Gælder: leveringsadresse = "HCS A/S Helsingør". Specificitet 16.
- **Afhentning Pap 20 m³** - fast pris 900,00 kr. Gælder: opgavetype = Afhentning, materiale = Pap, containerstørrelse = "Åben container 20 m³". Specificitet 14.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; containerstørrelse "Åben container 20 m³"; leveringsadresse "HCS A/S Helsingør"; start kl. 08:00

**Resultat:**
  - HCS: 1.300,00 kr
  - **I alt 1.300,00 kr** (ekskl. moms)

**Hvorfor:** 16 > 8 + 4 + 2 = 14. Vægtene er valgt, så en højere betingelse altid slår alle lavere tilsammen.

#### E11. Lige specifikke: den senest rettede vinder

**Regler:**
- **Pris A** - fast pris 900,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0. [senest rettet 2026-03-01]
- **Pris B** - fast pris 950,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0. [senest rettet 2026-05-01]

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Pris B: 950,00 kr
  - **I alt 950,00 kr** (ekskl. moms)

**Hvorfor:** Begge har 0 point. Så vinder den, der senest er rettet (updated_at). Det er en faldgrube: to generelle priser bør ikke findes samtidig. Editoren advarer, når betingelserne er helt ens.

#### E12. Lige specifikke på hver sin led

**Regler:**
- **Haster-pris** - fast pris 1.100,00 kr. Gælder: prioritet = Haster. Specificitet 1. [senest rettet 2026-02-01]
- **Hverdagspris** - fast pris 1.000,00 kr. Gælder: dagtype = Hverdag. Specificitet 1. [senest rettet 2026-04-01]

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; prioritet Haster; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Hverdagspris: 1.000,00 kr
  - **I alt 1.000,00 kr** (ekskl. moms)

**Hvorfor:** Prioritet og dagtype giver 1 point hver. En haster-tur på en hverdag passer på begge, og så vinder den senest rettede - her hverdagsprisen. Vil man have et haster-pristrin, er et haster-TILLÆG det rigtige.

#### E13. Kundepris for en anden kunde gælder ikke

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **ARGO-pris** - fast pris 1.500,00 kr. Gælder: kunde = ARGO. Specificitet 64.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - **I alt 1.000,00 kr** (ekskl. moms)

**Hvorfor:** ARGO-reglen passer ikke på en HF-tur. Den generelle pris bruges.

#### E14. Lokationspris for en anden lokation

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Lokation 1102** - fast pris 1.250,00 kr. Gælder: lokation = 1102. Specificitet 32.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - **I alt 1.000,00 kr** (ekskl. moms)

**Hvorfor:** Turen er på 1101.

#### E15. Flere kunder i samme betingelse

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **HF og ARGO** - fast pris 1.150,00 kr. Gælder: kunde = Helsingør Forsyning eller ARGO. Specificitet 64.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - HF og ARGO: 1.150,00 kr
  - **I alt 1.150,00 kr** (ekskl. moms)

**Hvorfor:** En liste betyder "en af disse". Specificiteten er stadig 64 - antallet af værdier tæller ikke.

#### E16. Kunde + hverdag slår kunde (hverdag)

**Regler:**
- **HF** - fast pris 1.200,00 kr. Gælder: kunde = Helsingør Forsyning. Specificitet 64.
- **HF hverdag** - fast pris 1.100,00 kr. Gælder: kunde = Helsingør Forsyning, dagtype = Hverdag. Specificitet 65.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - HF hverdag: 1.100,00 kr
  - **I alt 1.100,00 kr** (ekskl. moms)

**Hvorfor:** 65 > 64 på en hverdag.

#### E17. Kunde + hverdag passer ikke en lørdag

**Regler:**
- **HF** - fast pris 1.200,00 kr. Gælder: kunde = Helsingør Forsyning. Specificitet 64.
- **HF hverdag** - fast pris 1.100,00 kr. Gælder: kunde = Helsingør Forsyning, dagtype = Hverdag. Specificitet 65.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Lørdag; start kl. 08:00

**Resultat:**
  - HF: 1.200,00 kr
  - **I alt 1.200,00 kr** (ekskl. moms)

**Hvorfor:** Lørdag passer kun den brede HF-regel.

#### E18. Kørselsdato uden for reglens periode

**Regler:**
- **HF 2026** - fast pris 1.200,00 kr. Gælder: kunde = Helsingør Forsyning. Specificitet 64. [kørselsdato … til 2026-09-30]
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - **I alt 1.000,00 kr** (ekskl. moms)

**Hvorfor:** Reglen gælder ture KØRT til og med 30.09.2026. Turen er kørt 20.10.2026, så den generelle pris bruges.

#### E19. Periode udløbet og ingen anden pris

**Regler:**
- **HF 2026** - fast pris 1.200,00 kr. Gælder: kunde = Helsingør Forsyning. Specificitet 64. [kørselsdato … til 2026-09-30]

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - **Ingen pris: Mangler pris** (turen tæller ikke med i summen)
  - Markeringer: Ingen grundpris-regel matcher turen
  - Forklaring i Rapport: "Nærmeste regel "HF 2026" passer ikke på: kørselsdatoen er uden for reglens periode"

**Hvorfor:** Rapporten forklarer, hvad der mangler.

#### E20. Containerstørrelse matches uden hensyn til store/små bogstaver og mellemrum

**Regler:**
- **20 m³** - fast pris 900,00 kr. Gælder: containerstørrelse = "Åben container 20 m³". Specificitet 2.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; containerstørrelse "åben  container 20 M³"; start kl. 08:00

**Resultat:**
  - 20 m³: 900,00 kr
  - **I alt 900,00 kr** (ekskl. moms)

**Hvorfor:** Tekst-betingelser (containerstørrelse, leveringsadresse, materiale) sammenlignes med små bogstaver og enkelte mellemrum.

#### E21. Leveringsadresse matches på navnet

**Regler:**
- **HCS** - fast pris 1.300,00 kr. Gælder: leveringsadresse = "HCS A/S Helsingør". Specificitet 16.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; leveringsadresse "hcs a/s  helsingør"; start kl. 08:00

**Resultat:**
  - HCS: 1.300,00 kr
  - **I alt 1.300,00 kr** (ekskl. moms)

**Hvorfor:** Leveringsadressen matches på modtagerens navn, ikke på gade og nummer. Samme modtager på flere pladser prissættes derfor kun én gang.


### B3. Tillæg - og når flere tillæg overlapper

Tillæg har en kategori (Weekend, Helligdag, Haster, Hænger, Aften/nat, Ventetid, Ekstra stop, Andet). Pr. kategori bruges kun den mest specifikke regel, der passer (samme pointsystem). Forskellige kategorier lægges sammen.

#### E22. Weekendtillæg en lørdag

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekendtillæg** - tillæg (Weekend): 500,00 kr. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Lørdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Weekendtillæg: 500,00 kr
  - **I alt 1.500,00 kr** (ekskl. moms)

**Hvorfor:** 1.000 + 500.

#### E23. Weekendtillæg en hverdag

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekendtillæg** - tillæg (Weekend): 500,00 kr. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - **I alt 1.000,00 kr** (ekskl. moms)

**Hvorfor:** Tillægget passer ikke en hverdag.

#### E24. Kundens eget weekendtillæg erstatter det generelle

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekendtillæg** - tillæg (Weekend): 500,00 kr. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.
- **Weekend HF** - tillæg (Weekend): 300,00 kr. Gælder: kunde = Helsingør Forsyning, dagtype = Lørdag eller Søndag. Specificitet 65.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Lørdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Weekend HF: 300,00 kr
  - **I alt 1.300,00 kr** (ekskl. moms)

**Hvorfor:** Begge weekendtillæg passer. HF-tillægget har 65 point mod 1 og vinder. Det generelle bruges IKKE også - ingen dobbeltopkrævning.

#### E25. En anden kunde får det generelle

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekendtillæg** - tillæg (Weekend): 500,00 kr. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.
- **Weekend HF** - tillæg (Weekend): 300,00 kr. Gælder: kunde = Helsingør Forsyning, dagtype = Lørdag eller Søndag. Specificitet 65.

**Turen:** kunde ARGO; lokation 1101; materiale Pap; dagtype Lørdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Weekendtillæg: 500,00 kr
  - **I alt 1.500,00 kr** (ekskl. moms)

**Hvorfor:** HF-tillægget passer ikke på ARGO.

#### E26. Kunde fritaget for weekendtillæg

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekendtillæg** - tillæg (Weekend): 500,00 kr. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.
- **Weekend HF fritaget** - tillæg (Weekend): 0,00 kr. Gælder: kunde = Helsingør Forsyning, dagtype = Lørdag eller Søndag. Specificitet 65.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Lørdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Weekend HF fritaget: 0,00 kr
  - **I alt 1.000,00 kr** (ekskl. moms)

**Hvorfor:** Et kundespecifikt tillæg på 0 kr vinder over det generelle og fritager kunden. Linjen vises med 0 kr, så man kan se hvorfor.

#### E27. Forskellige kategorier lægges sammen

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekendtillæg** - tillæg (Weekend): 500,00 kr. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.
- **Haster** - tillæg (Haster): 250,00 kr. Gælder: prioritet = Haster. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; prioritet Haster; dagtype Lørdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Haster: 250,00 kr
  - Weekendtillæg: 500,00 kr
  - **I alt 1.750,00 kr** (ekskl. moms)

**Hvorfor:** 1.000 + 500 (weekend) + 250 (haster).

#### E28. Helligdag på en lørdag: kun helligdagstillæg

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekendtillæg** - tillæg (Weekend): 500,00 kr. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.
- **Helligdag** - tillæg (Helligdag): 800,00 kr. Gælder: dagtype = Helligdag. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Helligdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Helligdag: 800,00 kr
  - **I alt 1.800,00 kr** (ekskl. moms)

**Hvorfor:** Dagtyperne udelukker hinanden. 26.12.2026 er en lørdag og 2. juledag, så dagtypen er "Helligdag" - ikke "Lørdag". Weekendtillægget passer derfor ikke.

#### E29. Lørdagstillæg gælder ikke søndag

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Lørdag** - tillæg (Weekend): 400,00 kr. Gælder: dagtype = Lørdag. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Søndag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - **I alt 1.000,00 kr** (ekskl. moms)

**Hvorfor:** Tillægget nævner kun lørdag.

#### E30. Tillæg uden betingelser gælder altid

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Miljøgebyr** - tillæg (Andet): 75,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Miljøgebyr: 75,00 kr
  - **I alt 1.075,00 kr** (ekskl. moms)

**Hvorfor:** Et tillæg uden betingelser lægges på alle ture.

#### E31. To tillæg i samme kategori: kun ét bruges

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Miljøgebyr** - tillæg (Andet): 75,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Brobizz** - tillæg (Andet): 120,00 kr. Gælder: lokation = 1101. Specificitet 32.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Brobizz: 120,00 kr
  - **I alt 1.120,00 kr** (ekskl. moms)

**Hvorfor:** Begge er kategori "Andet". Brobizz (32 point) vinder, og miljøgebyret bortfalder. Skal begge opkræves, skal de have hver sin kategori.

#### E32. To lige tillæg i samme kategori

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Gebyr A** - tillæg (Andet): 50,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0. [senest rettet 2026-03-01]
- **Gebyr B** - tillæg (Andet): 60,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0. [senest rettet 2026-06-01]

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Gebyr B: 60,00 kr
  - **I alt 1.060,00 kr** (ekskl. moms)

**Hvorfor:** Lige specifikke: den senest rettede vinder.

#### E33. Specifikt haster-tillæg for materialet

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Haster** - tillæg (Haster): 200,00 kr. Gælder: prioritet = Haster. Specificitet 1.
- **Haster Pap** - tillæg (Haster): 300,00 kr. Gælder: materiale = Pap, prioritet = Haster. Specificitet 5.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; prioritet Haster; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Haster Pap: 300,00 kr
  - **I alt 1.300,00 kr** (ekskl. moms)

**Hvorfor:** Haster Pap har 1 + 4 = 5 point mod 1.

#### E34. Kundetillæg for en anden kunde

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekendtillæg** - tillæg (Weekend): 500,00 kr. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.
- **Weekend ARGO** - tillæg (Weekend): 250,00 kr. Gælder: kunde = ARGO, dagtype = Lørdag eller Søndag. Specificitet 65.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Lørdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Weekendtillæg: 500,00 kr
  - **I alt 1.500,00 kr** (ekskl. moms)

**Hvorfor:** ARGO-tillægget passer ikke på HF; det generelle gælder.

#### E35. Procent og kroner i forskellige kategorier

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekend 25 %** - tillæg (Weekend): 25 % af grundprisen. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.
- **Haster** - tillæg (Haster): 200,00 kr. Gælder: prioritet = Haster. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; prioritet Haster; dagtype Lørdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Haster: 200,00 kr
  - Weekend 25 % (25%): 250,00 kr
  - **I alt 1.450,00 kr** (ekskl. moms)

**Hvorfor:** 25 % af 1.000 = 250, plus 200.


### B4. Procenttillæg

Et %-tillæg regnes ALTID af grundprisen (inkl. startgebyr og evt. op til minimumsbeløb) - aldrig af andre tillæg. Flere %-tillæg lægges sammen, de ganges ikke.

#### E36. Haster 15 %

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Haster 15 %** - tillæg (Haster): 15 % af grundprisen. Gælder: prioritet = Haster. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; prioritet Haster; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Haster 15 % (15%): 150,00 kr
  - **I alt 1.150,00 kr** (ekskl. moms)

**Hvorfor:** 15 % af 1.000.

#### E37. Procent af timepris med startgebyr

**Regler:**
- **Timepris** - timepris 600 kr/t, startgebyr 200,00 kr, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekend 20 %** - tillæg (Weekend): 20 % af grundprisen. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Lørdag; start kl. 08:00; tid 90 min

**Resultat:**
  - Startgebyr: 200,00 kr
  - Timepris (1t 30m × 600 kr/t): 900,00 kr
  - Weekend 20 % (20%): 220,00 kr
  - **I alt 1.320,00 kr** (ekskl. moms)

**Hvorfor:** Grundpris = 200 + 600 × 90/60 = 1.100. 20 % af 1.100 = 220.

#### E38. Procent af minimumsbeløb

**Regler:**
- **Timepris** - timepris 600 kr/t, minimumsbeløb 500,00 kr, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Haster 10 %** - tillæg (Haster): 10 % af grundprisen. Gælder: prioritet = Haster. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; prioritet Haster; dagtype Hverdag; start kl. 08:00; tid 30 min

**Resultat:**
  - Timepris (0t 30m × 600 kr/t): 300,00 kr
  - Op til minimumsbeløb: 200,00 kr
  - Haster 10 % (10%): 50,00 kr
  - **I alt 550,00 kr** (ekskl. moms)

**Hvorfor:** 30 min = 300 kr, løftes til minimum 500. 10 % af 500 = 50.

#### E39. To procenttillæg ganges ikke

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekend 20 %** - tillæg (Weekend): 20 % af grundprisen. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.
- **Haster 10 %** - tillæg (Haster): 10 % af grundprisen. Gælder: prioritet = Haster. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; prioritet Haster; dagtype Lørdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Haster 10 % (10%): 100,00 kr
  - Weekend 20 % (20%): 200,00 kr
  - **I alt 1.300,00 kr** (ekskl. moms)

**Hvorfor:** 200 + 100 = 300 (ikke 1.000 × 1,2 × 1,1).

#### E40. Procent af pris pr. container

**Regler:**
- **Pr. container** - 400,00 kr pr. container. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekend 10 %** - tillæg (Weekend): 10 % af grundprisen. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Lørdag; start kl. 08:00; 3 containere

**Resultat:**
  - Pr. container (3 stk.): 1.200,00 kr
  - Weekend 10 % (10%): 120,00 kr
  - **I alt 1.320,00 kr** (ekskl. moms)

**Hvorfor:** 3 × 400 = 1.200. 10 % = 120.

#### E41. Procent på en aftalt pris er indregnet

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekend 25 %** - tillæg (Weekend): 25 % af grundprisen. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Lørdag; start kl. 08:00; Aftalt pris 2.000,00 kr

**Resultat:**
  - Aftalt pris: 2.000,00 kr
  - Weekend 25 % (25%) - indregnet i aftalt pris: 0,00 kr
  - **I alt 2.000,00 kr** (ekskl. moms)
  - Markeringer: Manuel pris

**Hvorfor:** Med aftalt pris beregnes tillæggene (500), men de vises som "indregnet i aftalt pris" med 0 kr. Kun ventetid kan lægges oveni (se B9).


### B5. Timepris

Fakturerbar tid = turens tid (efter deling med samtidige ture) minus pause (hvis reglen siger det) -> afrunding -> minimum minutter. Beløb = startgebyr + timepris × minutter/60, løftet til evt. minimumsbeløb.

#### E42. Uden afrunding

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 95 min

**Resultat:**
  - Timepris (1t 35m × 600 kr/t): 950,00 kr
  - **I alt 950,00 kr** (ekskl. moms)

**Hvorfor:** 95 min × 600/60 = 950.

#### E43. Op til nærmeste 15 min

**Regler:**
- **Timepris** - timepris 600 kr/t, op til 15 min, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 95 min

**Resultat:**
  - Timepris (1t 45m × 600 kr/t): 1.050,00 kr
  - **I alt 1.050,00 kr** (ekskl. moms)

**Hvorfor:** 95 -> 105 min. 105 × 10 = 1.050.

#### E44. Nærmeste 15 min (ned)

**Regler:**
- **Timepris** - timepris 600 kr/t, nærmeste til 15 min, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 95 min

**Resultat:**
  - Timepris (1t 30m × 600 kr/t): 900,00 kr
  - **I alt 900,00 kr** (ekskl. moms)

**Hvorfor:** 95/15 = 6,33 -> 6 kvarterer = 90 min.

#### E45. Nærmeste 15 min, præcis på halvdelen

**Regler:**
- **Timepris** - timepris 600 kr/t, nærmeste til 15 min, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 97,5 min

**Resultat:**
  - Timepris (1t 45m × 600 kr/t): 1.050,00 kr
  - **I alt 1.050,00 kr** (ekskl. moms)

**Hvorfor:** 97,5/15 = 6,5. Halve rundes op -> 7 kvarterer = 105 min. (Halve minutter opstår, når tid deles mellem samtidige ture.)

#### E46. Ned til 30 min

**Regler:**
- **Timepris** - timepris 600 kr/t, ned til 30 min, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 95 min

**Resultat:**
  - Timepris (1t 30m × 600 kr/t): 900,00 kr
  - **I alt 900,00 kr** (ekskl. moms)

**Hvorfor:** 95 -> 90 min.

#### E47. Ingen afrunding, halvt minut (22,5)

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 22,5 min

**Resultat:**
  - Timepris (0t 22m × 600 kr/t): 220,00 kr
  - **I alt 220,00 kr** (ekskl. moms)

**Hvorfor:** Uden afrunding rundes til hele minutter med Pythons round(), der runder halve til nærmeste LIGE tal: 22,5 -> 22. Det sker kun ved delt tid.

#### E48. Ingen afrunding, halvt minut (23,5)

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 23,5 min

**Resultat:**
  - Timepris (0t 24m × 600 kr/t): 240,00 kr
  - **I alt 240,00 kr** (ekskl. moms)

**Hvorfor:** 23,5 -> 24 (lige tal).

#### E49. Op til hele minutter

**Regler:**
- **Timepris** - timepris 600 kr/t, op til 1 min, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 22,5 min

**Resultat:**
  - Timepris (0t 23m × 600 kr/t): 230,00 kr
  - **I alt 230,00 kr** (ekskl. moms)

**Hvorfor:** "Op til 1 min": 22,5 -> 23.

#### E50. Minimum 60 minutter

**Regler:**
- **Timepris** - timepris 600 kr/t, minimum 60 min, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 35 min

**Resultat:**
  - Timepris (1t 00m × 600 kr/t): 600,00 kr
  - **I alt 600,00 kr** (ekskl. moms)
  - Markeringer: Minimum 60 min anvendt

**Hvorfor:** 35 min løftes til 60.

#### E51. Afrunding før minimum (ingen markering)

**Regler:**
- **Timepris** - timepris 600 kr/t, minimum 60 min, op til 15 min, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 50 min

**Resultat:**
  - Timepris (1t 00m × 600 kr/t): 600,00 kr
  - **I alt 600,00 kr** (ekskl. moms)

**Hvorfor:** 50 -> 60 ved afrundingen. Minimum er dermed nået, så der kommer ingen markering.

#### E52. Afrunding, så minimum

**Regler:**
- **Timepris** - timepris 600 kr/t, minimum 60 min, op til 15 min, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 40 min

**Resultat:**
  - Timepris (1t 00m × 600 kr/t): 600,00 kr
  - **I alt 600,00 kr** (ekskl. moms)
  - Markeringer: Minimum 60 min anvendt

**Hvorfor:** 40 -> 45 (afrunding) -> 60 (minimum).

#### E53. Startgebyr

**Regler:**
- **Timepris** - timepris 600 kr/t, startgebyr 200,00 kr, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 60 min

**Resultat:**
  - Startgebyr: 200,00 kr
  - Timepris (1t 00m × 600 kr/t): 600,00 kr
  - **I alt 800,00 kr** (ekskl. moms)

**Hvorfor:** 200 + 60 min × 10 kr = 800. To linjer.

#### E54. Minimumsbeløb

**Regler:**
- **Timepris** - timepris 600 kr/t, startgebyr 100,00 kr, minimumsbeløb 500,00 kr, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 20 min

**Resultat:**
  - Startgebyr: 100,00 kr
  - Timepris (0t 20m × 600 kr/t): 200,00 kr
  - Op til minimumsbeløb: 200,00 kr
  - **I alt 500,00 kr** (ekskl. moms)

**Hvorfor:** 100 + 20 min (200) = 300. Løftes med 200 til 500.

#### E55. Pause trækkes fra

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 120 min, heraf 30 min pause

**Resultat:**
  - Timepris (1t 30m × 600 kr/t): 900,00 kr
  - **I alt 900,00 kr** (ekskl. moms)

**Hvorfor:** 120 min, heraf 30 min pause -> 90 min.

#### E56. Pause trækkes ikke fra

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes ikke fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 120 min, heraf 30 min pause

**Resultat:**
  - Timepris (2t 00m × 600 kr/t): 1.200,00 kr
  - **I alt 1.200,00 kr** (ekskl. moms)

**Hvorfor:** Reglen siger at pausen ikke trækkes fra -> 120 min.

#### E57. Admin: pausen skal trækkes fra på denne tur

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes ikke fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; admin: pause trækkes fra; tid 120 min, heraf 30 min pause

**Resultat:**
  - Timepris (1t 30m × 600 kr/t): 900,00 kr
  - **I alt 900,00 kr** (ekskl. moms)

**Hvorfor:** Turens rettelse ("pause tæller/tæller ikke") vinder over reglen.

#### E58. Admin: pausen skal ikke trækkes fra

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; admin: pause trækkes ikke fra; tid 120 min, heraf 30 min pause

**Resultat:**
  - Timepris (2t 00m × 600 kr/t): 1.200,00 kr
  - **I alt 1.200,00 kr** (ekskl. moms)

**Hvorfor:** Omvendt.

#### E59. Mangler tid

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekendtillæg** - tillæg (Weekend): 500,00 kr. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Lørdag; start kl. 08:00

**Resultat:**
  - **Ingen pris: Mangler tid** (turen tæller ikke med i summen)
  - Markeringer: Mangler start- eller sluttid

**Hvorfor:** Timepris kræver start og slut. Uden tid ingen grundpris - og derfor heller ingen tillæg.

#### E60. Over midnat

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 22:30; tid 165 min

**Resultat:**
  - Timepris (2t 45m × 600 kr/t): 1.650,00 kr
  - **I alt 1.650,00 kr** (ekskl. moms)

**Hvorfor:** Start 22:30, slut 01:15. Slut før start = næste dag: 165 min.

#### E61. Minimum efter pause

**Regler:**
- **Timepris** - timepris 600 kr/t, minimum 60 min, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 75 min, heraf 30 min pause

**Resultat:**
  - Timepris (1t 00m × 600 kr/t): 600,00 kr
  - **I alt 600,00 kr** (ekskl. moms)
  - Markeringer: Minimum 60 min anvendt

**Hvorfor:** 75 - 30 pause = 45 -> minimum 60.


### B5b. Serverens tidsberegning

#### E62. Over midnat i serveren

På vej 22:30, afsluttet 01:15: 165 min -> 1.650,00 kr.

#### E63. Start og slut i samme minut (rettet 20.10.2026)

Start 10:00, slut 10:00. Før blev det regnet som et helt døgn (24 timer × 600 = 14.400 kr). Nu: "Mangler tid" med markeringen "Start og slut er samme minut - ret tiden", så tiden rettes før fakturering.


### B6. Samtidige ture og pauser

Kører samme chauffør flere ture samtidig (fx flere containere på én hænger), deles de overlappende minutter ligeligt mellem turene (indstillingen "split", standard). Med "full" får hver tur hele tiden. Pauser fra chaufførens Tid-registrering deles på samme måde. Kun samme chauffør og samme kørselsdato tæller.

#### E64. To ture helt samtidig

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Pauser:** ingen. **Tilstand:** split

| Tur | Tid | Minutter i alt | Minutter efter deling | Heraf pause | Pris |
|---|---|---|---|---|---|
| A | 08:00-10:00 | 120 | 60 | 0 | 600,00 kr |
| B | 08:00-10:00 | 120 | 60 | 0 | 600,00 kr |

**Hvorfor:** 120 minutter med to ture -> 60 til hver. Kunderne betaler tilsammen for de 2 timer, chaufføren brugte.

#### E65. Delvist overlap

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Pauser:** ingen. **Tilstand:** split

| Tur | Tid | Minutter i alt | Minutter efter deling | Heraf pause | Pris |
|---|---|---|---|---|---|
| A | 08:00-10:00 | 120 | 90 | 0 | 900,00 kr |
| B | 09:00-11:00 | 120 | 90 | 0 | 900,00 kr |

**Hvorfor:** A: 60 alene + halvdelen af 60 fælles = 90. B ligeså.

#### E66. Delvist overlap, tilstand "full"

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Pauser:** ingen. **Tilstand:** full

| Tur | Tid | Minutter i alt | Minutter efter deling | Heraf pause | Pris |
|---|---|---|---|---|---|
| A | 08:00-10:00 | 120 | 120 | 0 | 1.200,00 kr |
| B | 09:00-11:00 | 120 | 120 | 0 | 1.200,00 kr |

**Hvorfor:** Hver tur får hele sin tid. Den fælles time betales to gange.

#### E67. Tre ture

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Pauser:** ingen. **Tilstand:** split

| Tur | Tid | Minutter i alt | Minutter efter deling | Heraf pause | Pris |
|---|---|---|---|---|---|
| A | 08:00-11:00 | 180 | 130 | 0 | 1.300,00 kr |
| B | 09:00-10:00 | 60 | 25 | 0 | 250,00 kr |
| C | 09:30-10:30 | 60 | 25 | 0 | 250,00 kr |

**Hvorfor:** 08-09 A alene (60). 09-09:30 A+B (15 hver). 09:30-10 A+B+C (10 hver). 10-10:30 A+C (15 hver). 10:30-11 A alene (30). A = 130, B = 25, C = 25. I alt 180 = de 3 timer chaufføren var i gang.

#### E68. Pause mens to ture kører

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Pauser:** 09:00-09:30. **Tilstand:** split

| Tur | Tid | Minutter i alt | Minutter efter deling | Heraf pause | Pris |
|---|---|---|---|---|---|
| A | 08:00-10:00 | 120 | 60 | 15 | 450,00 kr |
| B | 08:00-10:00 | 120 | 60 | 15 | 450,00 kr |

**Hvorfor:** Hver tur får 60 min, heraf 15 min af pausen (30 min delt på to). 60 - 15 = 45 min.

#### E69. Pause uden for turen

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Pauser:** 12:00-12:30. **Tilstand:** split

| Tur | Tid | Minutter i alt | Minutter efter deling | Heraf pause | Pris |
|---|---|---|---|---|---|
| A | 08:00-10:00 | 120 | 120 | 0 | 1.200,00 kr |

**Hvorfor:** Pausen 12:00-12:30 ligger ikke i turen og påvirker den ikke.

#### E70. Tillæg pr. time på en tur med fast pris

**Regler:**
- **Fast pris** - fast pris 800,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Kran** - tillæg (Andet): 120 kr/t. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; tid 45 min (af 60 min før deling med samtidige ture)

**Resultat:**
  - Fast pris: 800,00 kr
  - Kran (45.0 min × 120 kr/t): 90,00 kr
  - **I alt 890,00 kr** (ekskl. moms)

**Hvorfor:** Fast pris har ingen fakturerbar tid. Et kr/t-tillæg (ikke ventetid) bruger så turens tid efter deling - UDEN afrunding og UDEN pausefradrag: 45 min × 120/60 = 90. (Teksten viser "45.0 min".)


### B7. Pris pr. container og pr. enhed

#### E71. Pr. container, 3 containere

**Regler:**
- **Pr. container** - 350,00 kr pr. container. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; 3 containere

**Resultat:**
  - Pr. container (3 stk.): 1.050,00 kr
  - **I alt 1.050,00 kr** (ekskl. moms)

**Hvorfor:** 3 × 350.

#### E72. Pr. container, ingen antal

**Regler:**
- **Pr. container** - 350,00 kr pr. container. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; 0 containere

**Resultat:**
  - Pr. container (1 stk.): 350,00 kr
  - **I alt 350,00 kr** (ekskl. moms)

**Hvorfor:** Mindst 1 container.

#### E73. Pr. enhed, planlagt antal

**Regler:**
- **Palletakst** - 45,00 kr pr. paller. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; opgavetype Levering; dagtype Hverdag; start kl. 08:00; antal: 12 paller (planlagt)

**Resultat:**
  - Palletakst (12 paller × 45 kr, planlagt): 540,00 kr
  - **I alt 540,00 kr** (ekskl. moms)

**Hvorfor:** 12 paller × 45. Uden registreret antal bruges det planlagte.

#### E74. Pr. enhed, registreret antal

**Regler:**
- **Palletakst** - 45,00 kr pr. paller. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; opgavetype Levering; dagtype Hverdag; start kl. 08:00; antal: 11 paller (registreret)

**Resultat:**
  - Palletakst (11 paller × 45 kr, registreret): 495,00 kr
  - **I alt 495,00 kr** (ekskl. moms)

**Hvorfor:** Chaufføren registrerede 11 - det registrerede antal vinder over det planlagte.

#### E75. Pr. enhed med minimumsbeløb

**Regler:**
- **Palletakst** - 45,00 kr pr. paller, minimum 600,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; opgavetype Levering; dagtype Hverdag; start kl. 08:00; antal: 12 paller (planlagt)

**Resultat:**
  - Palletakst (12 paller × 45 kr, planlagt): 540,00 kr
  - Op til minimumsbeløb: 60,00 kr
  - **I alt 600,00 kr** (ekskl. moms)

**Hvorfor:** 540 løftes til 600.

#### E76. Pr. enhed, turen har ikke enheden

**Regler:**
- **Palletakst** - 45,00 kr pr. paller. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekendtillæg** - tillæg (Weekend): 500,00 kr. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; opgavetype Levering; dagtype Lørdag; start kl. 08:00; antal: 5 kolli (planlagt)

**Resultat:**
  - **Ingen pris: Mangler antal** (turen tæller ikke med i summen)
  - Markeringer: Turen har intet antal i paller

**Hvorfor:** Reglen tæller paller, turen har kun kolli. "Mangler antal" - og så heller ingen tillæg.

#### E77. Pr. enhed, enhedens navn skrevet anderledes

**Regler:**
- **Palletakst** - 45,00 kr pr. Paller . Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; opgavetype Levering; dagtype Hverdag; start kl. 08:00; antal: 4 paller (planlagt)

**Resultat:**
  - Palletakst (4 Paller  × 45 kr): 180,00 kr
  - **I alt 180,00 kr** (ekskl. moms)

**Hvorfor:** Enheden sammenlignes med små bogstaver og uden ekstra mellemrum.


### B7b. Hvad turen tæller som (containere, enheder, stop)

#### E78. Containertur med to indholdslinjer

Linjer: "Pap" (ingen enhed) og "Plast" 3 stk. En linje tæller som 1 container, men en linje i stk/containere tæller sit antal: 1 + 3 = **4** containere. Med 350 kr pr. container: 1.400,00 kr. Materialerne er Pap + Plast.

#### E79. Varetur: samme enhed på to linjer, kun den ene registreret

Køkken: planlagt 5, registreret 6. Bad: planlagt 7 (enheden stavet "Paller"). Antal paller = 6 + 7 = **13**, kilde "delvist registreret". 45 kr pr. palle: 585,00 kr.

#### E80. Antal stop

Tur uden stop-liste = **2** stop (afhentning + aflevering). Tre stop, hvor chaufføren selv har tilføjet det tredje og planlæggeren ikke har godkendt det = **2**. Når det er godkendt = **3**.


### B8. Hængere

#### E81. Hængertillæg

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Hænger** - tillæg (Hænger): 300,00 kr. Gælder: med hænger. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; 1 hænger(e); start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Hænger: 300,00 kr
  - **I alt 1.300,00 kr** (ekskl. moms)

**Hvorfor:** 1.000 + 300.

#### E82. Pris efter antal hængere: 2

**Regler:**
- **Uden hænger** - fast pris 500,00 kr. Gælder: uden hænger. Specificitet 1.
- **1 hænger** - fast pris 700,00 kr. Gælder: antal hængere = 1. Specificitet 2.
- **2 hængere** - fast pris 1.100,00 kr. Gælder: antal hængere = 2. Specificitet 2.
- **3+ hængere** - fast pris 1.500,00 kr. Gælder: antal hængere = 3+. Specificitet 2.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; 2 hænger(e); start kl. 08:00

**Resultat:**
  - 2 hængere: 1.100,00 kr
  - **I alt 1.100,00 kr** (ekskl. moms)

**Hvorfor:** Kun "2 hængere" passer. 2 hængere koster ikke nødvendigvis det dobbelte.

#### E83. Pris efter antal hængere: 4

**Regler:**
- **Uden hænger** - fast pris 500,00 kr. Gælder: uden hænger. Specificitet 1.
- **1 hænger** - fast pris 700,00 kr. Gælder: antal hængere = 1. Specificitet 2.
- **2 hængere** - fast pris 1.100,00 kr. Gælder: antal hængere = 2. Specificitet 2.
- **3+ hængere** - fast pris 1.500,00 kr. Gælder: antal hængere = 3+. Specificitet 2.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; 4 hænger(e); start kl. 08:00

**Resultat:**
  - 3+ hængere: 1.500,00 kr
  - **I alt 1.500,00 kr** (ekskl. moms)

**Hvorfor:** "3+" dækker 3 og derover.

#### E84. Pris efter antal hængere: 0

**Regler:**
- **Uden hænger** - fast pris 500,00 kr. Gælder: uden hænger. Specificitet 1.
- **1 hænger** - fast pris 700,00 kr. Gælder: antal hængere = 1. Specificitet 2.
- **2 hængere** - fast pris 1.100,00 kr. Gælder: antal hængere = 2. Specificitet 2.
- **3+ hængere** - fast pris 1.500,00 kr. Gælder: antal hængere = 3+. Specificitet 2.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Uden hænger: 500,00 kr
  - **I alt 500,00 kr** (ekskl. moms)

**Hvorfor:** Kun "Uden hænger" passer.

#### E85. Antal hængere slår "med hænger"

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Hænger** - tillæg (Hænger): 300,00 kr. Gælder: med hænger. Specificitet 1.
- **2 hængere** - tillæg (Hænger): 450,00 kr. Gælder: antal hængere = 2. Specificitet 2.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; 2 hænger(e); start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - 2 hængere: 450,00 kr
  - **I alt 1.450,00 kr** (ekskl. moms)

**Hvorfor:** Samme kategori. Antal (2 point) > med/uden (1 point).


### B8b. Hvor antallet af hængere kommer fra

#### E86. Rækkefølgen for hængere

Godkendt/admin-rettet antal > ældre godkendt ja/nej > chaufførens oplyste antal > planlagt antal > ja/nej på turen.

| Situation | Antal i prisen | Kilde | Bekræftet |
|---|---|---|---|
| Godkendt rettelse "0 hængere", chaufføren sagde 2, planlagt 2 | 0 | godkendt/rettet | ja |
| Ældre godkendt "med hænger", intet antal, intet planlagt | 1 | godkendt/rettet | ja |
| Chaufføren oplyste 1, planlagt 2 | 1 | chaufføren | ja |
| Kun planlagt 2 | 2 | planlagt | ja |
| Automatisk forslag fra chaufførens profil | 1 | automatisk | NEJ |
| Intet | 0 | - | ja |

Et automatisk forslag prissættes med hænger, men turen får markeringen "Hænger: automatisk, ikke bekræftet".

#### E87. Automatisk hænger i prisen

Standardpris 1.000 + hængertillæg 300 = 1.300,00 kr. Markeringer: Hænger: automatisk, ikke bekræftet.


### B9. Ventetid

Ventetid kommer fra turens godkendte rettelser (chaufførens anmodning, automatisk godkendelse eller admin). Uden ventetid ingen linje. Kr/t-ventetid afregnes pr. PÅBEGYNDT kvarter.

#### E88. 20 min ventetid

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Ventetid** - tillæg (Ventetid): 400 kr/t. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; ventetid 20 min

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Ventetid (30 min × 400 kr/t): 200,00 kr
  - **I alt 1.200,00 kr** (ekskl. moms)

**Hvorfor:** 20 -> 30 min (påbegyndt kvarter). 400 × 30/60 = 200.

#### E89. 15 min ventetid

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Ventetid** - tillæg (Ventetid): 400 kr/t. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; ventetid 15 min

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Ventetid (15 min × 400 kr/t): 100,00 kr
  - **I alt 1.100,00 kr** (ekskl. moms)

**Hvorfor:** Præcis ét kvarter.

#### E90. Ingen ventetid

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Ventetid** - tillæg (Ventetid): 400 kr/t. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - **I alt 1.000,00 kr** (ekskl. moms)

**Hvorfor:** Ingen linje.

#### E91. Ventetid som fast beløb

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Ventetid** - tillæg (Ventetid): 150,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; ventetid 40 min

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Ventetid: 150,00 kr
  - **I alt 1.150,00 kr** (ekskl. moms)

**Hvorfor:** Fast 150 kr når der er ventetid - uanset hvor lang.

#### E92. Ventetid i procent

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Ventetid** - tillæg (Ventetid): 10 % af grundprisen. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; ventetid 40 min

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Ventetid (10%): 100,00 kr
  - **I alt 1.100,00 kr** (ekskl. moms)

**Hvorfor:** 10 % af grundprisen når der er ventetid.

#### E93. Aftalt pris + ventetid oveni

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Ventetid** - tillæg (Ventetid): 400 kr/t. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; ventetid 25 min; Aftalt pris 2.000,00 kr + ventetid oveni

**Resultat:**
  - Aftalt pris: 2.000,00 kr
  - Ventetid (30 min × 400 kr/t): 200,00 kr
  - **I alt 2.200,00 kr** (ekskl. moms)
  - Markeringer: Manuel pris

**Hvorfor:** Aftalt 2.000. Ventetid 25 -> 30 min = 200 lægges oveni (valgt ved aftalen).

#### E94. Aftalt pris uden ventetid oveni

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Ventetid** - tillæg (Ventetid): 400 kr/t. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; ventetid 25 min; Aftalt pris 2.000,00 kr

**Resultat:**
  - Aftalt pris: 2.000,00 kr
  - Ventetid (30 min × 400 kr/t) - indregnet i aftalt pris: 0,00 kr
  - **I alt 2.000,00 kr** (ekskl. moms)
  - Markeringer: Manuel pris

**Hvorfor:** Ventetiden er indregnet (0 kr).

#### E95. 61 min ventetid

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Ventetid** - tillæg (Ventetid): 400 kr/t. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; ventetid 61 min

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Ventetid (75 min × 400 kr/t): 500,00 kr
  - **I alt 1.500,00 kr** (ekskl. moms)

**Hvorfor:** 61 -> 75 min (5 påbegyndte kvarterer). 400 × 75/60 = 500.


### B10. Ekstra stop

En tur har som udgangspunkt 2 stop (afhentning + aflevering). Tillægget betales pr. stop ud over de inkluderede (standard 2).

#### E96. 4 stop, 2 inkluderet

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Ekstra stop** - tillæg (Ekstra stop): 150,00 kr pr. stop ud over 2. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; 4 stop

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Ekstra stop (2 ekstra stop × 150 kr): 300,00 kr
  - **I alt 1.300,00 kr** (ekskl. moms)

**Hvorfor:** 2 ekstra × 150.

#### E97. 2 stop

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Ekstra stop** - tillæg (Ekstra stop): 150,00 kr pr. stop ud over 2. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - **I alt 1.000,00 kr** (ekskl. moms)

**Hvorfor:** Ingen ekstra stop - ingen linje.

#### E98. 3 stop, 1 inkluderet

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Ekstra stop** - tillæg (Ekstra stop): 150,00 kr pr. stop ud over 1. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; 3 stop

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Ekstra stop (2 ekstra stop × 150 kr): 300,00 kr
  - **I alt 1.300,00 kr** (ekskl. moms)

**Hvorfor:** 2 ekstra × 150.


### B11. Aften/nat (tidsrum)

Tidsrummet gælder turens STARTtidspunkt. Fra-tid er med, til-tid er ikke. Et tidsrum over midnat (18:00-06:00) er tilladt.

#### E99. Start 19:30

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Aftentillæg** - tillæg (Aften/nat): 250,00 kr. Gælder: start kl. 18:00-06:00. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 19:30

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Aftentillæg: 250,00 kr
  - **I alt 1.250,00 kr** (ekskl. moms)

**Hvorfor:** I tidsrummet.

#### E100. Start 06:00

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Aftentillæg** - tillæg (Aften/nat): 250,00 kr. Gælder: start kl. 18:00-06:00. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 06:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - **I alt 1.000,00 kr** (ekskl. moms)

**Hvorfor:** 06:00 er sluttiden og er ikke med.

#### E101. Start 05:59

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Aftentillæg** - tillæg (Aften/nat): 250,00 kr. Gælder: start kl. 18:00-06:00. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 05:59

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Aftentillæg: 250,00 kr
  - **I alt 1.250,00 kr** (ekskl. moms)

**Hvorfor:** Før 06:00 = med.

#### E102. Start 17:59

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Aftentillæg** - tillæg (Aften/nat): 250,00 kr. Gælder: start kl. 18:00-06:00. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 17:59

**Resultat:**
  - Standardpris: 1.000,00 kr
  - **I alt 1.000,00 kr** (ekskl. moms)

**Hvorfor:** Før 18:00.

#### E103. Ingen starttid

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Aftentillæg** - tillæg (Aften/nat): 250,00 kr. Gælder: start kl. 18:00-06:00. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; ingen starttid

**Resultat:**
  - Standardpris: 1.000,00 kr
  - **I alt 1.000,00 kr** (ekskl. moms)

**Hvorfor:** Uden starttid kan et tidsrum aldrig passe.

#### E104. Dagtidsrum 06-18, start 18:00

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Dagtillæg** - tillæg (Andet): 100,00 kr. Gælder: start kl. 06:00-18:00. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 18:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - **I alt 1.000,00 kr** (ekskl. moms)

**Hvorfor:** 18:00 er sluttiden.

#### E105. Aftentillæg pr. time på timepris

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Aften kr/t** - tillæg (Aften/nat): 100 kr/t. Gælder: start kl. 18:00-06:00. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 19:00; tid 120 min

**Resultat:**
  - Timepris (2t 00m × 600 kr/t): 1.200,00 kr
  - Aften kr/t (120 min × 100 kr/t): 200,00 kr
  - **I alt 1.400,00 kr** (ekskl. moms)

**Hvorfor:** 120 fakturerbare min: 1.200 + 100 × 2 = 1.400. Et kr/t-tillæg bruger de fakturerbare minutter.


### B12. Dagtyper og helligdage

#### E106. Helligdage 2026 i logistikfirmaets egen kalender (standard)

Officielle danske helligdage beregnes for ethvert år (påskeformlen). Standard-tilvalg: Grundlovsdag, Juleaften, Nytårsaftensdag. 1. maj kan vælges til. Store bededag findes ikke (afskaffet fra 2024).

| Dato | Navn |
|---|---|
| 2026-01-01 | Nytårsdag |
| 2026-04-02 | Skærtorsdag |
| 2026-04-03 | Langfredag |
| 2026-04-05 | Påskedag |
| 2026-04-06 | 2. påskedag |
| 2026-05-14 | Kristi himmelfartsdag |
| 2026-05-24 | Pinsedag |
| 2026-05-25 | 2. pinsedag |
| 2026-06-05 | Grundlovsdag |
| 2026-12-24 | Juleaften |
| 2026-12-25 | 1. juledag |
| 2026-12-26 | 2. juledag |
| 2026-12-31 | Nytårsaftensdag |

#### E107. Dagtype for udvalgte datoer

| Dato | Dagtype |
|---|---|
| 2026-10-20 | Hverdag |
| 2026-10-24 | Lørdag |
| 2026-10-25 | Søndag |
| 2026-12-26 | Helligdag |
| 2026-06-05 | Helligdag |
| 2026-05-01 | Hverdag |
| 2026-12-24 | Helligdag |

En helligdag er altid "Helligdag", også på en lørdag eller søndag (26.12.2026 er en lørdag).

#### E108. Egen kalender: fravalgt juleaften, tilføjet firmafest

Indstillinger: fravalg 24.12.2026, ekstra fridag 14.08.2026 "Firmafest". Resultat: 24.12 er en almindelig torsdag, 14.08 er en helligdag (helligdagstillæg gælder).

#### E109. Lokationens kalender bruges i stedet for den egne

Indstilling "Brug kundens helligdage først" (standard). Lokation 1101 har en aktiv helligdagskalender for 2026 med kun juledagene. Tur 05.06.2026 (Grundlovsdag): kalenderen kommer fra "Lokationens helligdagskalender", og dagtypen er **Hverdag**. Den egne kalender (som har Grundlovsdag) bruges IKKE - den er kun reserve, når kunden ingen kalender har. Helligdagstillæg gælder derfor ikke.

#### E110. Materialets kalender går forud for lokationens

Pap på lokation 1101 har sin egen helligdagskalender (samme som bestillingssiden bruger), hvor 05.06 er fridag. Plast bruger lokationens aktive kalender. 05.06.2026: Pap = **Helligdag**, Plast = **Hverdag**.

#### E111. Kundens helligdagsgruppe når lokationen ingen kalender har

Ingen kalender på lokationen. HF er i en helligdagsgruppe med 05.06. Kilde: "Kundens helligdagsgruppe", dagtype **Helligdag**.

#### E112. Indstillingen "Brug egen kalender"

Med indstillingen "own" bruges altid logistikfirmaets egen kalender (kilde: "Egen helligdagskalender"). Samme tur 05.06.2026 med reglerne Standardpris 1.000 + Helligdag 800: med kundens kalender 1.000,00 kr, med egen kalender 1.800,00 kr.


### B13. Materialer

En GRUNDPRIS med materialer gælder kun, når ALLE turens materialer er nævnt. Et TILLÆG med materialer gælder, når ét af dem er på turen.

#### E113. Blandet tur matcher ikke betonprisen

**Regler:**
- **Beton** - fast pris 900,00 kr. Gælder: materiale = Beton. Specificitet 4.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Beton + Træ; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - **Ingen pris: Mangler pris** (turen tæller ikke med i summen)
  - Markeringer: Ingen grundpris-regel matcher turen
  - Forklaring i Rapport: "Nærmeste regel "Beton" passer ikke på: materiale (turen har Beton + Træ, reglen gælder Beton)"

**Hvorfor:** Turen har Beton + Træ. Betonprisen gælder kun rene betonture.

#### E114. Blandet tur får den generelle pris

**Regler:**
- **Beton** - fast pris 900,00 kr. Gælder: materiale = Beton. Specificitet 4.
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Beton + Træ; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - **I alt 1.000,00 kr** (ekskl. moms)

**Hvorfor:** 

#### E115. Regel for begge materialer

**Regler:**
- **Beton/Træ** - fast pris 950,00 kr. Gælder: materiale = Beton eller Træ. Specificitet 4.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Beton + Træ; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Beton/Træ: 950,00 kr
  - **I alt 950,00 kr** (ekskl. moms)

**Hvorfor:** Alle turens materialer er nævnt.

#### E116. Regel for begge, tur med ét

**Regler:**
- **Beton/Træ** - fast pris 950,00 kr. Gælder: materiale = Beton eller Træ. Specificitet 4.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Beton; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Beton/Træ: 950,00 kr
  - **I alt 950,00 kr** (ekskl. moms)

**Hvorfor:** Beton er nævnt - det er nok.

#### E117. Tillæg for ét af materialerne

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Betontillæg** - tillæg (Andet): 200,00 kr. Gælder: materiale = Beton. Specificitet 4.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Beton + Træ; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Betontillæg: 200,00 kr
  - **I alt 1.200,00 kr** (ekskl. moms)

**Hvorfor:** Tillæg: ét materiale er nok.

#### E118. Store og små bogstaver

**Regler:**
- **pap** - fast pris 800,00 kr. Gælder: materiale = pap. Specificitet 4.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - pap: 800,00 kr
  - **I alt 800,00 kr** (ekskl. moms)

**Hvorfor:** "pap" = "Pap".

#### E119. Tur uden materiale

**Regler:**
- **Pap** - fast pris 800,00 kr. Gælder: materiale = Pap. Specificitet 4.
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale (intet); dagtype Hverdag; start kl. 08:00

**Resultat:**
  - Standardpris: 1.000,00 kr
  - **I alt 1.000,00 kr** (ekskl. moms)

**Hvorfor:** En materialeregel kræver et materiale.


### B14. Forgæves kørsel

Almindelige regler gælder kun gennemførte ture. En forgæves tur skal have en regel med udfald "forgæves" (eller "alle").

#### E120. Forgæves uden forgæves-pris

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; FORGÆVES

**Resultat:**
  - **Ingen pris: Mangler pris** (turen tæller ikke med i summen)
  - Markeringer: Ingen grundpris-regel matcher turen
  - Forklaring i Rapport: "Nærmeste regel "Standardpris" passer ikke på: forgæves kørsel (ingen pris for forgæves kørsel)"

**Hvorfor:** 

#### E121. Forgæves-pris

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Forgæves kørsel** - fast pris 400,00 kr. Gælder: udfald = forgæves. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; FORGÆVES

**Resultat:**
  - Forgæves kørsel: 400,00 kr
  - **I alt 400,00 kr** (ekskl. moms)

**Hvorfor:** 

#### E122. Timepris for alle udfald

**Regler:**
- **Timepris alle** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: udfald = alle (gennemført og forgæves). Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; FORGÆVES; tid 45 min

**Resultat:**
  - Timepris alle (0t 45m × 600 kr/t): 450,00 kr
  - **I alt 450,00 kr** (ekskl. moms)

**Hvorfor:** Tiden for en forgæves tur er fra "På vej" til den blev markeret forgæves.

#### E123. Kundens forgæves-pris slår "alle udfald"

**Regler:**
- **Alle udfald** - fast pris 700,00 kr. Gælder: udfald = alle (gennemført og forgæves). Specificitet 1.
- **HF forgæves** - fast pris 450,00 kr. Gælder: kunde = Helsingør Forsyning, udfald = forgæves. Specificitet 65.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; FORGÆVES

**Resultat:**
  - HF forgæves: 450,00 kr
  - **I alt 450,00 kr** (ekskl. moms)

**Hvorfor:** 65 > 1.

#### E124. Prisaftalens tillæg gælder ikke forgæves ture

**Regler:**
- **HF forgæves** - fast pris 400,00 kr. Gælder: kunde = Helsingør Forsyning, udfald = forgæves. Specificitet 65.
- **Weekend HF** - tillæg (Weekend): 300,00 kr. Gælder: kunde = Helsingør Forsyning, dagtype = Lørdag eller Søndag. Specificitet 65.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Lørdag; start kl. 08:00; FORGÆVES

**Resultat:**
  - HF forgæves: 400,00 kr
  - **I alt 400,00 kr** (ekskl. moms)

**Hvorfor:** Tillæg i en prisaftale har udfald "gennemført". En forgæves lørdagstur får kun forgæves-prisen.

#### E125. Tillæg der også gælder forgæves

**Regler:**
- **Forgæves** - fast pris 450,00 kr. Gælder: udfald = forgæves. Specificitet 1.
- **Helligdag (alle udfald)** - tillæg (Helligdag): 800,00 kr. Gælder: dagtype = Helligdag, udfald = alle (gennemført og forgæves). Specificitet 2.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Helligdag; start kl. 08:00; FORGÆVES

**Resultat:**
  - Forgæves: 450,00 kr
  - Helligdag (alle udfald): 800,00 kr
  - **I alt 1.250,00 kr** (ekskl. moms)

**Hvorfor:** Vil man have tillæg på forgæves ture, skal tillægget have udfald "alle".


### B15. Aftalt pris, manuel pris og ekstra linjer

#### E126. Aftalt pris erstatter reglerne

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Weekendtillæg** - tillæg (Weekend): 500,00 kr. Gælder: dagtype = Lørdag eller Søndag. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Lørdag; start kl. 08:00; Aftalt pris 2.400,00 kr

**Resultat:**
  - Aftalt pris: 2.400,00 kr
  - Weekendtillæg - indregnet i aftalt pris: 0,00 kr
  - **I alt 2.400,00 kr** (ekskl. moms)
  - Markeringer: Manuel pris

**Hvorfor:** Weekend vises som indregnet (0 kr).

#### E127. Aftalt pris uden regler

**Regler:**
- (ingen regler)

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; Aftalt pris 2.400,00 kr

**Resultat:**
  - Aftalt pris: 2.400,00 kr
  - **I alt 2.400,00 kr** (ekskl. moms)
  - Markeringer: Manuel pris

**Hvorfor:** En aftalt pris virker også uden prisregler.

#### E128. Manuel pris + ekstra linje

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; Manuel pris 1.500,00 kr; ekstra linje "Ekstra rengøring" 300,00 kr

**Resultat:**
  - Manuel pris: 1.500,00 kr
  - Ekstra rengøring: 300,00 kr
  - **I alt 1.800,00 kr** (ekskl. moms)
  - Markeringer: Manuel pris

**Hvorfor:** 1.500 + 300.

#### E129. Reglernes pris + ekstra linje

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; ekstra linje "Ekstra rengøring" 300,00 kr

**Resultat:**
  - Standardpris: 1.000,00 kr
  - Ekstra rengøring: 300,00 kr
  - **I alt 1.300,00 kr** (ekskl. moms)

**Hvorfor:** 1.000 + 300. Ekstra linjer kan bruges uden at overstyre prisen.

#### E130. Ekstra linje redder ikke en manglende pris

**Regler:**
- (ingen regler)

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; ekstra linje "Ekstra rengøring" 300,00 kr

**Resultat:**
  - Ekstra rengøring: 300,00 kr
  - **Ingen pris: Mangler pris** (turen tæller ikke med i summen)
  - Markeringer: Ingen grundpris-regel matcher turen
  - Forklaring i Rapport: "Der er ikke oprettet nogen grundpris endnu"

**Hvorfor:** Mangler grundprisen, er der stadig ingen total.

#### E131. Manuel pris på en timepris-tur uden tid

**Regler:**
- **Timepris** - timepris 600 kr/t, ingen afrunding, pause trækkes fra. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; Manuel pris 1.500,00 kr

**Resultat:**
  - Manuel pris: 1.500,00 kr
  - **I alt 1.500,00 kr** (ekskl. moms)
  - Markeringer: Manuel pris

**Hvorfor:** Den manuelle pris gælder; "Mangler tid" forsvinder.

#### E132. Aftalt pris + ventetid + ekstra linje

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Ventetid** - tillæg (Ventetid): 400 kr/t. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00; ventetid 25 min; Aftalt pris 2.000,00 kr + ventetid oveni; ekstra linje "Færge" 350,00 kr

**Resultat:**
  - Aftalt pris: 2.000,00 kr
  - Ventetid (30 min × 400 kr/t): 200,00 kr
  - Færge: 350,00 kr
  - **I alt 2.550,00 kr** (ekskl. moms)
  - Markeringer: Manuel pris

**Hvorfor:** 2.000 + 200 (ventetid 30 min) + 350.


### B16. Versioner, gyldighed og fakturering

To forskellige ting: VERSION afgøres af hvornår turen blev OPRETTET/bestilt (`created_at`). GYLDIGHED (kørselsdato fra/til) afgøres af hvornår turen blev KØRT.

#### E133. Hvilken version gælder for en tur

Prisen blev rettet 2026-10-01T10:00:00+02:00 ("Nye ture fra nu"). Den gamle version lukkes på tidspunktet, den nye starter samme tidspunkt. Fra-tidspunktet er med, til-tidspunktet er ikke.

| Turen oprettet | Gammel version gælder | Ny version gælder |
|---|---|---|
| 2026-09-30T12:00:00+02:00 | ja | nej |
| 2026-10-01T10:00:00+02:00 | nej | ja |
| 2026-11-01T08:00:00+01:00 | nej | ja |

#### E134. Prisstigning "Nye ture fra nu"

v1 900 kr gælder ture oprettet før 01.10.2026 kl. 10, v2 1.000 kr ture oprettet derefter. Begge ture køres 20.10.2026. Tur oprettet 28.09: **900,00 kr**. Tur oprettet 02.10: **1.000,00 kr**. En prisændring ændrer altså ikke prisen på ture, der allerede var bestilt.

#### E135. "Fra en dato" følger oprettelsen, ikke kørslen

Ny pris "fra 01.01.2027" (versionen starter 2027-01-01T00:00:00+01:00). En tur oprettet 30.12.2026 og kørt 05.01.2027 får **900,00 kr** - den gamle pris, fordi den blev oprettet før. Skal prisen følge KØRSELSDATOEN, bruges "Ture kørt fra en dato" (næste eksempel).

#### E136. "Ture kørt fra en dato"

Den gamle aftale får kørselsdato til 31.12.2026, en ny aftale gælder ture kørt fra 01.01.2027 - også ture der allerede er oprettet (fx en serie). Tur oprettet 30.12, kørt 05.01.2027: **1.000,00 kr**. Tur kørt 30.12.2026: **900,00 kr**.

#### E137. "Nye + ture uden pris" (standard for nye prisaftaler)

En aftale oprettet 15.10 med dette valg gælder ture oprettet senere OG ældre ture, der ellers ingen pris har. Ældre tur uden pris: **800,00 kr** med markeringen "Pris fra aftale oprettet efter turen (gælder ture uden pris)". Samme tur, når den allerede havde en standardpris: **1.000,00 kr** - en tur med pris ændres aldrig.

#### E138. Faktureret tur er frosset

Turen blev faktureret til 950 kr. Reglen er siden sat op til 1.200. Turen viser stadig **950,00 kr** med markeringen "Faktureret". Skal den ændres, fjernes markeringen "faktureret" først.

#### E139. Tur uden oprettelsestidspunkt

Mangler `created_at` (meget gamle ture), bruges kørselsdatoen som oprettelse: 20.10.2026 -> ny version, **1.000,00 kr**.

#### E140. Danske tal i beløbsfelterne

| Indtastet | Læses som |
|---|---|
| `1.000` | 1000 |
| `1.000,50` | 1000,5 |
| `1000,5` | 1000,5 |
| `1100.5` | 1100,5 |
| `12.500` | 12500 |
| `1.5` | 1,5 |
| `2 500 kr` | 2500 |
| `15%` | 15 |

"1.000" er tusind (dansk tusindtalsseparator), mens "1.5" er halvanden.


### B17. Kørselsdato (hvilken dag tæller)

Kørselsdatoen styrer dagtype (weekend/helligdag), kørselsdato-gyldighed og hvilken periode turen står i i Rapport.

#### E141. Kørselsdato i forskellige situationer

Kørselsdatoen er den dag turen blev STARTET (dansk tid). Uden starttidsstempel regnes den ud fra afslutningen; er sluttiden før starttiden, startede turen dagen før.

| Situation | Kørselsdato |
|---|---|
| Startet lørdag 23:00 (på vej-tidsstempel), afsluttet søndag | 2026-10-24 |
| Ældre tur uden på vej-tidsstempel: start 23:00, slut 02:15 søndag | 2026-10-24 |
| Afsluttet 00:30 dansk tid (22:30 UTC dagen før), startet 23:30 | 2026-10-20 |
| Forgæves | 2026-10-20 |
| Ikke kørt endnu | 2026-11-02 |

#### E142. Lørdagstur der først blev afsluttet søndag

Reglerne: Standardpris 1.000 + søndagstillæg 600. Turen startede lørdag 23:00 og sluttede søndag 01:30. Pris: **1.000,00 kr** - lørdag, intet søndagstillæg.

#### E143. Tid på en forgæves tur

På vej kl. 09:10, markeret forgæves 07:55 UTC = 09:55 dansk tid. Tid: 09:10-09:55 = 45 min.


### B18. Hvem er kunden (prisnøglen)

#### E144. Prisnøglen for kunden

Logistikfirmaet hedder her `LOGI`. En kunde-betingelse i en prisregel matcher denne nøgle.

| Tur | Kundenøgle |
|---|---|
| Tur på HF's genbrugsplads (B2B) | `HF` |
| Egen tur med firmanavn "Byg ApS" | `firma:byg aps` |
| Egen tur valgt fra kunderegistret (navn "Byg A/S") | `firma:byg a/s` |
| Egen tur uden kunde | `LOGI` |

Navne gøres til små bogstaver med enkelte mellemrum, så "Byg  ApS" og "byg aps" er samme kunde. Et navn fra kunderegistret vinder over teksten på turen.


### B19. Samlede eksempler (mange regler på én gang)

#### E145. HF lørdag, haster, 2 hængere, ventetid, timepris

**Regler:**
- **HF timepris** - timepris 650 kr/t, startgebyr 250,00 kr, op til 15 min, pause trækkes fra. Gælder: kunde = Helsingør Forsyning. Specificitet 64.
- **Weekend HF 20 %** - tillæg (Weekend): 20 % af grundprisen. Gælder: kunde = Helsingør Forsyning, dagtype = Lørdag eller Søndag. Specificitet 65.
- **Haster** - tillæg (Haster): 300,00 kr. Gælder: prioritet = Haster. Specificitet 1.
- **2 hængere** - tillæg (Hænger): 400,00 kr. Gælder: antal hængere = 2. Specificitet 2.
- **Ventetid** - tillæg (Ventetid): 450 kr/t. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; prioritet Haster; dagtype Lørdag; 2 hænger(e); start kl. 07:00; ventetid 25 min; tid 128 min

**Resultat:**
  - Startgebyr: 250,00 kr
  - HF timepris (2t 15m × 650 kr/t): 1.462,50 kr
  - Haster: 300,00 kr
  - 2 hængere: 400,00 kr
  - Ventetid (30 min × 450 kr/t): 225,00 kr
  - Weekend HF 20 % (20%): 342,50 kr
  - **I alt 2.980,00 kr** (ekskl. moms)

**Hvorfor:** 128 -> 135 min. 650 × 135/60 = 1.462,50 + startgebyr 250 = 1.712,50. Weekend 20 % = 342,50. Haster 300. Hænger 400. Ventetid 25 -> 30 min × 450/60 = 225. I alt 2.980.

#### E146. Varelevering pr. palle med stop, aften og ventetid

**Regler:**
- **Palletakst** - 45,00 kr pr. paller, minimum 600,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Ekstra stop** - tillæg (Ekstra stop): 175,00 kr pr. stop ud over 2. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Aften 15 %** - tillæg (Aften/nat): 15 % af grundprisen. Gælder: start kl. 18:00-06:00. Specificitet 1.
- **Ventetid** - tillæg (Ventetid): 400 kr/t. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; opgavetype Levering; dagtype Hverdag; start kl. 18:30; ventetid 10 min; 4 stop; antal: 18 paller (registreret)

**Resultat:**
  - Palletakst (18 paller × 45 kr, registreret): 810,00 kr
  - Aften 15 % (15%): 121,50 kr
  - Ekstra stop (2 ekstra stop × 175 kr): 350,00 kr
  - Ventetid (15 min × 400 kr/t): 100,00 kr
  - **I alt 1.381,50 kr** (ekskl. moms)

**Hvorfor:** 18 × 45 = 810 (over minimum). 2 ekstra stop = 350. Aften 15 % af 810 = 121,50. Ventetid 10 -> 15 min = 100. I alt 1.381,50.

#### E147. Forgæves på en helligdag

**Regler:**
- **Standardpris** - fast pris 1.000,00 kr. Gælder: ingen betingelser (gælder alle ture). Specificitet 0.
- **Forgæves** - fast pris 450,00 kr. Gælder: udfald = forgæves. Specificitet 1.
- **Helligdag** - tillæg (Helligdag): 800,00 kr. Gælder: dagtype = Helligdag. Specificitet 1.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Helligdag; start kl. 08:00; FORGÆVES

**Resultat:**
  - Forgæves: 450,00 kr
  - **I alt 450,00 kr** (ekskl. moms)

**Hvorfor:** Helligdagstillægget har udfald "gennemført" og gælder ikke.

#### E148. Nærmeste regel i forklaringen

**Regler:**
- **HF Pap** - fast pris 900,00 kr. Gælder: kunde = Helsingør Forsyning, materiale = Pap. Specificitet 68.
- **ARGO 1101 Plast** - fast pris 950,00 kr. Gælder: kunde = ARGO, lokation = 1101, materiale = Plast. Specificitet 100.

**Turen:** kunde ARGO; lokation 1102; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - **Ingen pris: Mangler pris** (turen tæller ikke med i summen)
  - Markeringer: Ingen grundpris-regel matcher turen
  - Forklaring i Rapport: "Nærmeste regel "HF Pap" passer ikke på: kunde"

**Hvorfor:** "HF Pap" fejler kun på kunde (1 betingelse), "ARGO 1101 Plast" på lokation og materiale (2). Forklaringen viser reglen med færrest fejl.

#### E149. Lige mange fejl: den mest specifikke vises

**Regler:**
- **Lokation 1102** - fast pris 900,00 kr. Gælder: lokation = 1102. Specificitet 32.
- **ARGO** - fast pris 950,00 kr. Gælder: kunde = ARGO. Specificitet 64.

**Turen:** kunde Helsingør Forsyning; lokation 1101; materiale Pap; dagtype Hverdag; start kl. 08:00

**Resultat:**
  - **Ingen pris: Mangler pris** (turen tæller ikke med i summen)
  - Markeringer: Ingen grundpris-regel matcher turen
  - Forklaring i Rapport: "Nærmeste regel "ARGO" passer ikke på: kunde"

**Hvorfor:** Begge fejler på én betingelse; ARGO (64) foretrækkes frem for lokation (32).


### B20. Prisaftaler (sådan gemmes en aftale)

#### E150. En prisaftale bliver til flere regler

Aftalen "HF aftale" (kunde HF): grundpris 1.200, forgæves 400, weekend 300, aften 250, 2 hængere 350, ekstra stop 150. Hvert tillæg får aftalens betingelser + sin egen situation automatisk:

| Regel | Type | Gælder | Specificitet |
|---|---|---|---|
| HF aftale | grundpris | kunde = Helsingør Forsyning | 64 |
| HF aftale - Forgæves kørsel | grundpris | kunde = Helsingør Forsyning, udfald = forgæves | 65 |
| HF aftale - Weekend | tillæg | kunde = Helsingør Forsyning, dagtype = Lørdag eller Søndag | 65 |
| HF aftale - Aften/nat | tillæg | kunde = Helsingør Forsyning, start kl. 18:00-06:00 | 65 |
| HF aftale - Hænger | tillæg | kunde = Helsingør Forsyning, antal hængere = 2 | 66 |
| HF aftale - Ekstra stop | tillæg | kunde = Helsingør Forsyning | 64 |

Samme tillægstype to gange i én aftale afvises ("Tillægget 'Weekend' står to gange").


### B21. Moms

#### E151. Moms i Rapport

Alle priser er ekskl. moms. Rapporten lægger moms på summen: netto 10.000,00 kr + 25 % moms 2.500,00 kr = 12.500,00 kr. Momssatsen kan ændres under Indstillinger.

