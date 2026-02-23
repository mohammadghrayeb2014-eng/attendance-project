import bcrypt
from pymongo import MongoClient
import os

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["attendance_db"]
users_col = db["users"]

def fix_admin():
    username = "admin"
    password = "admin123"
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    
    result = users_col.update_one(
        {"username": username},
        {"$set": {"password_hash": pw_hash, "role": "admin", "name": "Administrator"}},
        upsert=True
    )
    
    if result.matched_count > 0:
        print(f"Updated existing admin user with password: {password}")
    else:
        print(f"Created new admin user with password: {password}")

if __name__ == "__main__":
    fix_admin()
