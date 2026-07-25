# ContainerFlow → Scaleway — Komplet Deployment-Guide

**Mål:** containerflow.dk kører på 100% EU-ejet infrastruktur (Scaleway, Frankrig), GDPR-klar, uden Emergent-afhængigheder.

**Hvad der allerede er gjort i denne kodebase (af Claude):**
- ✅ `emergentintegrations` fjernet fra requirements.txt (blev aldrig importeret i koden)
- ✅ Auth tilføjet på `/receipts/ocr-scan` og `/receipts/save-for-tour`
- ✅ SPA-serving tilføjet i server.py (React + API fra samme container)
- ✅ Produktions-Dockerfile oprettet (multi-stage: Node build → Python runtime)

---

## FASE A — Forberedelse (30 min, gøres lokalt på din maskine)

### A1. Test Docker-buildet lokalt FØRST
Du SKAL se containeren virke lokalt inden Scaleway. Ellers fejlfinder du i blinde.

```bash
cd <projektmappe>
docker build -t containerflow:test .
```

**Forventet:** Build gennemføres på 5-10 min. Fejler den i frontend-stadiet → send mig fejlen.

```bash
docker run -p 8080:8080 \
  -e MONGO_URL="mongodb://host.docker.internal:27017" \
  -e DB_NAME="containerflow" \
  -e JWT_SECRET="test-secret-min-32-tegn-langt-abcdef" \
  -e CORS_ORIGINS="http://localhost:8080" \
  containerflow:test
```

Åbn `http://localhost:8080` → du skal se login-siden. Test login virker (kræver lokal MongoDB med data, ellers bare at siden loader).

**⚠️ STOP hvis dette ikke virker.** Alt efterfølgende afhænger af det.

---

## FASE B — Scaleway-konto og database (45 min)

### B1. Opret konto
1. Gå til **console.scaleway.com** → Sign up
2. Verificér med betalingskort (intet trækkes før forbrug)
3. Vælg **Organization region: fr-par (Paris)** — dét er jeres EU-datacenter

### B2. Opret Managed MongoDB
1. Console → **Managed Databases** → **MongoDB®** → Create
2. Vælg:
   - Region: **fr-par (Paris)**
   - Node type: **MGDB-PLAY2-NANO** (mindste — rigeligt til jer, kan opgraderes med ét klik)
   - Storage: 10 GB (default)
   - High availability: **NEJ** for nu (fordobler prisen; tilvælg når I har 3+ kunder)
3. Notér: **connection string**, brugernavn, password (vises kun én gang — gem i password manager)
4. Under **Backups**: verificér at automatiske daglige snapshots er aktiveret (default: ja, 7 dages retention)

**Pris: ~€16-20/md**

### B3. TEST backup-restore med det samme (VIGTIGT — I bad om påpasselighed her)
1. Opret en test-collection via MongoDB Compass (forbind med connection string)
2. Console → din database → Backups → tag manuel snapshot
3. Restore snapshot til NY instans → verificér test-data findes → slet test-instansen
4. **Nu VED I at restore virker** — de fleste opdager det modsatte først når katastrofen er sket

---

## FASE C — Deploy containeren (45 min)

### C1. Opret Container Registry
1. Console → **Container Registry** → Create namespace
   - Name: `containerflow`
   - Region: **fr-par**
   - Privacy: **Private**

### C2. Push jeres image
```bash
# Login (token genereres i Console → IAM → API Keys → Generate)
docker login rg.fr-par.scw.cloud/containerflow -u nologin --password-stdin <<< "DIN_SECRET_KEY"

# Byg til amd64 (Scaleway kører amd64; vigtigt hvis du er på Mac M1/M2)
docker build --platform linux/amd64 -t rg.fr-par.scw.cloud/containerflow/app:v1 .
docker push rg.fr-par.scw.cloud/containerflow/app:v1
```

### C3. Opret Serverless Container
1. Console → **Serverless Containers** → Create namespace → `containerflow-prod`, region **fr-par**
2. Create container:
   - Image: `rg.fr-par.scw.cloud/containerflow/app:v1`
   - Port: **8080**
   - CPU: 1000 mCPU / RAM: 2048 MB (start her; kan justeres live)
   - Min scale: **1** (VIGTIGT: 0 giver cold starts på 10-30 sek — dårligt for chauffører)
   - Max scale: 3
3. **Miljøvariabler** (Environment variables — almindelige) — sæt disse:

| Variabel | Værdi |
|---|---|
| `DB_NAME` | `containerflow` |
| `CORS_ORIGINS` | `https://containerflow.dk,https://www.containerflow.dk` |
| `JWT_EXPIRY_HOURS` | `24` |
| `APP_PUBLIC_URL` | `https://containerflow.dk` |
| `SENDER_EMAIL` | jeres afsender-mail |
| `SENDER_NAME` | `ContainerFlow` |

4. **Secrets** (krypterede env vars — brug Secrets-fanen, IKKE almindelige env):

| Secret | Værdi |
|---|---|
| `MONGO_URL` | connection string fra B2 |
| `JWT_SECRET` | generér ny: `openssl rand -hex 32` — **ALDRIG genbrugt fra Emergent** |
| `SUPER_ADMIN_EMAIL` | jeres admin-email |
| `SUPER_ADMIN_PASSWORD` | nyt stærkt password |
| `RESEND_API_KEY` | fra jeres Resend-konto (mail-udsendelse) |
| `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY` / `VAPID_CLAIMS_EMAIL` | kopiér fra Emergent-miljøet (push-notifikationer) — eller generér nye: `npx web-push generate-vapid-keys` (bemærk: nye nøgler = brugere skal re-subscribe til push) |
| `GOOGLE_APPLICATION_CREDENTIALS` | se C4 hvis OCR/Vision bruges — ellers udelad (koden falder tilbage til manuel vægt) |

5. Deploy → vent på grøn status → test den auto-genererede URL (`https://xxx.functions.fnc.fr-par.scw.cloud`)

**⚠️ Kendt fælde:** Hvis containeren crasher ved start, tjek Logs-fanen. Hyppigste årsag: MONGO_URL forkert format (skal inkludere `?tls=true` for Scaleway managed MongoDB — står i deres connection string).

### C4. (Kun hvis OCR bruges) Google Vision credentials
Koden er bygget så OCR er valgfri — uden credentials fungerer manuel vægtindtastning fint. Hvis I VIL have OCR: upload service-account JSON som secret file (Scaleway understøtter secret files) og sæt `GOOGLE_APPLICATION_CREDENTIALS=/path/til/fil`. **Anbefaling: spring over nu, tilføj senere hvis behov.**

---

## FASE D — Domæne (30 min + DNS-ventetid)

### D1. Flyt DNS til Scaleway (one.com's DNS-editor er beviseligt ustabil for jer)
1. Console → **Domains and DNS** → Add external domain → `containerflow.dk`
2. Scaleway viser 2 nameservere (fx `ns0.dom.scw.cloud`, `ns1.dom.scw.cloud`)
3. Log ind på one.com → dit domæne → **Nameservers** (IKKE DNS records — selve nameserver-sektionen) → erstat med Scaleways to
4. Vent 1-4 timer (op til 24t worst case)

### D2. Koble domænet til containeren
1. Serverless Containers → jeres container → **Endpoints** → Add custom domain → `containerflow.dk`
2. Scaleway opretter automatisk DNS-record + **gratis SSL-certifikat** (Let's Encrypt, auto-fornyet)
3. Tilføj også `www.containerflow.dk` som endpoint nr. 2
4. Test: `https://containerflow.dk` → login-side med hængelås

---

## FASE E — Datamigration fra Emergent (1-2 timer, planlæg til aften)

### E1. Eksportér fra Emergent
I `data-migration/`-mappen ligger allerede dump-værktøjer. Fra Emergents miljø:
```bash
mongodump --uri="<EMERGENT_MONGO_URL>" --out=./dump
```
(Hvis Emergent ikke giver direkte mongo-adgang: brug deres eksport-funktion eller bed deres support om dump)

### E2. Importér til Scaleway
```bash
mongorestore --uri="<SCALEWAY_MONGO_URL>" ./dump
```

### E3. Verificér KRITISK data før cutover
- [ ] Antal users matcher (login-konti)
- [ ] Antal tours matcher
- [ ] Antal receipts matcher (inkl. billeder — de ligger som base64 i samme collection)
- [ ] Log ind som superadmin på Scaleway-versionen → klik gennem: bestillinger, rapporter, ét kvitteringsfoto åbnes korrekt

### E4. Cutover (det øjeblik containerflow.dk skifter fra Emergent til Scaleway)
Da domænet formentlig aldrig kom til at virke på Emergent (jeres DNS-problemer), er dette enkelt: D2 ovenfor ER cutover. Brugerne på `role-analysis-flow.emergent.host` informeres om ny URL.

**Kør Emergent parallelt i 14 dage** som fallback, derefter opsig.

---

## FASE F — Efter go-live (samme uge)

- [ ] Sæt **budget-alarm**: Console → Billing → Budget alerts → advarsel ved €50/md
- [ ] Verificér daglig backup kører (Console → Database → Backups → se dagens snapshot)
- [ ] Opdatér jeres DPA-udkast: databehandler = Scaleway SAS (Frankrig), datalokation = Paris — **dette er nu 100% sandt og CLOUD Act-frit** ✅
- [ ] Notér deploy-proceduren for fremtidige releases:
```bash
docker build --platform linux/amd64 -t rg.fr-par.scw.cloud/containerflow/app:v2 .
docker push rg.fr-par.scw.cloud/containerflow/app:v2
# Console → container → Edit → skift image-tag til v2 → Deploy
# (Zero-downtime: Scaleway ruller nye instanser op før gamle lukkes)
```

---

## Samlet månedlig pris (estimat)

| Komponent | Pris |
|---|---|
| Managed MongoDB (NANO) | ~€17/md |
| Serverless Container (1 vCPU/2GB, min-scale 1) | ~€12-18/md |
| Container Registry | ~€0-1/md |
| DNS | gratis |
| SSL | gratis |
| **Total** | **~€30-36/md ≈ 2.700-3.200 kr/år** ✅ inden for budget |

---

## Senere (IKKE nu — bevidst udskudt)

1. **Object Storage til fotos** — flyt base64-billeder ud af MongoDB når datamængden vokser (~6-12 md ude). Kræver lille koderefaktorering; jeg hjælper når tiden kommer.
2. **Staging-miljø** — kopiér containeren med suffix `-staging` + separat lille DB. 30 minutters arbejde når I vil have det.
3. **CI/CD** — GitHub Actions der bygger+pusher ved git push. Nice-to-have; manuel deploy er 3 kommandoer.
