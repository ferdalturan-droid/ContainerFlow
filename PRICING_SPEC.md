# Økonomi — prisregler, rapport og godkendelser (logistik admin)

Erstatter den gamle "Priser & Rapport"-side (fast pris pr. plads + fraktion + ét
haster-gebyr). Skrevet 2026-10-16. Kilden til sandhed for hvordan en tur prissættes.

## 1. Grundidé

En tur får sin pris fra **prisregler**, som logistikfirmaet vedligeholder.

* **Grundpris-regel** — bestemmer *prismodellen* for de ture den matcher:
  * **Fast pris** (kr pr. tur)
  * **Timepris** (kr/t, valgfrit startgebyr, minimum, afrunding, pause-regel)
  * **Pris pr. container** (fx løs afhentning: N containere × pris)
* **Tillæg-regel** — lægges oven i grundprisen: kr pr. tur, % af grundpris eller
  kr pr. time. Tillæg har en **kategori** (Weekend, Helligdag, Haster, Hænger,
  Aften/nat, Ventetid, Andet).

Begge regeltyper har de samme **betingelser** ("gælder for"). Tom betingelse = alle:

| Betingelse | Kilde i systemet |
|---|---|
| Kunde | turens `company_id` |
| Lokation | turens plads → `location_code` |
| Leveringsadresse | ordrens leveringsadresse (alternativ adresse har forrang), matchet på **navn** (fx "HCS A/S Helsingør") så samme modtager på flere pladser kun skal prissættes én gang. Manuelle ture: "Modtager"-feltet |
| Materiale | `fraction` |
| Opgavetype | Afhentning, Byt container, Til værksted, Hent fra værksted, Løs afhentning (logistikfirmaets egne containere) |
| Prioritet | Haster / Normal / Lav |
| Dagtype | Hverdag, Lørdag, Søndag, Helligdag (eksklusive — en helligdag på en lørdag er "Helligdag") |
| Hænger | Med / Uden (chaufføren angiver pr. tur) |
| Containerstørrelse | kapacitetsmål på ordren (fx "Åben container 20 m³") |
| Tidsrum | turens starttidspunkt inden for fx 18:00–06:00 |
| Udfald | Gennemført / Forgæves ("Kan ikke gennemføres") |
| Gyldighed | gyldig fra/til (prisstigning pr. 1. januar uden at ændre historik) |

## 2. Beregning (og hvorfor)

1. **Grundpris:** blandt aktive, gyldige grundpris-regler der matcher, vinder den
   **mest specifikke** (vægt: kunde 64, lokation 32, leveringsadresse 16,
   opgavetype 8, materiale 4, containerstørrelse 2, øvrige 1). Lige specifik →
   senest opdaterede. Ingen match → turen står som **"Mangler pris"** i rapporten.
2. **Tillæg:** pr. kategori anvendes kun den **mest specifikke** matchende regel.
   Derfor kan en generel weekend-sats (+500) overstyres af en kundespecifik
   (+300 for ARGO) uden dobbeltopkrævning, og et kundespecifikt tillæg på 0 kr
   fritager en kunde. Forskellige kategorier lægges sammen.
3. **%-tillæg** beregnes af grundprisen (inkl. startgebyr), ikke af andre tillæg.
4. Alle beløb er **ekskl. moms**; rapporten viser moms separat.

### Tid (timepris)
* Turens tid = **"På vej" → "Afslut tur"**.
* **Pauser** registreres kun under "Tid" (aldrig på turen). Pause-perioder der
  overlapper turens tidsrum trækkes fra, hvis grundprisreglen siger det.
* **Samtidige ture** (hænger med flere containere): når chaufføren har flere ture
  i gang samtidig, **fordeles** de overlappende minutter ligeligt mellem turene,
  så kunderne ikke betaler for den samme time to gange. Kan sættes til "fuld tid
  på hver tur" under Indstillinger.
* **Afrunding** (pr. regel): ingen / op / nærmeste / ned til nærmeste N minutter
  (15, 30, 60 eller eget tal).
* **Minimum** (valgfrit): minimum minutter og/eller minimumsbeløb.
* **Startgebyr** (valgfrit).
* Mangler start- eller sluttid → markeres "Mangler tid".

### Helligdage
Rækkefølge (indstilling "Brug kundens helligdage først", standard: til):
1. Lokationens helligdagskalender for materialet (samme som bestillingssiden
   bruger), ellers lokationens aktive kalender for året.
2. Kundens helligdagsgruppe (sat af system-ejeren).
3. Logistikfirmaets egen kalender.

Logistikfirmaets kalender beregnes **automatisk for alle år** (påskeberegning):
officielle danske helligdage + valgfrie dage (Grundlovsdag, Juleaften,
Nytårsaftensdag, 1. maj) + egne ekstra dage + fravalgte datoer.

Datoen der tæller er **den dag turen køres** (afslutningsdato; ikke-kørte ture:
planlagt dato).

## 3. Afvigelser pr. tur

* **Logistik admin** kan pr. tur (også afsluttede): sætte fast beløb, ændre
  fakta (start/slut, hænger, ventetid, pause tæller/tæller ikke) og tilføje
  ekstra linjer (fx "Ekstra rengøring 300 kr"). Gælder straks. Note påkrævet.
* **Chaufføren** ser aldrig beløb, men ser på turen: Fast pris / Timepris (kr/t),
  om pause trækkes fra. Chaufføren kan:
  * **Mens turen kører:** vælge Med/Uden hænger (faktum der registreres nu).
  * **Efter turen:** anmode om rettelse af start/slut, hænger og ventetid med en
    kommentar → **Godkendelser** hos logistik admin. Kun godkendte rettelser
    påvirker prisen. Chaufføren ser status (afventer/godkendt/afvist).
  * Chaufføren kan ikke vælge prismodel eller beløb — det er en kommerciel
    beslutning.
* **Faktureret:** markerer man ture som faktureret, fryses prisen (snapshot), så
  senere regelændringer ikke ændrer allerede fakturerede beløb.

## 3b. Prisændringer følger ikke gamle ture (2026-10-17)

En prisregel har **versioner**. Når en regel rettes, vælger man hvornår ændringen gælder:

| Valg | Effekt |
|---|---|
| **Nye ture fra nu** (standard) | Den gamle version lukkes nu (`version_to`), og en ny version starter (`version_from`). Ture der allerede er oprettet eller bestilt beholder den gamle pris i rapporter, PDF og fakturagrundlag |
| **Fra en dato** | Det samme, men skiftet sker ved midnat (dansk tid) den valgte dato |
| **Også eksisterende ture** | Versionen rettes direkte, bagudrettet. Fakturerede ture er stadig frosne |

- Hvilken version en tur bruger, afgøres af turens `created_at` (hvornår den blev oprettet eller bestilt). Kørselsdatoen afgør det ikke.
- At slette en regel betyder som standard **"Stop fra nu"**. "Slet helt" fjerner den også bagudrettet.
- At slå en regel til eller fra laver også en ny version fra nu.
- Første regel nogensinde gælder som standard alle ture (opstart).
- Kode:
  - `_rule_active_at`, `_PricingContext.rules_for`, `PUT /pricing/rules/{id}` (`effective`) og `GET /pricing/rules/{id}/history` (alle i `backend/server.py`).
  - `valid_from`/`valid_to` er noget andet: reglens kørselsdato-periode ("Kørselsdato fra/til" i editoren).

**Aftalt pris ved oprettelse:** I "Ny tur" kan man skrive en fast pris pr. tur. Den gemmes som `price_override` (fast) med historik, så den aldrig påvirkes af senere regelændringer. Kræver rettigheden "Ændre priser".

## 3c. Kunder & priser (2026-10-17)

Fanen **Kunder & priser** viser alle kunder ét sted:
- **Genbrugsplads-kunder.** Kunder der har købt systemet og bruger firmaet som logistikpartner (B2B).
- **Egne kunder.** Firmaets egne slutkunder på egne ture.
  - De oprettes i kunderegistret (`logistics_customers`: navn, CVR, adresse, kontakt, telefon, e-mail, note), også før der findes ture.
  - Navne der står på egne ture, men ikke er oprettet, vises som "Fra ture".
  - Nøglen for priser er `firma:<navn>`, den samme som egne ture altid har brugt. Omdøbes en kunde, følger prisregler og ture med.
- **Egne ture uden kunde.**

Ud for hver kunde står, om den følger de generelle priser eller har en egen prisaftale, og knappen **"Sæt egen pris"** åbner regel-editoren med kunden valgt. En kunderegel vinder altid over en generel (kunde er den mest specifikke betingelse). Man kan derfor lave én afvigelse eller en hel prismodel pr. kunde og kombinere med alle andre betingelser.

**Hjælpetekster:** ⓘ ved hver regel forklarer prismodellen eller tillægstypen på dansk. Feltet "Jeres forklaring" (`note`, op til 1000 tegn) vises også ved ⓘ.

**Ventetid** (tillæg): betaling for tid chaufføren venter på adressen. Den afregnes pr. påbegyndt kvarter ud fra `waiting_min` på turen, som kommer fra chaufførens anmodning (godkendes under Godkendelser) eller fra admin i Rapport. Uden ventetid gives intet tillæg.

## 3d. Hængere og aftalt pris (2026-10-17)
- Betingelsen **Antal hængere** (1, 2, 3+) på prisregler gør det muligt at sætte fx 1 hænger = 700 kr og 2 hængere = 1.100 kr (ikke nødvendigvis det dobbelte). Antallet kommer fra turens `trailer_count` (planlagt i Ny tur). Hvis det mangler, bruges 1, hvis chaufføren kørte med hænger.
- **Aftalt pris** (fast pris pr. tur) erstatter reglerne, og weekend-, haster- og andre tillæg er indregnet. Ventetid kan lægges oveni (`add_waiting`), fordi den ikke kendes, når prisen aftales. Valget bevares, når prisen rettes i Økonomi.

## 3e. Prisaftaler: grundpris og flere tillæg i én regel (2026-10-17)
- **Fejlen:** den gamle regel-editor havde én vippeknap mellem "grundpris" og "tillæg". En regel kunne kun være den ene slags, så når man skrev 500 kr i tillæg og derefter 1.000 kr i grundpris (eller omvendt), gemte backend kun det sidste.
- **Nu:** en **prisaftale** (`bundle_id`/`bundle_name`) er én formular med fælles betingelser (kunde, lokation, opgavetype, materiale), én grundpris og en liste af tillæg. Den gemmes som flere regler med samme `bundle_id` (`POST /api/pricing/bundles`). Hver regel versioneres som før (3b).
- **Tillæg får deres scenarie automatisk** (`_CAT_AUTO`): weekend → lørdag/søndag, helligdag → helligdage, haster → prioritet haster, hænger → med hænger (+ evt. antal), aften → tidsvindue (standard 18–06). Samme type tillæg to gange i én aftale afvises. Gamle enkeltregler, hvor tillægget mangler sin betingelse, får en advarsel ("gælder altid").
- **Prøv prisen** (`POST /api/pricing/simulate`): vælg dag, prioritet, hængere, ventetid m.m. og se den præcise pris med linjer, også for en aftale der ikke er gemt endnu. Viser hvilken grundpris der vinder, hvis flere matcher.
- **Konfliktadvarsel:** findes der allerede regler med præcis de samme betingelser, svarer backend 409 med en liste; man kan gå tilbage eller "Gem alligevel".
- **Danske tal:** "1.000", "1.000,50" og "1000,5" læses korrekt overalt (backend `_parse_dk_number`, frontend `parseDk`), og feltet viser read-back "= 1.000,00 kr". Før blev "1.000" til 1 kr.
- **Fritaget** er et eksplicit valg på et tillæg (i stedet for at skrive 0 kr).
- **Kunder & priser** åbner kundens eksisterende aftale ("Ret prisaftale") i stedet for at oprette en dublet.
- **Rapport:** ture uden pris har knappen "Opret pris", der åbner en ny aftale udfyldt med turens kunde, lokation, opgavetype og materiale.
- Gamle enkeltregler vises under "Enkeltregler" og kan åbnes som en aftale (`adopt_ids`).
- Slet en aftale: "Stop fra nu" (bevarer historikken) eller "Slet helt" (`DELETE /api/pricing/bundles/{id}?effective=`).
- Hængertillæg afregnes ud fra det antal hængere chaufføren faktisk kørte med (`trailer_count_actual`), hvis det er indberettet; ellers det planlagte.

## 3f. Fra "friske øjne"-gennemgangen (2026-10-18)
- **"Opret pris" fra Rapport gælder nu også turen, man kom fra.** Valget "Nye + ture uden pris" (`effective="unpriced"`) gemmer aftalen fra nu, men markerer reglerne `backfill_unpriced`. En ældre tur bruger dem kun, hvis den ellers ingen pris har; ture med pris ændres aldrig. Efter gem bliver man i Rapport.
- **Hvilke ture gælder aftalen for?** "Ture kørt fra en dato" (anbefalet ved prisstigning): den gamle aftale får `valid_to` = dagen før, og en ny aftale med de nye beløb gælder fra datoen, også for ture der allerede er oprettet (fx en serie). "Kun ture oprettet fra nu" og "Alle, også eksisterende" er uændrede.
- **Én sandhed for hængere** (`_trailer_info`): godkendt/admin-rettet antal → chaufførens oplyste antal → planlagt antal → ja/nej. Rettelser og godkendelser sender **antal**. En godkendt "uden hænger" slår nu igennem (før blev den overset, når chaufføren havde oplyst et antal).
- **Automatisk hænger (B2B):** forslaget fra chaufførens profil ved start bevares, men gemmes som `trailer_source="auto"`, `trailer_confirmed=false`. Ved afslutning spørges "Kørte du med hænger?" med svaret forudfyldt. Rapport viser "automatisk, ikke bekræftet" og har et filter, så planlæggeren kan tjekke før fakturering. Prisen regnes stadig med hænger.
- **Materiale som liste:** en grundpris med materialer gælder kun, når **alle** turens materialer er med (en betonpris gælder kun rene betonture). Et tillæg gælder, når **ét** passer. Før matchede "Beton + Træ" ingen materialeregel og faldt stille igennem til en generel pris.
- **Forklaring på "Mangler pris"** (`explain_missing`): den nærmeste regel og de betingelser, der ikke passede, fx "materiale (turen har Beton + Træ, reglen gælder Beton)" eller "forgæves kørsel". Vises i Rapport, i prisopbygningen og på Ture-siden.
- **Pris pr. enhed** (`per_unit`): beløb × antal i enheden (paller, kolli, m³, ton …), registreret antal hvis chaufføren har oplyst det, ellers planlagt, med valgfrit minimumsbeløb. "Mangler antal", hvis turen ikke har linjer i enheden.
- **Stoptillæg** (`stop`): pr. stop ud over de inkluderede (standard 2). Stop der ikke kunne gennemføres, tæller med. Stop som chaufføren selv har tilføjet, tæller først, når planlæggeren har godkendt dem.
- **Forgæves kørsel:** en aftale kan have en pris for forgæves kørsel (en grundpris med udfald "forgæves"). Forgæves ture får tid fra "På vej" til de blev markeret (før "Mangler tid" ved timepris). Chaufføren vælger en årsagskode (`not_completed_code`).
- **Containere:** på containerture med flere indholdslinjer tæller hver linje som en container (eller linjens antal i stk/containere). Før var det altid 1.
- **Aftalt pris:** tillæg, der er indregnet, vises som "… - indregnet i aftalt pris (0 kr)". Ved flere ture viser Ny tur "2.400 kr pr. tur · 3 ture = 7.200 kr i alt". Standard er pr. tur; "samlet, deles ligeligt" er et aktivt valg.
- **Haster:** én kilde (`priority`). "haster" i planlæggerens note sætter prioriteten ved oprettelse (ikke "ikke haster"). B2B-kundens valgte prioritet overstyres ikke af kommentaren.
- **Faktureret = frosset registrering:** vægt, mængder, status, tider, hængere, billeder og stop kan ikke ændres på en faktureret tur (409). Fjern markeringen først.
- **Godkendelser:** advarsel når ventetid godkendes uden ventetidstillæg (= 0 kr). Flere rettelser pr. tur er tilladt, når de handler om forskellige ting. Kort ventetid kan godkendes automatisk (Økonomi › Indstillinger, `auto_approve_waiting_min`).
- **Prisstatus på Ture-siden** (`GET /api/pricing/status?ids=`): Mangler pris / Faktureret / Rettelse venter, uden beløb og kun med økonomi-adgang. Timeprisede ture, der ikke er kørt endnu, er ikke "Mangler tid".
- **Kunde fra kunderegistret:** Ny tur gemmer `customer_ref_id`. Prisnøglen tages fra registrets navn, også hvis turens tekst er stavet anderledes. Ligner et nyt navn en eksisterende kunde, foreslås den ("Mente du …?"). Nye navne oprettes i registret, hvis man vil.

## 3g. Hvem er kunden på en tur? (2026-10-18)
Ejerskab følger lokationen. Tur på en genbrugsplads-kundes plads → kunden er pladsens firma (`company_id`), og kundens prisaftaler gælder. Tur på egen lokation → registerkunden (`firma:<navn>` eller `customer_ref_id`). Ældre manuelle ture på kunders pladser er rettet ved opstart (ikke fakturerede). Se TURE_REDESIGN "Ejerskab følger lokationen".

## 3h. Tid på timeprisede ture (2026-10-18, P8)
- **Kørselsdatoen er den dag turen blev startet** (`on_way_at`, ellers regnet ud fra start- og sluttid). Før var det afslutningsdagen, så en lørdagstur, der først blev afsluttet søndag (glemt "Afslut"), fik søndags-/weekendpris. Påvirker kun ikke-fakturerede ture; fakturerede er frosset.
- **Ture-siden markerer tidsfejl som afvigelse:**
  - "Afsluttet en anden dag end startet";
  - "Startet under 2 min før afsluttet";
  - "Varighed under 5 min (timepris)", kun når turen afregnes på timepris (`hourly` i prisstatus).
- **Afslutningsarket:** på timepris, når turen er under 5 min gammel, spørges "Er starttiden rigtig?". En rettet starttid sendes som rettelse til godkendelse i samme `/finish`-kald.
- **"Afslut dag"** advarer, når chaufføren stadig har ture "På vej" ("Gå til turen" / "Afslut dagen alligevel").

## 4. Sider (logistik admin → "Økonomi")

Rapport · Kunder & priser · Prisregler · Godkendelser · Helligdage · Indstillinger

## 5. Bevidst udeladt (for nu)
* Pris pr. ton (deponi-/modtagegebyrer er modtagerens, ikke transportørens).
* Kunden ser ikke priser.
* Kilometerpris (kræver kørselsdata vi ikke har pålideligt).
