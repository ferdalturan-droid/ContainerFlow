# Svar på FRESH_EYES_REVIEW.md

Skrevet 2026-10-18. Hvert forslag er vurderet mod den **aktuelle** kode (commit `f2688bb`), ikke kun mod dokumentet. Linjetal nedenfor er fra den aktuelle kode; dokumentets linjetal er fra zip-versionen og afviger lidt.

**Mærker:** ✅ Enig · ⚠️ Delvist enig (med ændring) · ❌ Uenig · ➕ Noget jeg ville gøre ud over forslaget.

---

## Status 2026-10-18: implementeret

**Beslutninger efter din gennemgang**
- **Hænger på B2B:** forslaget fra profilen beholdes. Ved afslutning spørges "Kørte du med hænger?" forudfyldt, og automatisk/bekræftet gemmes. Rapport viser "automatisk, ikke bekræftet" med filter. Prisen regnes stadig med hænger.
- **Separate ture:** aftalt pris er **pr. tur** som standard, og totalen vises under feltet. "Samlet, deles ligeligt" er et aktivt valg. Den anden AI's argument holdt, og jeg ændrede mening.

| Pakke | Status |
|---|---|
| 1. Prisfejl | ✅ F-2 (+ bliv i Rapport, lokal dato), F-5 (én hænger-sandhed + bekræftet/automatisk), F-1, F-4, spærring ved faktureret, e2e-tests i repoet |
| 2. Ny tur og chauffør | ✅ D-default, container nr. og Haster fremme, note + kontakt pr. stop, ISO-tid på stop |
| 3. Synlighed | ✅ E1 prisstatus, E3 afvigelser (+ E2 mangler mængde/billede), "Mangler pris" forklaret |
| 4. Kunde og forgæves | ✅ D-kunde (via registrets navn, "Mente du …?"), C3 koder pr. firma, F-7, F-6, F-10 (+ automatisk godkendelse) |
| 5. Gods-pris | ✅ per_unit med minimum, stoptillæg, F-3 (pr. tur + total), F-12 (kørt fra dato), F-14 |
| 6. Stop og serier | ✅ C1a (modtager, afvigelse pr. stop), D-serie, B2-d (chauffør tilføjer stop, godkendes) |
| 7. Robust afslutning | ✅ `/finish` med op_id, offline-kø (start, stop, billeder, afslutning), B3 bag firmaindstilling (slået fra) |

**Fundet og rettet undervejs:**
- Chaufføren kunne se gårsdagens dato efter login.
- Talfelter med fast bredde i Økonomi fyldte hele bredden.
- Timeprisede ture, der ikke er kørt endnu, stod som "Mangler tid".
- Note på en aflevering uden adresse forsvandt.

**Ikke lavet (står under "Senere" i planen):**
- C1b (billede pr. stop, "Ankommet") og C2 (linjer pr. stop).
- F-8 (dagtype fra startdato).
- F-9 (leveringsadresser for egne lokationer, heller ikke den lille løsning med at skjule betingelsen).
- E5 (godkend direkte fra tur-panelet).
- Krav pr. kunde i registret (fx "kræver billede").
- Koordinator-adgang pr. egen kunde.
- Binært billed-endpoint.
- CO2-kolonne skjult for gods.
- Skabeloner og underskrift.

---

## 0. Hvad jeg har tjekket i koden (og det holder)

Dokumentets vigtigste fakta-påstande er korrekte. Jeg har selv set dem:

| Påstand | Fundet i koden |
|---|---|
| "Opret pris" fra Rapport gemmer med "Nye ture fra nu", så turen den blev åbnet fra stadig mangler pris | `EconomyPanel.jsx:1303`: `effective` er "now", medmindre `firstRule` sendes, og Rapport sender den ikke (`:232`) |
| Godkendt "uden hænger" har ingen effekt, når chaufføren har oplyst et antal | `server.py:17226-17236`: `trailer = False or trailer_count(1) > 0` giver `True` |
| "Beton + Træ" matcher ingen materialeregel | `server.py:1577` laver strengen; `pricing.py:225` matcher på hele strengen |
| `containers` er altid 1 på ture med registrering | `container_weights` fjernes for capture-ture, og `server.py:17229` falder tilbage til 1 |
| Haster vises ud fra noten, men prisen bruger kun `priority` | `tourHelpers.js:71` og `server.py` attrs `priority` |
| Én afventende rettelse blokerer den næste | `server.py:18164` |
| `PUT /tours` har ingen spærring for fakturerede ture | `price_locked` tjekkes kun i pris-endpoints, ikke i `update_tour` |
| Stop gemmer kun "HH:MM" | `server.py:3359` |
| `stops[].note` findes, men vises ingen steder | `server.py:1518`; ingen brug i App.js eller ToursWorkspace |
| Gods får aldrig "registrér mængde" som standard | `ToursWorkspace.jsx:239`: `qtyDefault = !goods && …` |
| Hængeren sættes automatisk ved start ud fra chaufførens profil | `server.py:3060-3066` |
| Dagtypen tages fra afslutningsdatoen | `_service_date`, `server.py:16972` |

To af fejlene har jeg selv lavet i sidste runde: "Opret pris" (F-2) og at gods ikke får mængde som standard (D-default). Dem bør vi rette først.

---

## 1. Konklusionen (afsnit A)

✅ **Enig i diagnosen.** Det er rigtigt, at stop, indhold, hængere og pris er bygget som fire tilføjelser oven på den gamle én-adresse-containertur. Det er den rigtige måde at beskrive, hvor det knirker. Det gik hurtigt at få virkende funktioner, fordi de gamle felter (`address`, `facility`, `fraction`, `used_trailer`) blev ved med at virke. Prisen er, at hver ny funktion skal oversættes tilbage til de gamle felter, og det er netop dér, fejlene sidder (hængere, materiale, containere).

⚠️ **Én nuance:** dokumentet kalder "tre afslutningsflows" et af de tre vigtigste problemer. Det er rigtigt teknisk, men det er **ikke** det, brugerne mærker mest i dag. B2B-chaufføren ser kun det ene flow, og premium-chaufføren ser kun FinishSheet. Brugerne mærker mest prisfejlene (F-2, F-5, F-1), fordi de giver forkerte eller manglende beløb. Derfor ville jeg flytte B3 længere ned (det gør dokumentet også i G).

---

## 2. Handlingslisten (afsnit G), punkt for punkt

### F-2: "Opret pris" skal også gælde turen, den blev åbnet fra · Must
✅ **Enig, og det er en fejl, ikke en forbedring.**
- **Hvorfor:** knappen lover at løse "Mangler pris", men gør det ikke. Brugeren tror, systemet er i stykker. Når en tur mangler pris, findes der ingen regel, der ellers ville have givet en anden pris. Derfor er det ufarligt at lade den nye aftale gælde bagud for den slags ture.
- ➕ **Jeg ville også:**
  - Efter gem skal brugeren blive i Rapport og se rækken få sin pris. I dag springer den til Prisregler (`EconomyPanel.jsx:239`, `setView("rules")`), og man mister konteksten.
  - Rette `effDate` (`:1304`): den bruger `toISOString()`, som er UTC. Mellem kl. 00 og 02 dansk tid bliver standarddatoen derfor i går.
  - Vise en lille bekræftelse: "Aftalen gælder også for N ture uden pris".

### F-5: Ét sandhedsfelt for hængere · Must
✅ **Enig i princippet** (`trailer_count_actual`, så planlagt, så `used_trailer`, og rettelser sender antal).
- **Hvorfor:** tre felter giver tre sandheder, og en godkendt rettelse, der ikke virker, er den værste slags fejl, fordi ingen opdager den.
- ⚠️ **Med én ændring om hænger-forslaget ved start (5b):** dokumentet foreslår at fjerne det automatiske "med hænger" fra chaufførprofilen. For B2B betyder det, at hængertillæg, der i dag opkræves, kan forsvinde. Det er en indtægtsbeslutning og din at tage. Mit forslag:
  - Ture med planlagt antal: brug det planlagte antal, og ignorér profilen.
  - B2B-ture: behold forslaget fra profilen, men vis det tydeligt ved afslutning ("Med hænger: Ja · ret"), så chaufføren aktivt ser det. Så opkræves der ikke noget, som ingen har set.
- ➕ Migrationen skal kun røre ture, der ikke er faktureret (som dokumentet siger). Jeg ville også skrive en revisionslinje pr. tur.

### F-1: Materiale som liste · Must
✅ **Enig, også i valget: grundpris kræver at *alle* linjer passer, tillæg kræver at *én* passer.**
- **Hvorfor:** "Beton + Træ" falder i dag stille igennem til en generel regel og får dermed en forkert, lavere pris. Den er værre end "Mangler pris", fordi den ikke ses. Kravet om at alle linjer passer er det sikre valg: en betonpris gælder kun rene betonture.
- ➕ Rapporten bør vise *hvorfor* en tur med flere materialer ikke fik en materialepris ("Turen har Beton + Træ, reglen gælder kun Beton"). Ellers ligner det samme fejl igen.

### D-kunde: Kunde fra registret · Must
⚠️ **Enig i målet, men løsningen bør være lidt anderledes.**
- **Hvorfor enig:** en stavefejl i kundenavnet giver i dag en ny kunde uden pris. Det sker i praksis.
- **Ændringen:** registret har allerede en `price_key` (`firma:<navn>`) pr. kunde. I stedet for en helt ny id-nøgle i prismotoren ville jeg:
  1. gemme `customer_ref_id` på turen;
  2. lade `customer_key()` slå kundens **faste** `price_key` op i registret;
  3. sørge for, at `price_key` ikke ændres, når kunden omdøbes.

  Så virker alle eksisterende prisregler uændret, og omdøbning bryder ikke priserne. Det er mindre risiko og mindre kode.
- ➕ "Opret ny kunde 'X'?" skal også foreslå en eksisterende kunde ved lignende navn ("Mente du Carlsberg Byen A/S?"). Det er dét, der forhindrer dubletter.

### F-4: Haster fra én kilde · Must
✅ **Enig. Jeg vælger retningen "backend sætter `priority`", ikke "UI holder op med at læse noten".**
- **Hvorfor:** chaufføren og planlæggeren *ser* "haster" i noten og forventer haster. At fjerne det fra UI ville skjule information. Det rigtige er:
  - ved oprettelse og import: står der "haster" i noten, sættes `priority = urgent`;
  - en engangsrettelse af ikke-fakturerede ture;
  - derefter læser UI kun `priority`.
- ➕ Push for nye haster-ture bruger samme felt, så den rettelse får push med.

### B2-b: Note pr. stop · Must
✅ **Enig.** Feltet findes allerede, så det er lille og uden risiko. "Port 3, ring til Hans" er præcis den information, chaufføren mangler ved flere stop.
- ➕ Samme sted: valgfri **kontakt (navn + telefon) pr. stop** med en Ring-knap hos chaufføren. Det er dokumentets punkt i D-tabellen, men jeg ville lave det samtidig, fordi det er samme formular og samme stop-kort.

### D-default: Mængde = ja på gods når en linje har antal; container nr. fremme · Must
✅ **Enig.** Det er min fejl fra sidste runde. "12 paller" uden afstemning modsiger hele idéen med linjens enhed. Container nr. er det første, en containerchauffør leder efter.

### E1: Prisstatus på Ture-siden · Must
✅ **Enig.** At opdage "Mangler pris" først ved månedens fakturering er for sent. På Ture-siden kan planlæggeren rette det samme dag.
- ⚠️ **Kun status, aldrig beløb.** Status vises kun for brugere med økonomi-adgang, så en koordinator uden den ikke ser noget. Ellers lækker vi information.
- ➕ Det samme endpoint kan bruges til opmærksomhedslinjen ("3 ture mangler pris i dag").

### C1: Stop med kvittering (ISO-tid, ankomst, modtager, billede, afvigelse) · Should
⚠️ **Enig i C1, men delt i to:**
- **C1a (lille):** ISO-tidsstempel, afvigelse pr. stop ("kunne ikke afleveres" + kode) og modtagernavn. Det er det, der gør flere stop brugbare.
- **C1b (større):** billede pr. stop og "Ankommet"-knap. Ankomst-tid giver kun værdi, hvis nogen bruger den (fx ventetid). Den kan vente.
- **Hvorfor:** "hele turen er forgæves" er forkert ved 5 stop, når kun ét fejler. Det skal løses. Ankomst-knappen er derimod endnu et tryk med handsker, uden at nogen har bedt om det.

### C2: Linjer pr. afleveringsstop · Should
⚠️ **Enig i modellen (valgfrit, "alt fra A til B" som standard), men lavere prioritet end per_unit.**
- **Hvorfor:** "5 til Helsingør, 4 til Hillerød" er rigtigt, men sjældnere end "12 paller fra A til B". `per_unit` (pris pr. palle) hjælper hver gods-tur. C2 hjælper kun ture med flere afleveringer. Der skal også afstemmes på to niveauer, og det giver mange kanttilfælde. Jeg ville lave den, efter at C1a har været i brug et stykke tid.

### C3: Afvigelseskoder · Should
✅ **Enig.** Koder er forudsætningen for at måle og fakturere forgæves kørsel, og de er billige at lave. FinishSheet har allerede hurtigvalg; de skal bare gemmes som kode og ikke kun som tekst.
- ➕ Listen skal kunne vedligeholdes pr. firma i Indstillinger, ikke kun i koden. Containerpladser og godsfirmaer har forskellige årsager.

### F-7: Forgæves kørsel · Should
✅ **Enig.** "Mangler pris" uden forklaring, selv om der findes en forgæves-regel (ved timepris), er forvirrende.
- ➕ Standardtillægget "Forgæves kørsel" i aftale-editoren bør ligge som et valgfrit tillæg ved siden af de andre, ikke som en separat regel.

### F-6: Antal containere på containerture med flere linjer · Should
✅ **Enig.** "3 containere" skal give 3 × containerpris. Den nemmeste og mest forudsigelige regel er antallet af containerlinjer. Har en linje et antal, tæller antallet.

### F-per_unit: Grundpris pr. enhed (palle, kolli, m³, ton) · Should
✅ **Enig. Det er den vigtigste prisudvidelse for gods.**
- **Hvorfor:** uden den ender hver gods-tur med paller som aftalt pris. Det betyder ingen regler, ingen simulator og ingen historik, altså præcis det, prisaftalerne skulle løse.
- ➕ Regn på registreret antal, når det findes, ellers på planlagt antal, og vis hvilket i prisopbygningen ("6 paller, registreret").
- ➕ Brug **minimum** frem for "inkluderet antal" som første version. "Min. 1.000 kr" er den måde vognmænd normalt aftaler pris pr. palle på.

### F-stop: Stoptillæg · Should
✅ **Enig, med 2 stop inkluderet som standard.**
- ➕ Stop med afvigelse ("kunne ikke afleveres") skal tælle med som standard. Chaufføren kørte derhen, og det koster det samme. Dokumentet foreslår det modsatte, og der er jeg uenig.

### F-3: Aftalt pris ved flere ture · Should
⚠️ **Enig i, at der skal spørges, men uenig i standardvalget for "separate ture".**
- **Gentag:** "pr. tur" som standard. En fast daglig tur aftales pr. gang.
- **Separate ture:** "samlet (deles)" som standard. Det er én opgave, der kun er delt op af planlægningsgrunde, så kunden har fået én pris. Ellers ganges prisen med 3, uden at nogen opdager det.

### F-10: Ventetid uden regel og flere rettelser pr. tur · Should
✅ **Enig i begge dele.** At godkende ventetid, der giver 0 kr uden advarsel, er en skjult fejl. At én afventende rettelse blokerer den næste, rammer FinishSheet direkte, fordi ventetiden sendes som rettelse ved afslutning. Derefter kan chaufføren ikke rette tiden.
- ➕ Overvej en indstilling, så kort ventetid (fx højst 15 min) godkendes automatisk. Det sparer planlæggeren for mange små godkendelser.

### F-12: Tydeligere "hvilke ture gælder prisen for?" · Should
✅ **Enig.** Forskellen mellem "oprettet fra" og "kørt fra" er den mest forvirrende del af prisdelen i dag. Ved en prisstigning 1. januar mener man næsten altid "kørt fra". Dokumentets tre valg er de rigtige.

### B3: Ét afslutningsflow for alle ture · Should
⚠️ **Enig i retningen, men ikke før de små prisrettelser, og kun bag et flag.**
- **Hvorfor enig:** tre kopier af vægtlogikken betyder, at hver ny funktion (fx kvittering pr. stop) skal bygges tre gange.
- **Hvorfor forsigtig:** B2B er det flow, der virker og giver penge. Backend-kravet (vægt påkrævet) skal blive uændret, så frontend ikke kan bryde det. Scanner til vejeseddel og spejling til bestillingen skal testes før og efter.
- ➕ **Før B3:** ét endpoint `POST /tours/{id}/finish`, der tager hele afslutningen i ét kald og tåler at blive sendt to gange. Se afsnit 4.

### D-serie: `series_id` på gentagne ture · Should
✅ **Enig.** At rette 20 ture hver for sig er tydeligt spild. "Ret alle fremtidige" og "Slet resten af serien" er standard i alle kalendere.

### B2-d: Chaufføren tilføjer selv et stop · Could
✅ **Enig som Could, efter C1a.** Det er rigtigt self-service, men giver kun mening, når stop har afvigelser og kvittering.

### F-8: Dagtype fra startdato · Could
✅ **Enig.** En tur, der startes fredag 23:30, er en fredagstur. Det ændrer prisen for ture over midnat, så det skal stå i PRD og kun gælde ikke-fakturerede ture.

### F-9: Leveringsadresser for egne lokationer · Could
⚠️ **Enig i problemet, men gør først den lille løsning:** skjul betingelsen "Leveringsadresse" for egne ture i editoren, så ingen laver en regel, der aldrig virker. Modtageanlæg i registret (M) kan komme, hvis der bliver efterspørgsel.

### E2/E3/E5: Chips og filtre (mangler registrering, afvigelse, afventer godkendelse) · Could
⚠️ **Enig, men E3 (afvigelse) bør op på Should.** Planlæggerens kl. 16-gennemgang handler netop om afvigelser. Registreringen er værdiløs, hvis ingen ser afvigelserne. E2 og E5 kan vente.

### F-14: Vis "indregnet i aftalt pris" · Could
✅ **Enig.** Det er lille og fjerner spørgsmålet "hvorfor er der ingen weekend på denne tur?".

### B-offline: Offline-kø · Could
⚠️ **Mener det bør op på Should**, i hvert fald for Start, Afslut og stop-kryds. Dækning på containerpladser og i kældre er dårlig. En afslutning, der fejler halvvejs, er netop dét, der giver "afsluttet uden hænger-info" (se afsnit 4, punkt 1).

### B-nav: "Næste tur" efter afslutning · Could
✅ **Enig.** Lille og rart.

### Oprydning · Could
⚠️ **Delvist enig:**
- ✅ Skjul "Lav prioritet" i formularen, men behold værdien i backend.
- ❌ **Fjern ikke `is_private` fra data.** Det bruges i ældre "firma tur"-stier og rapporter. Skjul det i UI og afled det ved gem, men lad feltet blive.
- ✅ Slet legacy-afslutning først, når B3 har kørt en release uden problemer.

### Bilag 2: Små fund
- ✅ **Spær registrering på fakturerede ture i backend.** Det bør op på **Must.** I dag kan "Ret registrering" ændre mængde og billeder efter fakturering. Prisen er frosset, men registreringen passer så ikke længere med fakturaen, og det er et revisionsproblem.
- ✅ **Billeder som binær download** frem for base64 i én liste. Should, så snart der kommer billeder pr. stop.
- ✅ **Ét `/finish`-kald** i stedet for 3–4 kald efter hinanden. Should (se afsnit 4).
- ✅ **Ingen CO2-kolonne for gods** i Rapportering. Lille.
- ✅ **`trailer_counts` "3+"** står allerede som "3+" i editoren. Det skal blot dokumenteres.

---

## 3. Øvrige beslutninger i dokumentet

### B3-matricen (self-service kontra godkendelse)
✅ **Enig i hele matricen.** Princippet er rigtigt: *det, chaufføren registrerer i øjeblikket, er self-service; det, der ændrer prisen bagefter, kræver godkendelse.* Det er også sådan, det er bygget i dag, bortset fra at hængerrettelser er ja/nej i stedet for antal (F-5).

### Stop-modellen (C3, valg 2)
✅ **Enig i valget af model 2** (valgfrie linjer pr. stop) frem for model 3 (ordrelinjer som egen samling). Model 3 ville bryde "én opgave = én tur", som vi lige har indført, og røre rapport, PDF og ordrespejling. Se dog min rækkefølge for C1 og C2 ovenfor.

### Felterne i Ny tur (afsnit D)
- ✅ **Container nr. fremme for container, og Haster som chip fremme.** Det er det mest brugte.
- ✅ **Antal og enhed også på containerlinjer.** Det er nødvendigt for F-6.
- ⚠️ **Billede = ja som standard ved gods-levering:** jeg ville i stedet gemme standarden **pr. kunde i registret** ("Kunden kræver billede ved levering"). Det er kunden, der kræver dokumentation, ikke opgavetypen. Et billede for meget gør chaufførerne trætte af funktionen.
- ⚠️ **Underskrift:** Could. Navn + tid + billede dækker 95 %. Underskrift med handsker på en telefon er bøvlet.
- ✅ **Skabeloner** senere.

### Ture-oversigten (afsnit E)
✅ **Enig i, at kroner ikke hører til på Ture-siden; status gør.**

---

## 4. Ting jeg ville tilføje (ikke i dokumentet)

Det her ved jeg fra arbejdet i de sidste runder:

1. **Ét `POST /tours/{id}/finish`, der tåler gentagelse (Should, før B3).**
   - **Problem:** FinishSheet sender i dag hænger, afslutning, besked og ventetid som fire kald efter hinanden. Ryger dækningen efter kald 1, er hængeren gemt, men turen ikke afsluttet. Trykker chaufføren igen, kan beskeden komme to gange.
   - **Løsning:** ét kald med et engangs-id. Det er også det, offline-køen skal sende.
2. **Flyt mine end-to-end-tests ind i repoet (Must, lille).**
   - **Problem:** testene for B2B, gods, stop, prisaftaler og push ligger kun i min midlertidige mappe og forsvinder med sessionen.
   - **Løsning:** læg dem i `backend/tests/e2e/` med oprydning og en fast dato (de afhænger i dag af ugedagen; i lørdags gav weekendtillægget et "forkert" resultat). Uden dem er B3 og F-5 for risikable at lave.
3. **Spær registrering på fakturerede ture (Must).** Se Bilag 2 ovenfor. Backend skal afvise ændringer af mængde, billede og hængere, når `price_locked` er sat, med beskeden "Turen er faktureret – kontakt din logistik admin".
4. **Rapport: forklar "Mangler pris".** I stedet for kun "Mangler pris" skal der stå, hvilken betingelse der ikke passede ("ingen regel for kunden", "materiale Beton + Træ", "forgæves – ingen forgæves-regel"). Prissimulatoren kan allerede det meste af dette, så det er mest UI.
5. **Rettelser af `effDate`, UTC og standardvalg i prisaftalen** (se F-2) samles i samme pakke.
6. **Krav pr. kunde i registret:** "kræver billede", "kræver vejeseddel" og "aftalt minimum". Så følger standarderne i Ny tur kunden automatisk, og planlæggeren skal huske mindre.
7. **Koordinator-adgang pr. egen kunde:** når turen har `customer_ref_id` (D-kunde), kan en koordinator begrænses til fx "kun Carlsberg". I dag kan adgangen kun være "egne ture" eller bestemte B2B-kunder. Could.

---

## 5. Spørgsmålene i afsnit H: mit svar

| # | Spørgsmål | Dokumentets svar | Mit svar |
|---|---|---|---|
| 1 | Pris efter oprettelses- eller kørselsdato? | Behold oprettelse; "kørt fra" ved prisstigning | ✅ Enig |
| 2 | Aftalt pris ved flere ture | Pr. tur, men spørg | ⚠️ Pr. tur ved Gentag, **samlet** ved "separate ture" |
| 3 | B2B over i det nye afslutningsark? | Ja, med flag | ✅ Enig, men efter `/finish` og e2e-tests i repoet |
| 4 | Kvittering: navn + tid + billede nok? | Ja, underskrift valgfri | ✅ Enig |
| 5 | Chauffør tilføjer stop? | Ja, markeret | ✅ Enig, efter C1a |
| 6 | Pris pr. enhed nu? | Ja for gods | ✅ Enig, med minimumspris |
| 7 | Stop inkluderet | 2 | ✅ Enig, og stop med afvigelse tæller med |
| 8 | Hænger: fri ved afslutning, godkendelse bagefter | Ja, med antal | ✅ Enig |
| 9 | Forgæves: gebyr + koder | Ja | ✅ Enig, koder pr. firma |
| 10 | Kunderegister obligatorisk? | Nej, men opret efter bekræftelse | ✅ Enig, med forslag af lignende navne |

**Spørgsmål kun du kan svare på:**
- **(A) F-5b:** må hængertillæg på B2B-ture fortsat foreslås ud fra chaufførens profil (mit forslag, men vist tydeligt ved afslutning), eller skal det kun opkræves, når nogen aktivt har valgt det?
- **(B) F-3:** er du enig i "samlet" som standard ved separate ture?

---

## 6. Min anbefalede rækkefølge (i pakker, der kan testes hver for sig)

| Pakke | Indhold | Størrelse |
|---|---|---|
| **1. Prisfejl, der giver forkerte beløb** | F-2 (+ bliv i Rapport, `effDate`), F-5, F-1, F-4, spærring ved faktureret, e2e-tests i repoet | 1–2 dage |
| **2. Små ting i Ny tur og for chaufføren** | D-default, container nr. fremme, Haster-chip, B2-b note + kontakt pr. stop, ISO-tid på stop | 1 dag |
| **3. Synlighed for planlæggeren** | E1 prisstatus, E3 afvigelse, "Mangler pris" forklaret | 1–2 dage |
| **4. Kunde og forgæves** | D-kunde (via `price_key`), C3 koder, F-7, F-6, F-10 | 2–3 dage |
| **5. Gods-pris** | per_unit (med minimum), stoptillæg, F-3, F-12, F-14 | 2–3 dage |
| **6. Stop med kvittering og serier** | C1a, D-serie, derefter B2-d | 3–4 dage |
| **7. Robust afslutning** | `/finish`-endpoint, offline-kø, B3 bag flag | 3–5 dage |
| **Senere** | C1b, C2, F-8, F-9, E2/E5, skabeloner, underskrift | – |

Pakke 1 og 2 er små og retter det, brugerne mærker. Pakke 7 er den eneste med reel risiko for B2B og kommer derfor sidst, med tests foran.
