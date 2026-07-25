"""
Fase 18.43 — Generér demo-bestillinger med trends
==================================================
Opretter mange varierede bestillinger på Blishøj 1, Blishøj 49, SAC og Cirklen
spredt over de sidste 60 dage, så rapporter viser et flot trend-mønster.

Kør: python3 /app/scripts/generate_demo_orders.py
"""
import os
import re
import uuid
import random
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient

# --- Load env ---
env = {}
with open('/app/backend/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")

MONGO_URL = env['MONGO_URL']
DB_NAME = env['DB_NAME']

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

# --- Target lokationer ---
TARGETS = [
    {"code": "1967", "name": "Boliggården - Blishøj 1"},
    {"code": "6164", "name": "Boliggården - Blishøj 49"},
    {"code": "4178", "name": "SAC (Skibstrup)"},
    {"code": "6322", "name": "Cirklen"},
]
TARGET_COMPANY = "a949d27f-af3a-4af8-9d70-b31cd36ac8d4"

# --- Load reference data ---
co2_types = list(db.co2_types.find({"company_id": TARGET_COMPANY}))
co2_by_name = {t["name"].lower(): t for t in co2_types}

# Available materials (fald tilbage til standard-liste hvis container_counts er tomme)
STANDARD_MATERIALS = [
    "Pap", "Papir", "Træ", "Metal", "Glas", "Plast", "Elektronik",
    "Storskrald", "Have- og parkaffald", "Beton", "Jord", "Asfalt",
    "Restaffald", "Farligt affald",
]

PRIORITIES = ["haster", "normal", "senere"]
PRIORITY_WEIGHTS = [10, 70, 20]  # normal er hyppigst

# Users på target company (til created_by fyld)
users = list(db.users.find({"company_id": TARGET_COMPANY, "role": {"$in": ["order", "location_admin", "customer_admin"]}}))
if not users:
    users = list(db.users.find({"role": "order"}).limit(5))
print(f"Fandt {len(users)} brugere til at oprette bestillinger")

# Delivery addresses map (location_code -> list of addresses)
delivery_addr_map = {}
for code in [t["code"] for t in TARGETS]:
    addrs = list(db.delivery_addresses.find({"location_code": code}))
    delivery_addr_map[code] = addrs

# --- Slet gamle demo-bestillinger (kun dem markeret som demo) ---
existing_demo = db.container_orders.count_documents({"demo_data": True})
print(f"Sletter {existing_demo} eksisterende demo-bestillinger...")
db.container_orders.delete_many({"demo_data": True})
# Slet også de generede tours der har source='demo_data'
db.tours.delete_many({"source": "demo_data"})

# --- Generér bestillinger ---
now = datetime.now(timezone.utc)
orders_to_insert = []
tours_to_insert = []
total_planned = 0

# Til hver location — generér 20-35 bestillinger spredt over 60 dage
for loc in TARGETS:
    code = loc["code"]
    name = loc["name"]
    n_orders = random.randint(20, 35)
    total_planned += n_orders
    print(f"\n→ Genererer {n_orders} bestillinger for {name} (code={code})")

    # Materials for denne plads (fra container_counts, ellers standard)
    mats_here = list(db.container_counts.find({"location_code": code}))
    if mats_here:
        loc_materials = [(m["material"], m.get("count", 1)) for m in mats_here]
    else:
        loc_materials = [(m, random.randint(1, 3)) for m in random.sample(STANDARD_MATERIALS, 8)]

    addrs = delivery_addr_map.get(code, [])

    for _ in range(n_orders):
        # Random dato inden for sidste 60 dage — vægt mod nyere datoer
        days_ago = int(random.triangular(0, 60, 15))
        order_date = (now - timedelta(days=days_ago)).date().isoformat()

        # Status logic: ældre bestillinger primært completed, nyere primært pending
        if days_ago > 30:
            status_choice = random.choices(["completed", "completed", "completed", "cancelled"], weights=[70, 15, 10, 5], k=1)[0]
        elif days_ago > 7:
            status_choice = random.choices(["completed", "completed", "pending"], weights=[75, 15, 10], k=1)[0]
        else:
            status_choice = random.choices(["pending", "completed", "on_way"], weights=[55, 25, 20], k=1)[0]

        # Vælg material + container-nummer
        material, count_max = random.choice(loc_materials)
        container_num = f"Container {random.randint(1, max(1, count_max))}"

        # Priority
        priority = random.choices(PRIORITIES, weights=PRIORITY_WEIGHTS, k=1)[0]

        # CO2 lookup (case-insensitive contains)
        co2 = None
        for key, t in co2_by_name.items():
            if key in material.lower() or material.lower() in key:
                co2 = t
                break
        co2_id = co2["id"] if co2 else ""
        co2_name = co2["name"] if co2 else ""
        co2_factor = float(co2.get("factor", 0)) if co2 else 0.0

        # Weight (kg) - kun for completed
        weight_kg = 0.0
        co2_kg = 0.0
        if status_choice == "completed":
            weight_kg = round(random.uniform(200, 2500), 1)
            co2_kg = round((co2_factor * weight_kg) / 1000.0, 2)

        # Delivery address
        addr = random.choice(addrs) if addrs else None
        delivery_addr_id = addr.get("id", "") if addr else ""
        customer_address = ""
        if addr:
            street = addr.get("street", "")
            pc = addr.get("postcode", "")
            city = addr.get("city", "")
            customer_address = f"{street}, {pc} {city}".strip(", ")

        # Random bruger
        user = random.choice(users) if users else None
        created_by_id = user.get("id", "") if user else ""
        created_by_name = user.get("name", "") if user else ""
        created_by_email = user.get("email", "") if user else ""

        created_at = (now - timedelta(days=days_ago, hours=random.randint(0, 8))).isoformat()

        order_id = str(uuid.uuid4())
        tour_id = str(uuid.uuid4())

        # Container order document
        order = {
            "id": order_id,
            "location_code": code,
            "location_name": name,
            "address_id": "",
            "customer_name": name,
            "customer_address": customer_address,
            "container_number": container_num,
            "container_id_override": "",
            "material": material,
            "co2_type_id": co2_id,
            "co2_type_name": co2_name,
            "co2_factor": co2_factor,
            "weight_kg": weight_kg,
            "co2_kg": co2_kg,
            "order_date": order_date,
            "priority": priority,
            "comment": "" if random.random() < 0.7 else random.choice([
                "Skal tømmes hurtigst muligt", "Standard afhentning", "Rådne rester i bunden — bær handsker",
                "OK", "Full container", "Har været fyldt i 2 dage",
            ]),
            "status": status_choice,
            "driver_id": "",
            "driver_name": "",
            "admin_note": "",
            "sort_order": 0,
            "completed_at": created_at if status_choice == "completed" else "",
            "open_from": "07:00",
            "open_to": "16:00",
            "tour_type": "normal",
            "estimated_count": 0,
            "partner_id": "",
            "created_at": created_at,
            "created_by_user_id": created_by_id,
            "created_by_name": created_by_name,
            "created_by_email": created_by_email,
            "delivery_address_id": delivery_addr_id,
            "alternative_delivery_address_id": "",
            "manual_alternative_address": "",
            "original_customer_address": customer_address,
            "workshop_id": "",
            "workshop_name": "",
            "workshop_address": "",
            "workshop_phone": "",
            "workshop_override": False,
            "capacity_label": "",
            "capacity_volume_m3": None,
            "company_id": TARGET_COMPANY,
            "assigned_logistics_company_ids": [],
            "tour_id": tour_id,
            "demo_data": True,  # marker så vi kan slette dem senere
        }
        orders_to_insert.append(order)

        # Matching tour (så drivers/rapporter kan finde det)
        tour = {
            "id": tour_id,
            "date": order_date,
            "container": container_num,
            "fraction": material,
            "facility": name,
            "address": customer_address,
            "weight": weight_kg if weight_kg > 0 else None,
            "time": "",
            "completed": status_choice == "completed",
            "on_way": status_choice == "on_way",
            "is_pause": False,
            "is_same_day": False,
            "is_private": False,
            "private_company": "",
            "open_from": "07:00",
            "open_to": "16:00",
            "remark": "",
            "plads": name,
            "driver_id": "",
            "driver_name": "",
            "report_id": "",
            "sort_order": 0,
            "priority": priority,
            "claimed_by": "",
            "claimed_by_id": "",
            "claimed_at": "",
            "receipt_image": "",
            "lat": None,
            "lng": None,
            "route_distance_km": None,
            "route_order": None,
            "transport_mode": "",
            "on_way_time": "",
            "tour_type": "normal",
            "container_type": "",
            "order_id": order_id,
            "customer_name": name,
            "customer_code": code,
            "source": "demo_data",
            "created_at": created_at,
            "capacity_label": "",
            "capacity_volume_m3": None,
            "order_date": order_date,
            "created_by_name": created_by_name,
            "created_by_email": created_by_email,
            "tour_number": "",
            "assigned_by_id": "",
            "assigned_by_name": "",
            "assigned_at": "",
            "estimated_count": 0,
            "loose_estimated_count": 0,
            "container_weights": [],
            "not_completed": False,
            "not_completed_at": "",
            "not_completed_comment": "",
            "not_completed_by_name": "",
            "reactivated_at": "",
            "reactivated_by_name": "",
            "reactivate_comment": "",
            "company_id": TARGET_COMPANY,
            "assigned_logistics_company_ids": [],
        }
        tours_to_insert.append(tour)

# --- Bulk insert ---
if orders_to_insert:
    db.container_orders.insert_many(orders_to_insert)
    print(f"\n✅ Indsat {len(orders_to_insert)} demo container_orders")
if tours_to_insert:
    db.tours.insert_many(tours_to_insert)
    print(f"✅ Indsat {len(tours_to_insert)} matching tours")

# --- Statistik ---
print("\n=== Statistik pr. lokation ===")
for loc in TARGETS:
    n_total = db.container_orders.count_documents({"location_code": loc["code"], "demo_data": True})
    n_completed = db.container_orders.count_documents({"location_code": loc["code"], "demo_data": True, "status": "completed"})
    n_pending = db.container_orders.count_documents({"location_code": loc["code"], "demo_data": True, "status": "pending"})
    print(f"  {loc['name']:35s} | total={n_total:3d} | fuldført={n_completed:3d} | afventende={n_pending:3d}")

print("\n🎉 Demo-data genereret!")
