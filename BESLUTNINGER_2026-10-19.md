# Beslutninger 2026-10-19: Bestil for kunden, annullering, kort-knap, partner

Arbejdsmetode: For hver beslutning er mindst 3 alternativer vurderet, og den
valgte løsning er gennemtænkt i 5 runder: mangler der noget, er der fejl i
processen, og bør det gøres anderledes? Til sidst er hele kæden stresstestet
(kunde → logistik → chauffør → økonomi/CO2) i e2e-testen `flow_behalf.py`.

---

## 1. Logistikfirmaet opretter på en genbrugsplads = "Bestil for kunden" (begge pakker)

**Fundet:** En tur, som logistikfirmaet oprettede på kundens plads (Ny tur,
Kopiér eller Excel), fik ingen bestilling. Kunden så den derfor ikke under Mine
bestillinger, i rapporterne eller i CO2-tallet, kun i Arkiv med 0 kg CO2.
Kunden kunne heller ikke annullere den, men betalte for den.

**Alternativer:**
- A. Som før.
- B. Fjern for alle.
- C. Fjern kun for partnere.
- D. Kunden godkender et forslag.
- **E. Bestilling på kundens vegne (valgt).**
- F. E plus en indstilling hos kunden.

**Valgt E, for partner og premium.** Det rigtige på en genbrugsplads afhænger
af pladsen og kundens data, ikke af logistikfirmaets pakke.

**Runde 1 – mangler der noget?**
- Formularen bruger kundens egne valg: materialer og containere (kun dem firmaet
  kører), leveringsadresse og åbningstid fra kundens kalender for netop den dag
  (inklusive låste adresser og tider samt lukkedage), og kundens værksteder.
- "Hvem bad om det?" er påkrævet, fx "Jens, telefon".
- Planlæggeren kan tildele chauffør og antal hængere direkte i formularen.

**Runde 2 – proces:**
- Samme oprettelse som bestillingssiden (`_create_customer_order`): tjek for
  dobbeltbestilling, CO2-kategori, partner og haster-push.
- Formularen viser en åben bestilling på samme container, før der sendes.

**Runde 3 – data til alle ender:**
- Kundens Mine bestillinger viser "Bestilt af X for jer · Jens, telefon" (også
  under "Mine", da bestillingen er til pladsen).
- Lokationsadmins Bestillinger og Arkiv viser "X for jer".
- Rapporter og CO2 tæller bestillingen; den står under firmaet og ikke under
  planlæggerens navn.
- Historik viser "oprettet for jer". Historik-knappen havde intet endpoint og
  er rettet.
- Chaufføren ser "Bestilt af X for kunden (Jens)".
- Økonomi bruger kundens priser, fordi kunden ejer turen.

**Runde 4 – premiums egen logistik:**
- Fri "Ny tur" er uændret på egne lokationer, for egne kunder og på fri adresse,
  med Fragt, stop, Gentag, hængere med indhold og krav ved afslutning
  (e2e-test 10).
- Premium får "Ny tur" og "Bestil for kunde". Vælger planlæggeren en kundes
  plads i Ny tur, skifter formularen til bestilling.
- Skriver planlæggeren en fri adresse, der er en kundes genbrugsplads, kommer
  der en blød hint: "bestil for kunden". Det blokerer ikke.

**Runde 5 – fejlsituationer:**
- **Tastefejl:** "Ret bestilling" virker kun på firmaets egne bestillinger for
  kunden. Kundens egne bestillinger retter kunden selv.
- **Planlæggeren kan flytte dato og prioritet** på alle bestillings-ture.
  Kundens bestilling følger med, og ændringen kommer i historikken. Før blev
  den gamle dato stående hos kunden.
- **Materiale, container, adresse og opgave på en bestillings-tur** kan kun
  rettes i bestillingen. Serveren afviser ændringen med 409, så tur og
  bestilling aldrig siger noget forskelligt.
- **Kopiér af en bestilling** hedder nu "Bestil igen" og giver en ny bestilling.
  Massekopiér springer bestillinger over.
- **Excel-rækker på en kundes plads** bliver bestillinger.
  - Rettet undervejs: skabelonen manglede en dato-kolonne (alt fik dags dato).
  - Rettet undervejs: vejledningen nederst i arket blev læst som 7 fejlrækker.
  - Rettet undervejs: rækker på egne lokationer får nu turnummer, tjek for
    dobbeltbestilling og haster.
- **Gamle åbne ture uden bestilling** på kundepladser har fået en bestilling
  "for kunden" (engangsrettelse).
  - Afsluttede ture er ikke ændret, så kundens tidligere rapporter ikke ændrer
    sig bagud.

**Usikkerhed:** Kunden får ingen e-mail, når der bestilles for dem. De ser det
tydeligt i appen. Hvis kunder efterspørger det, kan en daglig opsummering til
lokationsadmin være bedre end én e-mail pr. bestilling.

---

## 2. Annullering – også efter at chaufføren er kørt

**Fundet (alvorligt):**
- Turens datamodel smed "annulleret" væk. En annulleret bestilling lå derfor
  stadig som en almindelig tur hos chaufføren og planlæggeren og kunne startes
  og køres.
- Kunden så sin annullerede bestilling som "Afventer" med knapperne Redigér og
  Annullér.

**Alternativer:**
- A. Kun før start (som før).
- B. Altid, også efter afhentning.
- C. En anmodning, som chaufføren eller planlæggeren godkender.
- **D. Valgt: til turen er kørt.** Er chaufføren på vej, skal kunden bekræfte.

**Valgt D. Reglerne:**
- **Afhentet:** kan ikke annulleres, for vægt, CO2 og pris hører til.
- **Før start:** kunden annullerer.
- **På vej:** kunden skal bekræfte "kan koste en forgæves kørsel".
  - Turen bliver forgæves med koden "Annulleret af kunden".
  - Aftalens forgæves-pris gælder, og planlæggeren ser turen i Økonomi før
    fakturering.
- **Logistikfirmaet** kan annullere på kundens anmodning, men kun før start og
  kun med en begrundelse, som kunden ser.

**Runde 1 – synlighed:**
- Chaufføren får push med det samme, hvis turen var tildelt eller i gang.
- På kortet står "Turen er annulleret · Af … : begrundelse", og
  start/afslut-knapperne forsvinder.
- Planlæggeren ser status "Annulleret" (ny filterknap) med hvem, hvornår og
  hvorfor. Turen tæller ikke længere som "ikke tildelt" eller "haster uden
  chauffør".

**Runde 2 – offline-køen:**
- Afslutter chaufføren en annulleret tur fra telefonen uden net, svarer
  serveren 409: "kontakt planlæggeren".

**Runde 3 – kørt alligevel:**
- "Genoptag bestilling" (med begrundelse) gør bestillingen aktiv igen.
- Var chaufføren på vej, beholder han turen og kan afslutte den. Bestillingen
  bliver så afhentet med vægt og CO2.

**Runde 4 – spejling:**
- Når turen opdateres, overskriver det ikke længere "annulleret" på
  bestillingen.
- "Genaktivér" (for "kunne ikke gennemføres") kan ikke genåbne en tur, kunden
  har annulleret. Endpointet havde i øvrigt intet firma-tjek; det har det nu.

**Runde 5 – rapporter:**
- En annulleret bestilling tæller ikke i CO2.
- "Afventer" i kunderapporterne talte på et felt, der aldrig blev gemt. Det
  tæller nu på status.

**Usikkerhed:** Skal en forgæves kørsel på grund af kundens annullering altid
koste noget? Det følger aftalens forgæves-pris. Uden en forgæves-pris i aftalen
står turen som "mangler pris", indtil planlæggeren tager stilling.

---

## 3. Kort-knappen i chaufførappen

**Fundet:** Turens "adresse" betyder leveringsstedet på en bestilling, men
afhentningsstedet på en manuel tur. Knappen gik derfor nogle gange til det
første sted og nogle gange til det sidste, og detaljevisningen kaldte pladsen
for "Modtageanlæg".

**Alternativer:**
- A. Altid det første sted.
- B. Altid det sidste sted.
- C. Hele ruten med pladsen som mellemstop.
- D. Valg efter GPS.
- **E. Valg mellem stederne i køreorden (valgt).**

**Runde 1 – mangler:**
- Turen havde ikke pladsens egen adresse, så "Hent på pladsen" kunne ikke
  navigeres. Nu har den `plads_address` og `delivery_name`, fx "HCS A/S
  Helsingør". Åbne ture er rettet.

**Runde 2 – fejl:**
- Rettet: fra 2026-10-19 blev pladsens by sat på en leveringsadresse uden by.
- Felternes betydning i databasen er ikke ændret, fordi priser, rapporter og CO2
  bruger dem. Én funktion (`routeOf`) oversætter for alle skærme.

**Runde 3 – særtilfælde:**
- Afhent fra værksted: værkstedet først (containeren står der), så pladsen.
- Byt container: ét sted, så Google Maps åbner direkte.
- Stop-ture: næste stop som før.

**Runde 4 – samme rute alle steder:**
- Chaufførens kort, chaufførens detaljevisning (et link pr. sted) og
  planlæggerens tur-panel bruger samme rute.
- Planlæggerens "Kort" viser hele ruten fra første til sidste sted.

**Runde 5 – Google Maps:**
- Alle links bruger vejvisning med ", Danmark", så en adresse som "Folehaven 1"
  ikke lander i udlandet.

---

## 4. Partner (ikke-premium) – hvad der ikke gav mening

**Rettet:**
- **"Ret" på en tur** viste mængde/billede, stop, linjer og "Godkend stop", men
  serveren smed det væk, og der stod alligevel "gemt". Felterne skjules nu.
- **Seriefelterne** skjules uden Gentag.
- **Falske afvigelser:** "Hængere 0 → 1" kom på alle partner- og
  bestillings-ture. Afvigelsen vises nu kun, når der er planlagt hængere.
- **Antal hængere er nu kerne** (krogløfter med anhænger), mens indhold og pris
  pr. hænger stadig er premium.
- **Økonomi** viser ikke længere prisvalg, der aldrig kan ramme en partnertur:
  "Ekstra stop", "Pris pr. enhed" og opgavetyper til Fragt.
- **Tekster:** "Flere detaljer" og Helligdage følger nu det, partneren faktisk
  har.
- **En gemt "Fragt"-standard** giver ikke længere en formular uden valgt opgave.
- **API:** en partner kan ikke flytte en tur til en skjult egen lokation, og
  ingen kan flytte en tur ind på en kundes plads.
- **Gammel import (`/import-argo`)** gik uden om alle kontroller og er nu kun
  for super admin.
- **Premium ser ikke længere partnerformularen et øjeblik**, mens profilen
  indlæses.
- **Sikkerhed (pushet tidligere i dag):** en kunde-bruger kunne rette ethvert
  firmas tur. Logistikfirmaet fik "ikke fundet", når det slettede ture på
  kundens plads.

**Ikke rettet (lav værdi, noteret):**
- En partner uden kunder ser tomme faner uden for Ture.
- Rettigheden hedder "Lokationer" og ikke "Genbrugspladser".

---

## 5. Faste tømninger og "Bestil igen" (bygget samme dag)

**Valgt:** Faste tømninger pr. container hos lokationsadmin og kundeadmin, plus
"Bestil igen" på en tidligere bestilling.

**Alternativer:**
- A. Ingenting.
- B. "Gentag" for alle medarbejdere.
- **C. Faste tømninger pr. container (valgt).**
- D. Kun "Bestil igen".
- E. Påmindelse dagen før.
- F. Sensorer.

**Runde 1 – mangler:**
- Opsætning: ugedage, hver 1.–4. uge, periode (fx sæson), partner (når pladsen
  har flere), opgave (afhent eller byt), prioritet og kommentar.
- Forhåndsvisning af de næste datoer.
- På listen: hvad der er bestilt, og hvad der er sprunget over (lukket dag,
  manglende leveringsadresse).

**Runde 2 – proces:**
- Hver tømning bliver en almindelig bestilling 7 dage før gennem samme
  oprettelse som bestillingssiden. Leveringsadresse og åbningstid hentes for
  netop den dag.
- Lukket leveringssted (helligdag) betyder, at tømningen springes over og
  logges.
- Dobbeltbestillings-tjekket lader nu en ekstra bestilling en anden dag
  komme igennem (containeren blev fuld før tid). Samme dag er stadig
  dobbelt.

**Runde 3 – fejlsituationer:**
- Hver kombination af skema og dato oprettes højst én gang (unikt indeks), også
  med flere app-instanser og ved genstart.
- "Spring over" er en annullering af den ene dag; den oprettes ikke igen.
- Pause og stop annullerer de bestilte, ikke startede tømninger. Genoptag
  opretter dem igen, men ikke dem, der blev sprunget over.

**Runde 4 – ret:**
- Partner, materiale, container og opgave er selve tømningen. De kan ikke
  rettes; man stopper den og opretter en ny.
- Ugedage, interval, periode, prioritet og kommentar kan rettes:
  - bestilte datoer, der ikke længere passer, annulleres;
  - de øvrige får den nye prioritet og kommentar.

**Runde 5 – alle ender:**
- Mærket "Fast" i Mine bestillinger, som alle på pladsen ser.
- Knappen "Spring over" i stedet for "Annullér".
- Ture viser "Fast tømning" og hvornår.
- Chaufføren ser noten "Fast tømning · Man, Tor · hver uge".
- Rapporter tæller tømningerne under "Fast tømning".
- Testet i e2e-testen `flow_fixed` (15 tjek).

**Usikkerheder:**
- "Hver 4. uge" bruges som månedlig. Ønskes "første mandag i måneden", er
  det en lille udvidelse.
- De 7 dage er fast for nu (feltet `lead_days` findes på skemaet).

---

## 6. Priser der skiftede i Økonomi › Rapport (fundet 2026-10-19)

**Årsag (bevist):** Mine e2e-tests kørte mod den samme lokale database, som du
bruger i browseren.
- For at få faste resultater slår testene midlertidigt firmaets egne
  prisregler fra og opretter "E2E …"-regler.
- Mens testen kørte, viste TUR-0671 "Nærmeste regel 'E2E HF kundepris' passer
  ikke på: kunde". Bagefter var den 1.460 kr igen.
- Reproduceret ved at aflæse prisen 2 gange i sekundet under en testkørsel.
- Dine egne regler var urørte.

**Alternativer:**
- A. Advare før testkørsel.
- B. Skrive testene om, så de ikke slår regler fra.
- **C. Egen testdatabase og egen test-app (valgt).**

**Løsning C:** `./scripts/e2e.sh`.
- Hver kørsel får en frisk database (`containerflow_e2e`) med testdata og en
  separat app på port 8081.
- Testene nægter at køre mod din database.
- Det, testene manglede (koordinator, ILK's egen lokation, partner nr. 2 på
  Folehaven), oprettes af `_fixtures.py`.

---

## 7. Chaufførens adresser og kort-knappen (2. runde)

**Feedback:** Et kort-ikon uden tekst siger ikke, hvor det fører hen.

**Valgt:** Ruten står på kortet i køreorden, og hvert sted har sin egen
"Kør"-knap:
1. Hent · Nordkysten – Folehaven 1: Folehaven 1, Hornbæk [Kør]
2. Aflever · HCS A/S Helsingør: Energivej 10, 3000 Helsingør [Kør]

Ingen skjulte valg. Stop-ture viser næste stop med "Kør".

**Skærmbilledet med "Aflevering" og "Adresse" ens** var det gamle layout. En
side, der står åben, beholder den gamle kode, til den genindlæses. Derfor:
- Banner: "Der er en ny version af ContainerFlow · Tryk for at opdatere".
- Turen "test" havde samme adresse som afhentning og aflevering. Den vises nu
  som ét sted ("Hent og aflever"), og Ny tur advarer, når de to adresser er
  ens.

---

## 8. Containerlisten i "Bestil for kunden" + "Overskriv" (2026-10-20)

**Krav:** Listen skal være lokationens containere, og de rigtige, da en lokation
kan have flere logistikfirmaer. Det skal være muligt at overskrive
containernummeret.

**Alternativer:**
- A. Kun containere med nummer, som på bestillingssiden.
- **B. Alle lokationens containere for det bestillende firma, også dem uden
  nummer (valgt).**
- C. Alle firmaers containere.

**Runde 1 – kilde:** Samme kilde som bestillingssiden (containerantal pr.
logistikfirma plus fælles containeropsætning). Det bestillende firma ser kun
sine egne. Fx har Test Partner pap-containeren på Folehaven, så ILK ser den
ikke.

**Runde 2 – visning:** "Nr. 5555 · Container 1 · Lukket container 30 m³".
Nummeret står først, fordi det er det, planlæggeren kender fra pladsen.
Containere uden nummer står som "Intet nr.".

**Runde 3 – Overskriv:**
- Skriver planlæggeren et andet nummer på en container, bestilles den med det
  nummer.
- Har kunden låst nummeret, gælder låsen. Det indtastede bestilles så som en
  anden container, og formularen siger det.
- Har firmaet ingen containere for materialet, skrives nummeret direkte.

**Runde 4 – samspil:**
- "Bestil igen" kender kun nummeret (fx 12345). Det slås op i listen, og findes
  det ikke, udfyldes det som et overskrevet nummer.
- Tjekket for dobbeltbestilling og leveringsadressen bruger pladsens navn for
  containeren.

**Runde 5 – test:** e2e 33–36:
- listen pr. firma, også containere uden nummer;
- "Overskriv" på en container uden lås;
- låst nummer bevares;
- manuelt nummer uden for listen.

## 9. Månedlige faste tømninger (2026-10-20)

"Hver 4. uge" glider i forhold til måneden. Små fraktioner tømmes ofte
månedligt. Derfor findes nu valget "Månedligt" med første, anden, tredje,
fjerde eller sidste valgte ugedag i måneden (fx "Første mandag i måneden").

Varslet på 7 dage er beholdt fast. Det er én ting mindre at forklare
lokationsadmin, og logistikfirmaet har altid en uge at planlægge i.

e2e: flow_fixed 16.

## 10. Faste tømninger – datoliste, hvad der opretter dem, og containernummer (2026-10-20)

- **"Næste" lignede dubletter.** Kortet viste de næste 6 datoer og under dem
  de datoer, der allerede var bestilt, så det lignede samme datoer plus én.
  Nu er der én liste: hver dato én gang med status ("Bestilt", "Bestilles
  tor. 22.10", "Sprunget over", "Lukket", "Chaufføren er i gang").
- **Hvad opretter bestillingerne:** app-serveren.
  - Med det samme, når den faste tømning gemmes.
  - Hver time i baggrunden.
  - Nyt: når appen bruges (Ture, chaufførappen, bestillingssiden), højst hvert
    10. minut.

  Grunden er, at Scaleway Serverless kan lukke containeren ned, når ingen
  bruger appen, og så kører timejobbet ikke. Indhentningen sikrer, at de
  oprettes, så snart nogen bruger appen. Med 7 dages varsel er der god margin.
  Hvis I altid vil have mindst én kørende instans, kan "min scale = 1" sættes
  i Scaleway.
- **Hvorfor 7 dage frem og ikke hele perioden på én gang:**
  - Logistikfirmaet ser en uge frem og kan planlægge chauffører.
  - Leveringsadresse og åbningstid hentes for netop den dag. Kalenderændringer
    og helligdage, der lægges ind senere, kommer med.
  - Ret, pause og stop har kun få bestillinger at rydde op i.
  - Mine bestillinger og Ture fyldes ikke med måneder af fremtidige
    bestillinger.
  - Prisen versioneres ved oprettelse og følger dermed aftalen, som den er
    ugen før.
- **"Container-nr. ikke angivet"** på en bestilling med et manuelt nummer.
  - Nummeret lå i bestillingen, men listen viste kun numre fra pladsens
    containeropsætning.
  - Nu vises det manuelle nummer på bestillingssiden og hos lokationsadmin.
  - e2e: behalf 37, fixed 14a.

---

## 11. Basic vs. Premium for logistikfirmaer (2026-10-20)

**Spørgsmålet:** Skal "Beskeder" fjernes for basic for at gøre forskellen til
Premium større? Og skal basic være enklere, så kunderne kan onboarde deres
logistikfirmaer uden friktion?

**Konklusion:**
- **Nej til at fjerne beskeder.** De gør kundens ture bedre (sporbarhed ved
  klager, færre forgæves ture), og ingen opgraderer for at kunne skrive til sine
  egne chauffører.
- **Ja til større forskel**, trukket efter hvem der har gavn af funktionen.
  Logistikfirmaets egen drift (Økonomi, Tid & ressourcer, Rapportering,
  koordinatorroller) blev Premium. Det gør basic enklere og giver Premium en
  klar historie.

**Alternativer:**
- A. Som før.
- B. Fjern beskeder m.m. fra basic.
- **C. Opdel efter hvem der har gavn (valgt).**
- D. Alle får Premium i en prøveperiode og falder så tilbage.
- E. Kun enklere skærme, uden at flytte funktioner.

**Runde 1 – mangler:**
- Basic skal stadig kunne fakturere. Historik-eksporten har fået tur-nr.,
  haster, hængere, ventetid og afvigelse.
- Ventetid oplyst ved afslutning står nu på turen.

**Runde 2 – ting der hang på tidsregistrering:**
- Haster-push gik kun til chauffører, der havde stemplet ind. Uden stempling går
  den nu til alle aktive chauffører.
- "Afslut dag" stemplede automatisk ud; uden tidsregistrering springes det
  over.
- Chaufførappen åbnede på "Tid"-fanen; uden tidsregistrering åbner den på Ture.

**Runde 3 – Team:**
- Basic kunne kun invitere koordinatorer med rettigheder. Nu inviterer basic
  "kolleger" med fuld adgang.
- Roller pr. person er Premium.
- Disponent-telefonen er stadig basic.

**Runde 4 – eksisterende partnere:**
- Ingen mister noget ved opdateringen. Et basic-firma, der allerede bruger
  Økonomi, tid eller koordinatorer, beholder det som enkelt modul
  (engangsrettelse).
- Super admin kan give og fjerne moduler ("Moduler" i partnerlisten), og data
  slettes aldrig.

**Runde 5 – onboarding:**
- Basic-menuen er Ture · Chauffører · Arkiv.
- En "Kom godt i gang"-tjekliste i Ture: invitér chauffører, se kundernes
  pladser, kør bestillingerne.

**Test:** flow_tiers 11–13d.

## 12. Vedhæftninger, skjul det man ikke har, pakkeskift og prisforklaring (2026-10-20)

### 12a. Vedhæftninger i Arkiv

**Fejlen:** Chaufførens billeder på en tur (fx varekørsel uden container) blev gemt, men vist ingen steder i Arkiv. Kun vejesedler stod der.

**Valgt løsning:** Én fælles visning, "Vedhæftninger", med en type-kolonne (Vejeseddel / Billede) og et typefilter.
- Vejesedler beholder deres egen logik: vægt, ret vægt og CO2.
- Billeder følger turens adgang.
- Endpoints: `GET /attachments-archive` og `GET /tour-photos/{id}`.

**Fravalgt:**
- To separate faner. Man skal så lede to steder efter "det chaufføren hængte på turen".
- At gemme billeder som vejesedler. Det ville blande vægt og CO2 sammen med almindelige fotos.

**Øvrige ændringer:**
- En vejeseddel uden vægt (fx på en varetur) blev smidt væk ved afslutning. Nu gemmes den altid og vises som "Uden vægt".
- Kunden ser ikke billederne herfra. De er logistikkens dokumentation.

**Fundet undervejs:** Siden login-skærpelsen 18.10 kunne vejesedlens billede og dagrapportens "Original"-PDF ikke åbnes. `<img>` og links sender ikke login med, så de fik 401. De hentes nu med login (`lib/authedFile.js`).

### 12b. Premium-funktioner vises ikke uden Premium

**Årsagen** til "Tid"-fanen med fejlbesked: siden havde hentet pakken, før firmaet blev nedgraderet.

**Rettelser:**
- Skjult uden tidsregistrering:
  - chaufførens "Stempling"-knap;
  - stempeloverblikket;
  - den manuelle stempel-dialog.
- En "Tid & ressourcer"-fane, man står på, lukkes, når modulet forsvinder.
- Chaufførens rettelser til godkendelse kræver Økonomi. Uden Økonomi er der ingen at sende dem til. Det håndhæves også af serveren.

**Notifikationer:** Push-notifikationer er ikke premium. Fejlen kom fra den forældede side.

### 12c. Pakkeskift slår igennem med det samme

**Årsager:**
- Siden hentede pakken kun én gang, ved indlæsning.
- Serveren huskede pakken i 15 sekunder pr. app-instans.
- Lige efter et skift kunne skærmen og serveren derfor være uenige, og det var forskelligt fra gang til gang.

**Nu opdaterer siden pakken:**
- hvert 30. sekund;
- når fanen/vinduet får fokus igen;
- straks, når serveren afviser noget som premium. Funktionen forsvinder så i stedet for at blive ved med at fejle.

**Serveren** husker pakken i 3 sekunder (før 15). Med flere app-instanser rydder et skift kun cachen i den instans, der modtog det.

**Fravalgt:** Ingen cache overhovedet. Det ville give et databaseopslag på hvert premium-kald, og 3 sekunder er ikke til at mærke.

**Test:**
- flow_tiers 13e: premium ↔ basic tre gange i træk hos admin og chauffør.
- flow_tiers 13f: modulet Tid til og fra.
- flow_tiers 12e: rettelser uden Økonomi.
- Browsertjek: en åben side mistede Økonomi efter ca. 17 sekunder uden genindlæsning. Ved fokus gik det på 0,1 sekund. Chaufførens IND-tryk efter nedgradering fjernede "Tid" med det samme.

### 12d. Prisberegning forklaret + fejl i tid

- `PRISBEREGNING.md` er en komplet forklaring med 151 eksempler. Eksemplerne er regnet af prismotoren og kontrolleret af `scripts/prisberegning_eksempler.py`.
- **Fejl fundet:** start og slut i samme minut blev regnet som 24 timer på timepris (over midnat-reglen). Nu giver det "Mangler tid" med beskeden "Start og slut er samme minut - ret tiden".
- **Test:** flow_pricing 21-22.

## 13. Chaufførsiden: kompakt liste, "Tag turen" og hængerkørsel (2026-10-20)

**Brugerens ønske:**
- Mindre ture (ikke store kort).
- "Tag og start" bliver "Tag turen" (læg i Mine), og man kan stadig starte med det samme.
- Hænger vs. solo besluttes, når turen startes.
- En solotur kan laves om til en hængerkørsel.
- Knapperne "Uden/Med hænger" fjernes.
- Priser kan sættes, så containeren på hængeren koster mindre.

### 13a. Liste og knapper

- **Kompakte rækker i grupperede bokse** (ikke kort):
  - linje 1: haster, tidsrum, på vej, Bil/Hænger;
  - linje 2: indhold · opgave · størrelse · container · km;
  - hent og aflever på hver sin linje med en lille "Kør".
- **Fjernet fra listen:** kundens note (gul), kunde, telefon og "Tildelt dig". Kunde og note står nu inde i turen; telefonen var der i forvejen.
- **Grupperet pr. plads** i Mine og Ledige. En hængerkørsel står som én blok, og samme hent/aflever skrives kun én gang.
- **"Tag turen"** lægger en ledig tur i Mine. En smal ▶-knap ved siden af tager og starter med det samme, med samme solo/hænger-flow.
  - Fravalgt: et toast "Start nu?" efter "Tag turen" forsvinder for hurtigt på telefonen.
  - Fravalgt: et langt tryk kan ingen finde.
  - Fravalgt: kun i turens vindue koster et ekstra tryk.
- **"Læg tilbage i Ledige"** findes inde i en tur, man selv har taget (ikke tildelt af planlæggeren).

### 13b. Hængerkørsel

- **Uden hænger** (valgt ved login) starter "Start" turen med det samme.
- **Med hænger** viser "Start" ture fra samme plads samme dag og forsinkede ture.
  - Samme materiale står først, egne før ledige, haster før andre.
  - Valget er frivilligt og begrænset af hængerens plads.
  - Er der ingen at vælge imellem, starter turen bare.
- **Serverens regel:** alle chaufførens containerture, der er på vej samtidig, er én kørsel. Den først startede er "på bilen".
  - Det samme gælder fra ældre app-versioner og ved "Tilføj tur på hængeren" fra en tur, der kører.
  - Starter man en tur, mens en anden kører, siger appen det ("Du kører allerede … Er den færdig, så afslut den først"). Ellers bliver en glemt "Afslut" til en billig hængerpris.
- **Tag af hængeren:** turen går tilbage til Mine. Er der én tur tilbage, bliver den solo.
- **Ekstra trin efter 10 gennemgange af 9A:**
  - fortryd, nulstilling, sletning og annullering;
  - afsluttede ture beholder rollen;
  - fakturerede ture røres aldrig;
  - kapaciteten tjekkes også for ture, man allerede har taget. Før blev den kun tjekket, når turen blev taget og startet i ét.
- **Data:** turen har felterne `run_id`, `run_role` (solo/truck/trailer), `run_seq` og `run_size`.
- **Fravalgt:** at udlede kørslen af tidsoverlap alene.
  - Det ville ændre prisen på gamle ture.
  - En glemt "Afslut" ville give hængerpris.
  - Planlæggeren kunne ikke se, hvilke ture der kørte sammen.
- **Varekørsel og løs afhentning** indgår ikke. Deres hængere hører til selve turen og oplyses ved afslutning som før. Det giver ikke mening at koble to varejobs på én hænger; flere afleveringer er stop på én tur.
- **Planlæggeren** lægger ikke hængerkørsler på forhånd. Chaufføren afgør det ud fra forholdene på pladsen. Planlæggeren ser kørslen på turen ("Hængerkørsel · på hængeren") og i Rapport.

### 13c. Hænger og pris

**"Med hænger" på en containertur = del af en hængerkørsel.** Det var ikke klart for brugeren, hvad der var mest logisk. Valget er dette:
- En solotur med en tom hænger koster det samme som uden hænger. Kunden har ikke fået noget ekstra, og ellers ville prisen afhænge af, hvad chaufføren tilfældigvis valgte ved login.
- Før blev en solotur automatisk "med hænger" (og fik hængertillæg) bare fordi der var valgt hænger ved login.
- Ældre ture og varekørsel prissættes uændret.

**Prisforbedringer:**
1. Ny betingelse "Kørsel" (solo / på bilen / på hængeren, 2 point) i motoren.
2. Prisaftalen har afsnittet "Hængerkørsel": container på hængeren og på bilen, som grundprisen, fast beløb eller % af grundprisen. Gemmes som regler som forgæves-prisen. Fravalgt: et negativt "rabat"-tillæg (motoren og fakturaen skal ikke have minusbeløb) og en procent-faktor i motoren (for meget ny logik).
3. "Med hænger" udledes af kørslen, så falske hængertillæg ikke opstår.
4. Bekræftelsen "Hænger: automatisk, ikke bekræftet" og spørgsmålet ved afslutning er væk for containerture.
5. Admin kan rette kørslen pr. tur i Økonomi (med begrundelse og historik).
6. "Prøv prisen" kan vælge kørsel.
7. Rapport og CSV viser kørsel og hvilke ture der kørte sammen.
8. Advarsel på turen, når to grundpriser passer lige godt ("den senest rettede bruges").
9. Kr/t-tillæg viser "45 min" (ikke "45.0 min").
10. Chaufførens rettelse kan ikke længere sætte hænger på en containertur (kørslen afgør, admin retter). Varekørsel er uændret.
11. Hjælpetekster og PRISBEREGNING.md er opdateret: 163 kontrollerede eksempler, med nye faldgruber (mere specifik aftale uden hængerpris; timepris + hængerpris).

**Fravalgt:** flere "Andet"-gebyrer pr. tur. Det ville ændre prisen på eksisterende ture uden versionering.

**Test:**
- flow_run 1-33 (nyt);
- flow_b2b 5-13 (gammel automatisk hænger erstattet);
- alle andre grupper uændrede.

### 13d. Runde 2 (samme dag): mere kompakt, Start i Mine ture, "Giv turen tilbage"

**Kompakt og tydelige skel:**
- Hver tur er sin egen lille boks med luft imellem. Før var det linjer i én fælles boks, så man ikke kunne se, hvor en tur sluttede.
- Turen viser:
  - linje 1: Bil/Hænger, haster og indhold;
  - linje 2: tidsrum, på vej, container og km (grå);
  - kun de adresser, der ikke allerede står ovenover, på én linje med en lille "Kør".
- Pladsens adresse står én gang i gruppens overskrift med "Kør" (når alle turene kører fra/til pladsen). Hver tur viser så kun afleveringen.
- Hængerkørsel er en lilla ramme med hvide bokse. Kører containerne samme vej, står hent og aflever én gang øverst i rammen.
- Ture med flere end 2 stop viser kun næste stop på listen. Hele listen står inde i turen. Ved 2 adresser (almindelig containertur) står begge med "Kør".
- **Fravalgt:**
  - Adressen som link uden knap: for lille trykflade, og man kommer til at navigere ved et uheld.
  - Kun ikoner: et kort-ikon uden tekst var netop det, der forvirrede før.
  - Begge "Kør" på samme linje: det er ikke tydeligt, hvilken knap der hører til hvilken adresse.

**Start i Mine ture åbnede ikke listen:**
- Dine data viser, at en tur startede som solo kl. 19:14, mens to ledige ture fandtes på samme plads.
- Sandsynligvis kørte fanen stadig den gamle version (siden opdaterer først ved genindlæsning).
- Der var også en reel fejl: en forsinket tur (dato i går) fandt kun ture med samme dato, så dagens ture kom ikke med. Nu tæller alle ture til og med i dag.
- **Ny regel:** med hænger åbner "Start" altid listen på en containertur, også når der ikke er andre ture. Så ser chaufføren, at muligheden findes, og at en tur kan lægges på hængeren senere.

**"Giv turen tilbage"** (dansk for "unassign myself"):
- Står som tydelig knap inde i en tur, man selv har taget og ikke har startet. Turen kommer tilbage under Ledige.
- Ledige ture har også "Tag turen" inde i turen.
- Ture, planlæggeren har tildelt, kan ikke gives tilbage af chaufføren; det er som før.

### 13e. Hængerlisten: materiale først, også for forsinkede ture (2026-10-22)
Listen "Kører du flere containere?" havde en egen gruppe "Fra tidligere dage". Den samme container kunne derfor stå to steder, fx Papir #Container 2 fra i dag under "Samme materiale" og fra 20.10 under "Fra tidligere dage". Nu sorteres der først på materiale, som ønsket:
- Der er to grupper: "Samme materiale" og "Andre materialer".
- En forsinket tur står under sit materiale med et gult mærke ("20.10 · 2 dage for sent").
- I hver gruppe kommer egne ture først, så haster, så forsinkede (ældste først), og til sidst efter tidsrum.
- Fravalgt: forsinkede i en egen gruppe. Materialet er det, chaufføren vælger efter (samme fraktion til samme modtager).

### 13f. Login når serveren ikke svarer (2026-10-22)
**Fejlen:** login gav "Cannot read properties of undefined (reading 'name')" og hang på "Indlæser...".
- Serveren kørte ikke (Docker var stoppet).
- Appens offline-hjælper (service worker) svarede "OK" på login uden en bruger.

**Rettet:**
- Offline-hjælperen (v4) svarer med en rigtig fejl (503) i stedet for falske "OK"-svar. Det gælder også for start, afslutning osv., så appens egen kø gemmer chaufførens handlinger rigtigt.
- Login og bruger-svar caches aldrig.
- Login siger "Ingen forbindelse til serveren. Prøv igen om lidt."
- Åbnes appen igen uden net, bruges den sidst kendte bruger for samme login, så en chauffør ikke bliver logget ud. Kun en rigtig afvisning logger ud.
