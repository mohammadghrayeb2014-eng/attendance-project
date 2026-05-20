from pymongo import MongoClient
import bcrypt

client = MongoClient("mongodb://localhost:27017")
db = client["attendance_db"]
users = list(db.users.find({}, {"_id": 0}))

print(f"Total users found: {len(users)}")
for u in users:
    print(f"User: {u.get('username')}, Role: {u.get('role')}, Hash exists: {bool(u.get('password_hash'))}")
    if u.get('password_hash'):
        # Test a common password if you want, but just checking if it looks like a hash
        print(f"  Hash: {u.get('password_hash')[:10]}...")
