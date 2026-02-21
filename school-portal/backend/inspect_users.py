import os
import pymongo
import json

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
DB_NAME = os.getenv('MONGO_DB_NAME', 'attendance_db')

client = pymongo.MongoClient(MONGO_URI)
db = client[DB_NAME]

users = list(db.users.find({}, {'_id': False, 'password_hash': True, 'username': True, 'id': True, 'role': True, 'name': True}))
print(f"Total users: {len(users)}")
for i,u in enumerate(users[:50], start=1):
    print(f"{i}: id={u.get('id')!s} username={u.get('username')!s} role={u.get('role')!s} has_hash={bool(u.get('password_hash'))}")

# Print admin record details
admin = next((x for x in users if x.get('username','').lower()=='admin'), None)
print('\nAdmin record:')
print(json.dumps(admin, indent=2, ensure_ascii=False))

# Verify common passwords if hash present
import bcrypt
if admin and admin.get('password_hash'):
    h = admin['password_hash']
    print('\nPassword checks:')
    for pw in ['AdminPass123!', 'admin123', 'password', '123456']:
        try:
            ok = bcrypt.checkpw(pw.encode('utf-8'), h.encode('utf-8'))
        except Exception:
            ok = False
        print(f"{pw}: {ok}")
