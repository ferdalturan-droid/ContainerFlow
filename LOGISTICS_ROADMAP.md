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
| 5 | Økonomi | **Fakturaeksport** (CSV/e-conomic/Dinero) direkte fra Økonomi › Rapport | 5 | 3 | Fakturagrundlaget findes. Næste skridt er at få det ud uden copy-paste |
| 6 | Ture | **Skabeloner for faste kunder** ("Carlsberg mandag: 3 × Træ, 2 × Rest"), oprettet med ét klik | 4 | 2 | Gentagelse findes nu. Skabeloner dækker variationer uden at vedligeholde serier |
| 7 | Chauffør | **Vejesedel-OCR → vægt udfyldes automatisk** | 4 | 3 | OCR-tjenesten findes allerede (receipts). Sparer indtastning og fejl |
| 8 | Kvalitet | **Afvigelseskoder** i stedet for fritekst ved "Kan ikke gennemføres" (Lukket, Blokeret, Forkert affald, Ingen container) | 4 | 1 | Gør det muligt at måle årsager i Rapportering og fakturere forgæves kørsel |
| 9 | Økonomi | **Forgæves kørsel** som automatisk tillæg, når en tur markeres "kan ikke gennemføres" med en bestemt kode | 4 | 2 | Bygger på #8 og prisreglerne ("surcharge") |
| 10 | Drift | **Køretøjstjek** (dagligt eftersyn i appen før første tur: lys, dæk, kran) | 3 | 2 | Lovkrav/forsikring hos nogle firmaer. Kan knyttes til vogn-valget der findes |
| 11 | Rapportering | **Ugerapport på mail** til logistik admin (ture, kg, forsinkelser, top-afvigelser) | 3 | 2 | Overblik uden at logge ind |
| 12 | Sikkerhed | **Roller i firmaet**: "Planlægger" (ingen Økonomi) vs. "Admin" | 3 | 2 | Ikke alle der planlægger skal se priser |
| 13 | Chauffør | **Navigation til næste tur** i ét tryk efter afslutning (åbner Google/Apple Maps med næste adresse) | 4 | 1 | Færre tryk mellem ture |
| 14 | Integration | **ARGO/Vestforbrænding-import via mail-indbakke** (videresend mail → ture oprettes) | 4 | 4 | Parse-mail-logikken findes. Mangler en indbakke |
| 15 | Opfølgning | **Kunde-kvittering**: kunden får en mail med vægt og tidspunkt, når turen er færdig | 3 | 2 | Bruges ofte som dokumentation hos boligforeninger |

## Spørgsmål til dig

| # | Spørgsmål | Hvorfor jeg spørger |
|---|---|---|
| A | Hvem planlægger i praksis: én disponent, eller flere der deler dagen? | Afgør om vi skal have "lås"/"hvem arbejder på hvad" i Ture, og rolle-forslaget (#12) |
| B | Ringer chaufførerne i dag til disponenten, eller skriver de (sms/WhatsApp)? | Hvis det meste går via telefon, bør "Ring planlægger" være en knap på kortet ved siden af Besked |
| C | Skal kunden (fx boligforeningen eller slutkunden på en firma-tur) kunne se tur-status og beskeder? | Afgør om beskedtråden skal deles med kunden eller forblive intern |
| D | Hvad sker der i dag, når en tur ikke kan gennemføres – betaler kunden for forgæves kørsel? | Afgør #8 og #9 og hvilke koder der skal være |
| E | Hvilket regnskabssystem bruger logistikfirmaerne (e-conomic, Dinero, Uniconta, andet)? | Afgør formatet i #5 |
| F | Kører chaufførerne på Android, iPhone eller begge? Bruges appen fra hjemmeskærmen (PWA)? | iPhone kræver hjemmeskærm-installation for web push. Afgør om vi skal vise en installationsguide |
| G | Skal "Gentag" kunne køre uden slutdato (fx "hver mandag indtil videre")? | I dag laves ture op til 120 dage frem. Uden slutdato kræver det et natligt job |
| H | Har firmaerne faste ruter/zoner (nord/syd), som chauffører normalt kører? | Kan bruges til automatisk forslag om chauffør ved nye ture |
