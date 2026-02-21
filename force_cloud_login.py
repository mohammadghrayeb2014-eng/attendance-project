import bcrypt
import os
from pymongo import MongoClient

# PASTE YOUR CLOUD LINK HERE
# Example: mongodb+srv://Admin:PASSWORD@cluster.mongodb.net/
CLOUD_URI = "mongodb+srv://Admin:ghraib2014@cluster0.e9v82ox.mongodb.net/?appName=Cluster0"
MONGO_DB_NAME = "attendance_db"

client = MongoClient(CLOUD_URI)
db = client[MONGO_DB_NAME]

def reset_user(username, password, role="admin"):
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.users.update_one(
        {"username": username},
        {"$set": {
            "password_hash": pw_hash,
            "role": role,
            "name": username.capitalize()
        }},
        upsert=True
    )
    print(f"Cloud User '{username}' has been RESET/CREATED with password: {password}")

if __name__ == "__main__":
    print(f"Connecting to Cloud: {CLOUD_URI.split('@')[-1]}")
    reset_user("admin", "admin123", "admin")
    reset_user("teacher", "teacher123", "teacher")
    reset_user("student", "student123", "student")
    print("\nSUCCESS! You can now log into https://attendance-project-final.vercel.app")
