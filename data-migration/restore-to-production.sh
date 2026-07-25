#!/bin/bash
# ============================================================================
# ContainerFlow — Migrér preview-data til produktion
# ============================================================================
# Denne script sletter ALT data i produktions-MongoDB og importerer preview-dump.
#
# Krav:
#   • MongoDB Tools installeret (`mongodump` / `mongorestore`)
#     → macOS: brew install mongodb-database-tools
#     → Linux: apt-get install mongodb-database-tools
#   • preview-dump-YYYYMMDD.tar.gz filen i samme mappe
#
# Brug:
#   1. Læg denne .sh og tar.gz-filen i samme mappe
#   2. Åbn terminal, cd til mappen
#   3. Kør:   bash restore-to-production.sh "<PRODUKTIONS_MONGO_URL>"
#
#   Eksempel:
#   bash restore-to-production.sh "mongodb+srv://user:pass@cluster.mongodb.net/containerflow"
# ============================================================================

set -e

if [ -z "$1" ]; then
  echo "❌ Fejl: Angiv produktions MongoDB URL som første argument."
  echo ""
  echo "   Brug:  bash restore-to-production.sh \"mongodb+srv://user:pass@cluster.mongodb.net/DBNAME\""
  echo ""
  exit 1
fi

PROD_URL="$1"
DUMP_TARBALL="$(ls preview-dump-*.tar.gz 2>/dev/null | head -1)"

if [ -z "$DUMP_TARBALL" ]; then
  echo "❌ Fejl: preview-dump-*.tar.gz ikke fundet i den nuværende mappe."
  exit 1
fi

echo "📦 Bruger dump-fil: $DUMP_TARBALL"

# Udpak
echo "📂 Udpakker dump..."
rm -rf ./dump
tar -xzf "$DUMP_TARBALL"

if [ ! -d "./dump/test_database" ]; then
  echo "❌ Fejl: forventet ./dump/test_database/ mappe blev ikke fundet efter udpakning."
  exit 1
fi

# Tag database-navn fra produktions-URL (den del efter sidste '/' og før '?')
PROD_DB=$(echo "$PROD_URL" | sed -E 's|^.*/([^/?]+)(\?.*)?$|\1|')
echo "🎯 Produktion database-navn: $PROD_DB"

# Bekræft
echo ""
echo "⚠️  ADVARSEL: Alt data i produktion-databasen '$PROD_DB' bliver SLETTET"
echo "   og erstattet med preview-dumpet ($(du -sh ./dump/test_database | cut -f1))."
echo ""
read -p "   Skriv 'JA SLET' for at fortsætte: " confirm
if [ "$confirm" != "JA SLET" ]; then
  echo "❌ Afbrudt af bruger."
  exit 1
fi

# Restore med --drop (sletter eksisterende collections først)
echo ""
echo "🚀 Kører mongorestore (drop + restore)..."
mongorestore \
  --uri="$PROD_URL" \
  --db="$PROD_DB" \
  --drop \
  --numParallelCollections=4 \
  --gzip=false \
  ./dump/test_database/

echo ""
echo "✅ Migrering færdig!"
echo ""
echo "   Preview-data er nu i produktion. Test din app på https://containerflow.dk"
echo ""
echo "   Tip: Ryd op i dump/ efter test: rm -rf ./dump"
