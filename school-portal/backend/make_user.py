import bcrypt
from pymongo import MongoClient
from pathlib import Path
import json
import sys

# MongoDB connection
MONGO_URI = "mongodb://localhost:27017"
client = MongoClient(MONGO_URI)
db = client["attendance_db"]
users_col = db["users"]

def load_users():
    return list(users_col.find({}, {"_id": False}))


def save_users(users):
    # This script is a utility for batch creation. 
    # For a single user creation, it's safer to just insert_one, 
    # but keeping the existing logic structure modified for MongoDB.
    # We don't overwrite the whole collection here to avoid deleting existing users.
    pass

def next_id(users):
    return max((u.get("id", 0) for u in users), default=0) + 1


def create_user(username, password, role="teacher", name=None):
    if users_col.find_one({"username": username}):
        raise ValueError("Username already exists")

    users = load_users()
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = {
        "id": next_id(users),
        "username": username,
        "role": role,
        "name": name or username,
        "password_hash": pw_hash
    }
    users_col.insert_one(user)
    print(f"Created user: {username} (role={role}) in MongoDB")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python make_user.py <username> <password> [role] [name]")
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]
    role = sys.argv[3] if len(sys.argv) >= 4 else "teacher"
    name = sys.argv[4] if len(sys.argv) >= 5 else None

    create_user(username, password, role, name)
