# Logistik: næste forbedringer (research 2026-10-16)

Værdi og indsats er på en skala 1–5. **?** betyder, at jeg har brug for dit svar,
før den kan bygges rigtigt.

## Forslag

| # | Område | Forslag | Værdi | Indsats | Hvorfor |
|---|---|---|---|---|---|
| 1 | Chauffør | **Foto ved afslutning** (container før/efter, fyldningsgrad). Vises i tur-panelet hos planlæggeren | 5 | 2 | Dokumentation ved klager om overfyldt/forkert sorteret container. Kvitterings-scanneren findes allerede og kan genbruges |
| 2 | Chauffør | **Offline-kø**: "Start/Afslut" gemmes lokalt uden dækning og sendes, når der er net | 5 | 3 | Containerpladser og industriområder har ofte dårlig dækning. I dag fejler handlingen |
| 3 | Planlægning | **Kort-visning af dagen** (alle ture + chaufførernes sidste position) | 4 | 3 | Hurtigere at give en haster til den nærmeste chauffør. Lat/lng findes på mange pladser |
| 4 | Planlægning | **ETA til kunden** ("chaufføren er på vej, ca. 25 min") via sms/mail, når turen sættes på vej | 4 | 3 | Færre opkald fra kunder. Resend er sat op |
| 6 | Ture | **Skabeloner for faste kunder** ("Carlsberg mandag: 3 × Træ, 2 × Rest"), oprettet med ét klik | 4 | 2 | Gentagelse findes nu. Skabeloner dækker variationer uden at vedligeholde serier |
| 7 | Chauffør | **Vejesedel-OCR → vægt udfyldes automatisk** | 4 | 3 | OCR-tjenesten findes allerede (receipts). Sparer indtastning og fejl |
| 8 | Kvalitet | **Afvigelseskoder** i stedet for fritekst ved "Kan ikke gennemføres" (Lukket, Blokeret, Forkert affald, Ingen container) | 4 | 1 | Gør det muligt at måle årsager i Rapportering og fakturere forgæves kørsel |
| 9 | Økonomi | **Forgæves kørsel** som automatisk tillæg, når en tur markeres "kan ikke gennemføres" med en bestemt kode | 4 | 2 | Bygger på #8 og prisreglerne ("surcharge") |
| 10 | Drift | **Køretøjstjek** (dagligt eftersyn i appen før første tur: lys, dæk, kran) | 3 | 2 | Lovkrav/forsikring hos nogle firmaer. Kan knyttes til vogn-valget der findes |
| 11 | Rapportering | **Ugerapport på mail** til logistik admin (ture, kg, forsinkelser, top-afvigelser) | 3 | 2 | Overblik uden at logge ind |
| 12 | Sikkerhed | ~~Roller i firmaet~~ **Bygget 2026-10-17**: koordinatorer + Team & rettigheder (se `TEAM_RETTIGHEDER.md`) | – | – | – |
| 13 | Chauffør | **Navigation til næste tur** i ét tryk efter afslutning (åbner Google/Apple Maps med næste adresse) | 4 | 1 | Færre tryk mellem ture |
| 14 | Integration | **ARGO/Vestforbrænding-import via mail-indbakke** (videresend mail → ture oprettes) | 4 | 4 | Parse-mail-logikken findes. Mangler en indbakke |
| 15 | Opfølgning | **Kunde-kvittering**: kunden får en mail med vægt og tidspunkt, når turen er færdig | 3 | 2 | Bruges ofte som dokumentation hos boligforeninger |

## Dine svar (2026-10-17) og hvad der er gjort

| # | Svar | Gjort |
|---|---|---|
| A | Flere kan planlægge. De skal kunne tilføjes som koordinator med styrbare rettigheder | Bygget: Mere › Team & rettigheder, 13 rettigheder, skabeloner, invitation pr. mail |
| B | Undersøg hvad chaufførerne vil være gladest for | Research: chauffører ringer stadig oftest til disponenten. De vil have få tryk, hurtigsvar og vide at beskeden er set. Bygget: "Ring til planlæggeren" ved hver tur, hurtigsvar og "Læst". Næste: offline-kø (#2) |
| C | Kundesiden er fin nu | Ingen ændring. Jeg ser heller ikke et behov lige nu |
| D | Manuelle priser smart, og prisændringer må ikke ændre eksisterende ture | Bygget: versionerede prisregler ("Nye ture fra nu" / "Fra dato" / "Også eksisterende") og "Aftalt pris" i Ny tur. Afvigelseskoder og forgæves kørsel (#8, #9) er stadig forslag |
| E | Ikke relevant | Fakturaeksport fjernet fra listen |
| F | iPhone, Android og iPad | Chauffør- og admin-siderne testet på telefon- og iPad-bredde |

## Besvaret 2026-10-17
- **Push til chauffører:** slået til som standard; chaufføren kan slå det fra under Profil. Det kræver VAPID-nøgler i Scaleway (se `WORKFLOW.md` 4b).
- **Gods og andet:** premium-firmaer kan nu køre ture der ikke handler om containere (se `TURE_REDESIGN.md`).
