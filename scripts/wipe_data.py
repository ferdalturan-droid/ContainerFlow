"""
Wipe ALL platform data except the single super_admin (doganmiketuran@gmail.com).
Run with: python /app/scripts/wipe_data.py
"""
import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

KEEP_EMAIL = "doganmiketuran@gmail.com"

client = MongoClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

print(f"Database: {os.environ['DB_NAME']}")
print(f"Keeping super_admin user: {KEEP_EMAIL}\n")

# Show current state
print("BEFORE:")
for col in db.list_collection_names():
    print(f"  {col}: {db[col].count_documents({})}")

# Wipe everything except the one keeper user
keeper_count = db.users.count_documents({"email": KEEP_EMAIL, "role": "super_admin"})
if keeper_count == 0:
    print(f"\n⚠️  Keeper user '{KEEP_EMAIL}' NOT found as super_admin. Aborting!")
    sys.exit(1)

print(f"\nFound {keeper_count} keeper user(s).\n")

# 1. Delete users except the keeper (super_admin only)
res = db.users.delete_many({
    "$or": [
        {"email": {"$ne": KEEP_EMAIL}},
        {"email": KEEP_EMAIL, "role": {"$ne": "super_admin"}},
    ]
})
print(f"users: deleted {res.deleted_count}")

# 2. Wipe everything else
wipe_collections = [
    "companies",
    "plads",
    "locations",
    "tours",
    "container_orders",
    "container_overrides",
    "container_counts",
    "customer_addresses",
    "drivers",
    "driver_sessions",
    "invitation_tokens",
    "receipts",
    "pdf_archives",
    "messages",
    "reports",
    "tour_prices",
    "plads_addresses",
    "genbrug_orders",
    "activity_log",
    "push_subscriptions",
]
for col in wipe_collections:
    if col in db.list_collection_names():
        res = db[col].delete_many({})
        print(f"{col}: deleted {res.deleted_count}")

# Re-create essential super_admin if needed and reset password to known value
import sys as _sys
_sys.path.insert(0, "/app/backend")
from auth import hash_password  # noqa: E402

NEW_PASSWORD = "SuperAdmin2026!"
keeper = db.users.find_one({"email": KEEP_EMAIL})
if keeper:
    db.users.update_one(
        {"_id": keeper["_id"]},
        {
            "$set": {
                "role": "super_admin",
                "active": True,
                "password_hash": hash_password(NEW_PASSWORD),
                "invitation_status": "active",
                "managed_company_ids": [],
            }
        },
    )
    print(f"\n✓ Keeper user reset: {keeper.get('email')} (password={NEW_PASSWORD!r})")
else:
    print(f"\n⚠️ Did not find keeper — re-creating now.")
    import uuid as _uuid
    from datetime import datetime, timezone as _tz
    db.users.insert_one({
        "id": str(_uuid.uuid4()),
        "email": KEEP_EMAIL,
        "name": "Dogan",
        "role": "super_admin",
        "active": True,
        "password_hash": hash_password(NEW_PASSWORD),
        "invitation_status": "active",
        "managed_company_ids": [],
        "created_at": datetime.now(_tz.utc).isoformat(),
    })
    print(f"✓ Created keeper {KEEP_EMAIL!r} with password {NEW_PASSWORD!r}")

print("\nAFTER:")
for col in db.list_collection_names():
    print(f"  {col}: {db[col].count_documents({})}")
print("\n✓ Data wipe complete.")
