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

## 4. Sider (logistik admin → "Økonomi")

Rapport · Prisregler · Godkendelser · Helligdage · Indstillinger

## 5. Bevidst udeladt (for nu)
* Pris pr. ton (deponi-/modtagegebyrer er modtagerens, ikke transportørens).
* Kunden ser ikke priser.
* Kilometerpris (kræver kørselsdata vi ikke har pålideligt).
