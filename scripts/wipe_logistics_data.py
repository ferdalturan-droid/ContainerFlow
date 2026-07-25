"""
Logistik-data nulstilling — Fase 1 i logistik-modernisering.

KRAV:
- Sletter KUN logistik-data: drivers, tours, reports, receipts, pdf_archives,
  driver_sessions, push_subscriptions, messages, tour_prices, genbrug_orders,
  container_counts, users.role="driver", invitation_tokens for drivers.
- BEVARER ALT container-data: companies, locations, holiday_*, material_*,
  hours_*, delivery_addresses, workshops, capacity_measures, container_orders
  (selve ordrerne — kun tour_id ryddes), location_groups, holiday_groups,
  alle non-driver users, container_overrides, plads (legacy — bevares til
  Fase 3 unification).

BRUG:
  # 1) Dry-run (default — viser hvad der ville blive slettet)
  python /app/scripts/wipe_logistics_data.py --dry-run

  # 2) Faktisk wipe (kræver bekræftelse: skriv "WIPE LOGISTICS")
  python /app/scripts/wipe_logistics_data.py --confirm

  # 3) Snapshot only (gem JSON-dump uden at slette)
  python /app/scripts/wipe_logistics_data.py --snapshot-only

Snapshot gemmes ALTID til /app/backups/pre-wipe-{timestamp}.json før wipe
køres, så data kan inspiceres eller restoreres manuelt.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

# ─── Configuration ────────────────────────────────────────────────────────────
LOGISTICS_COLLECTIONS = [
    "drivers",
    "tours",
    "reports",
    "receipts",
    "pdf_archives",
    "driver_sessions",
    "push_subscriptions",
    "messages",
    "tour_prices",
    "genbrug_orders",
    "container_counts",
]

# Collections explicitly preserved (just for documentation in output)
PRESERVED_COLLECTIONS = [
    "companies",
    "locations",
    "users (non-driver)",
    "holiday_calendars",
    "holiday_deltas",
    "holiday_groups",
    "delta_notifications",
    "material_calendars",
    "hours_calendars",
    "delivery_addresses",
    "workshops",
    "capacity_measures",
    "container_orders (data preserved, tour_id field cleared)",
    "container_overrides",
    "location_groups",
    "plads (legacy — handled in Phase 3)",
    "activity_log",
]

BACKUPS_DIR = Path("/app/backups")
SNAPSHOT_PATH_TEMPLATE = "pre-wipe-{ts}.json"


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _serialize(obj):
    """JSON-safe serialization (handles ObjectId, datetime, bytes)."""
    from bson import ObjectId
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return f"<bytes:{len(obj)}>"
    raise TypeError(f"Type {type(obj)} not serializable")


def build_snapshot(db):
    """Capture full current state of all logistics-related data + driver users."""
    snap = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "db_name": os.environ.get("DB_NAME", "test_database"),
        "counts": {},
        "collections": {},
    }
    for coll in LOGISTICS_COLLECTIONS:
        docs = list(db[coll].find({}))
        snap["counts"][coll] = len(docs)
        snap["collections"][coll] = docs

    # Driver users (role='driver') — copied into the snapshot so they can be
    # restored if needed.
    driver_users = list(db.users.find({"role": "driver"}))
    snap["counts"]["users (role=driver)"] = len(driver_users)
    snap["collections"]["users_drivers"] = driver_users

    # Invitation tokens whose user_id matches a driver user — captured for
    # restore-completeness.
    driver_user_ids = [u.get("id") for u in driver_users if u.get("id")]
    inv_tokens = list(db.invitation_tokens.find({"user_id": {"$in": driver_user_ids}})) if driver_user_ids else []
    snap["counts"]["invitation_tokens (driver-related)"] = len(inv_tokens)
    snap["collections"]["invitation_tokens_driver"] = inv_tokens

    # Container orders that have a tour_id linkage — captured before we clear them
    orders_with_tour = list(db.container_orders.find(
        {"$or": [{"tour_id": {"$exists": True, "$ne": ""}}, {"order_id": {"$exists": True, "$ne": ""}}]}
    ))
    snap["counts"]["container_orders (with tour_id linkage)"] = len(orders_with_tour)
    snap["collections"]["container_orders_with_tour_linkage"] = orders_with_tour

    return snap


def write_snapshot(snap):
    """Persist snapshot to /app/backups/pre-wipe-{ts}.json. Verify it opens."""
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = BACKUPS_DIR / SNAPSHOT_PATH_TEMPLATE.format(ts=ts)
    with path.open("w", encoding="utf-8") as f:
        json.dump(snap, f, default=_serialize, ensure_ascii=False, indent=2)

    # Verify the file opens and parses cleanly
    with path.open("r", encoding="utf-8") as f:
        reload = json.load(f)
    assert reload["created_at"] == snap["created_at"], "Snapshot verification failed"

    return path


def print_dry_run(db, snap):
    """Show exactly what would be deleted."""
    print()
    print("═" * 78)
    print(" DRY-RUN — INGEN DATA SLETTES — kun rapport over hvad wipe ville røre ")
    print("═" * 78)
    print()

    print("📦 KOLLEKTIONER DER SLETTES HELT:")
    for coll in LOGISTICS_COLLECTIONS:
        count = snap["counts"][coll]
        print(f"  ✗ {coll:<35} → {count} dokumenter")

    print()
    print("👤 USERS DER SLETTES (role='driver'):")
    drv_users = snap["collections"]["users_drivers"]
    print(f"  ✗ {len(drv_users)} chauffør-brugere")
    for u in drv_users[:10]:
        print(f"      - {u.get('email', '<no-email>')} | name='{u.get('name', '')}'")
    if len(drv_users) > 10:
        print(f"      ... og {len(drv_users) - 10} flere")

    print()
    print("🎟  INVITATION TOKENS DER SLETTES (driver-related):")
    print(f"  ✗ {snap['counts']['invitation_tokens (driver-related)']} tokens")

    print()
    print("🔗 CONTAINER_ORDERS — tour_id/order_id felter ryddes (selve ordren bevares):")
    print(f"  ⤺ {snap['counts']['container_orders (with tour_id linkage)']} ordrer med tour-linkage")

    print()
    print("✅ BEVARES UÆNDRET:")
    for c in PRESERVED_COLLECTIONS:
        print(f"  • {c}")

    print()
    print("─" * 78)
    print(f"TOTAL DOKUMENTER DER SLETTES: {sum(snap['counts'][c] for c in LOGISTICS_COLLECTIONS) + len(drv_users) + snap['counts']['invitation_tokens (driver-related)']}")
    print(f"TOTAL ORDRER DER MODIFICERES (kun tour_id ryddes): {snap['counts']['container_orders (with tour_id linkage)']}")
    print("─" * 78)


def perform_wipe(db, snap_path):
    """The actual destructive operation. Only called after explicit confirmation."""
    print()
    print("⏳ Udfører wipe...")
    summary = {}

    # 1) Drop logistics collections
    for coll in LOGISTICS_COLLECTIONS:
        res = db[coll].delete_many({})
        summary[coll] = res.deleted_count
        print(f"  ✗ {coll}: slettet {res.deleted_count}")

    # 2) Delete driver users
    drv = db.users.delete_many({"role": "driver"})
    summary["users (role=driver)"] = drv.deleted_count
    print(f"  ✗ users (role=driver): slettet {drv.deleted_count}")

    # 3) Delete invitation_tokens for drivers (find first since we just deleted them)
    # Use snapshot data to identify them
    with open(snap_path, "r", encoding="utf-8") as f:
        snap_data = json.load(f)
    driver_user_ids = [u.get("id") for u in snap_data["collections"]["users_drivers"] if u.get("id")]
    if driver_user_ids:
        inv = db.invitation_tokens.delete_many({"user_id": {"$in": driver_user_ids}})
        summary["invitation_tokens (driver-related)"] = inv.deleted_count
        print(f"  ✗ invitation_tokens (driver): slettet {inv.deleted_count}")
    else:
        summary["invitation_tokens (driver-related)"] = 0

    # 4) Clear tour_id / order_id linkage on container_orders (preserve the orders themselves)
    res = db.container_orders.update_many(
        {"$or": [{"tour_id": {"$exists": True}}, {"order_id": {"$exists": True}}]},
        {"$unset": {"tour_id": "", "tour_completed": "", "tour_on_way": "", "tour_weight": "", "driver_name": "", "driver_id": ""}}
    )
    summary["container_orders (tour_id cleared)"] = res.modified_count
    print(f"  ⤺ container_orders modificeret: {res.modified_count}")

    print()
    print("✅ Wipe komplet.")
    return summary


def show_state(db, label):
    """Print collection counts for verification."""
    print(f"\n📊 STATE — {label}:")
    print("─" * 60)
    all_cols = sorted(db.list_collection_names())
    for c in all_cols:
        cnt = db[c].count_documents({})
        marker = "✗" if c in LOGISTICS_COLLECTIONS else "  "
        print(f"  {marker} {c:<35} {cnt}")
    # Special user breakdown
    drv = db.users.count_documents({"role": "driver"})
    if drv > 0:
        print(f"      ↳ {drv} drivers will be removed")


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Logistik-data wipe (Fase 1)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be deleted. Default if neither --confirm nor --snapshot-only is given.")
    parser.add_argument("--snapshot-only", action="store_true",
                        help="Create snapshot dump, but do NOT wipe.")
    parser.add_argument("--confirm", action="store_true",
                        help="Actually perform the wipe (still requires typing the confirmation phrase).")
    args = parser.parse_args()

    # Default to dry-run if no destructive flag was set
    if not args.confirm and not args.snapshot_only:
        args.dry_run = True

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "test_database")
    if not mongo_url:
        print("❌ MONGO_URL ikke sat", file=sys.stderr)
        sys.exit(1)

    client = MongoClient(mongo_url)
    db = client[db_name]
    print(f"🔌 Forbundet til database: {db_name}")

    show_state(db, "FØR")
    snap = build_snapshot(db)

    if args.dry_run:
        print_dry_run(db, snap)
        # Skip snapshot writing on pure dry-run (no destructive action follows)
        print("\n💡 Kør med --confirm for at udføre wipe (snapshot oprettes automatisk først).")
        return

    # SNAPSHOT — written BEFORE any destructive action
    snap_path = write_snapshot(snap)
    print(f"\n💾 Snapshot gemt: {snap_path}")
    print(f"   Størrelse: {snap_path.stat().st_size:,} bytes")
    # Verify it opens
    with snap_path.open("r", encoding="utf-8") as f:
        verify = json.load(f)
    print(f"   Verificeret: {sum(verify['counts'].values())} dokumenter snapshot'et")

    if args.snapshot_only:
        print("\n✅ Snapshot-only mode — wipe blev IKKE udført.")
        return

    # Final confirmation
    print()
    print("⚠️  " + "═" * 70)
    print("⚠️   DESTRUKTIV OPERATION — kan IKKE fortrydes (men snapshot er gemt) ")
    print("⚠️  " + "═" * 70)
    phrase = "WIPE LOGISTICS"
    typed = input(f"\nSkriv præcis '{phrase}' for at fortsætte (ellers afbrudt): ").strip()
    if typed != phrase:
        print(f"\n❌ Bekræftelse-frase matchede ikke ('{typed}'). AFBRUDT.")
        sys.exit(0)

    summary = perform_wipe(db, snap_path)

    show_state(db, "EFTER")

    print()
    print("═" * 78)
    print(" ✅ WIPE FÆRDIG — Container-data uberørt, logistik nulstillet ")
    print("═" * 78)
    print(f"   Snapshot: {snap_path}")
    print()


if __name__ == "__main__":
    main()
