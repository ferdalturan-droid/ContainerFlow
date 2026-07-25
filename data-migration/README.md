# ContainerFlow — Data-migrering til produktion

## Hvad ligger her?
- **`preview-dump-YYYYMMDD.tar.gz`** — komplet backup af hele preview-databasen (`test_database`), inklusive **alle** collections: brugere, pladser, containere, materialer, CO2-typer, leveringsadresser, bestillinger (inkl. 88 nyoprettede demo-trends for Blishøj 1/49, SAC og Cirklen), tours, aktivitets-log osv.
- **`restore-to-production.sh`** — automatisk migreringsscript. Sletter produktions-data først, importerer preview-dumpet.
- **`dump/test_database/`** — udpakket rå-form af dumpet (kan slettes efter tarball er lavet).

## Hvad du skal gøre for at migrere til produktion

### 1. Find produktions MongoDB URL
- Log ind på [emergent.com](https://emergent.com) → dit projekt → Deploy settings
- Kopier **produktions MONGO_URL** (starter typisk med `mongodb+srv://...`)

### 2. Download filerne til din computer
- Fra Emergent's "Save to Github" eller download disse to filer:
  - `preview-dump-YYYYMMDD.tar.gz`
  - `restore-to-production.sh`

### 3. Installér MongoDB Tools (hvis ikke allerede)
```bash
# macOS
brew tap mongodb/brew
brew install mongodb-database-tools

# Linux (Debian/Ubuntu)
apt-get install mongodb-database-tools
```

### 4. Kør migreringen
```bash
cd ~/Downloads   # eller hvor du har lagt filerne
bash restore-to-production.sh "mongodb+srv://USER:PASS@cluster.mongodb.net/DBNAME"
```

Scriptet:
1. Udpakker dumpet
2. Beder om bekræftelse (`JA SLET`) — sikkerhedsforanstaltning
3. Sletter alle collections i produktion (`--drop`)
4. Importerer preview-data
5. Rapporterer succes

### 5. Verificér i produktion
Åbn `https://containerflow.dk` og bekræft at:
- Login virker med samme brugere som preview
- Bestillingssiden viser dine 4 lokationer (Blishøj 1/49, SAC, Cirklen)
- **Rapporter viser trends** — bestillinger spredt over de sidste 60 dage med mix af `completed`/`pending`/`cancelled`

## Genererede demo-bestillinger
88 bestillinger blev tilføjet på tværs af de 4 lokationer:
- **Boliggården - Blishøj 1**: 20 bestillinger (16 fuldført)
- **Boliggården - Blishøj 49**: 21 bestillinger (15 fuldført)
- **SAC (Skibstrup)**: 22 bestillinger (20 fuldført)
- **Cirklen**: 25 bestillinger (20 fuldført)

Fordelt over de sidste 60 dage med:
- Varierede materialer (Pap, Papir, Træ, Metal, Glas, Plast, Beton osv.)
- Varierede priorities (haster 10%, normal 70%, senere 20%)
- Realistiske vægte (200-2500 kg) og CO2-beregninger
- Blandet status (completed/pending/on_way/cancelled)
- Brugere fra samme firma som "created_by"

Demo-bestillinger er markeret med `demo_data: true` i databasen, så de kan slettes samlet senere hvis nødvendigt:
```javascript
db.container_orders.deleteMany({ demo_data: true })
db.tours.deleteMany({ source: "demo_data" })
```

## Kør igen (regenerér demo-data)
Hvis du vil ha' MERE eller FRISKE demo-bestillinger senere:
```bash
python3 /app/scripts/generate_demo_orders.py
```
Det sletter først eksisterende demo-orders og genererer nye.
