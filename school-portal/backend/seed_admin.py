import bcrypt
from pymongo import MongoClient

MONGO_URI="mongodb+srv://attendance_db:jdk344hj@cluster03.xelztiz.mongodb.net/?appName=Cluster03"


client = MongoClient(MONGO_URI)
database = client["attendance_db"]

password = "admin123"
pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

user = {
    "id": 1,
    "username": "admin@gmail.com",
    "role": "admin",
    "name": "Admin",
    "password_hash": pw_hash
}

database["users"].insert_one(user)
print("Admin created successfully!")