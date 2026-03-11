import bcrypt
from pymongo import MongoClient

MONGO_URI="mongodb+srv://attendance_db:jdk344hj@cluster03.xelztiz.mongodb.net/?appName=Cluster03"


client = MongoClient(MONGO_URI)
database = client["attendance_db"]

password = "admin123"
pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

database.users.update_one(
    {"username": "admin"},
    {"$set": {
        "password_hash": pw_hash,
        "role": "admin",
        "name": "Administrator"
    }},
    upsert=True
)

print(f"Created/Updated admin with password: {password}")