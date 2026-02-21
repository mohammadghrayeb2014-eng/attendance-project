"""
seed_db.py — Seeds the MongoDB database with all required collections.
Run this ONCE after MongoDB is installed and running.

Admin login will be:
  username: admin
  password: AdminPass123!
"""
import bcrypt
import json
from pathlib import Path
from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "attendance_db"
DATA_DIR = Path(__file__).parent / "data"


def hash_pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def read_json(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def seed():
    print("Connecting to MongoDB...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]

    # ── USERS ────────────────────────────────────────────────────────────────
    # Always ensure the admin user exists with the correct password
    admin_hash = hash_pw("AdminPass123!")

    # Remove any existing admin and re-insert with fresh hash
    db.users.delete_one({"username": "admin"})
    db.users.insert_one({
        "id": 1,
        "username": "admin",
        "role": "admin",
        "name": "Administrator",
        "password_hash": admin_hash
    })
    print("[OK] Admin user seeded  (username=admin  password=AdminPass123!)")

    # Migrate any extra users from users.json that don't already exist
    existing_usernames = {u["username"] for u in db.users.find({}, {"username": 1})}
    json_users = read_json("users.json")
    for u in json_users:
        if u.get("username") and u["username"] not in existing_usernames:
            if not u.get("password_hash"):
                # skip users with empty hashes
                continue
            db.users.insert_one({k: v for k, v in u.items() if k != "_id"})
            existing_usernames.add(u["username"])
    print(f"[OK] users collection now has {db.users.count_documents({})} document(s)")

    # -- OTHER COLLECTIONS -------------------------------------------------
    collections_to_seed = [
        "classes", "subjects", "assignments",
        "exams", "homework", "grades", "attendance"
    ]
    for cname in collections_to_seed:
        if db[cname].count_documents({}) == 0:
            data = read_json(f"{cname}.json")
            if data:
                db[cname].insert_many(data)
                print(f"[OK] {cname}: imported {len(data)} record(s) from JSON")
            else:
                print(f"  {cname}: empty (no JSON data to import)")
        else:
            print(f"  {cname}: already has {db[cname].count_documents({})} record(s), skipped")

    print("\n[DONE] Database seeded successfully!")
    print("   Login credentials -> username: admin  |  password: AdminPass123!")


if __name__ == "__main__":
    seed()
