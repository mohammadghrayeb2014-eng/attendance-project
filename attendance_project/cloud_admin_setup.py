import bcrypt
import certifi
from pymongo import MongoClient
import os
from dotenv import load_dotenv

MONGO_URI = "mongodb+srv://attendance_db:jdk344hj@cluster03.xelztiz.mongodb.net/?appName=Cluster03"
MONGO_DB_NAME = "attendance_db"

def setup():
    print(f"Connecting to Cloud DB: {MONGO_URI.split('@')[-1]}...")
    
    try:
        client = MongoClient(MONGO_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=10000)
        client.admin.command('ping')
        print("✅ Successfully connected to MongoDB Atlas!")
        
        db = client[MONGO_DB_NAME]
        
        username = "admin"
        password = "admin123"
        
        print(f"Adding/Updating account: {username}...")
        pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        db.users.update_one(
            {"username": username},
            {"$set": {
                "password_hash": pw_hash,
                "role": "admin",
                "name": "Administrator"
            }},
            upsert=True
        )
        
        print(f"🚀 SUCCESS! Cloud user '{username}' is ready with password: {password}")

    except Exception as e:
        print(f"❌ CONNECTION FAILED: {e}")

if __name__ == "__main__":
    setup()
