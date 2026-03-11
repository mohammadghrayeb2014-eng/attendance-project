import bcrypt
import certifi
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# Path to the backend .env
dotenv_path = "school-portal/backend/.env"
load_dotenv(dotenv_path)

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "attendance_db")

def setup():
    if not MONGO_URI:
        print("❌ Error: MONGO_URI not found in .env")
        return

    print(f"Connecting to Cloud DB: {MONGO_URI.split('@')[-1]}...")
    
    try:
        # tlsCAFile=certifi.where() is critical for Windows users connecting to Atlas
        client = MongoClient(MONGO_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=10000)
        client.admin.command('ping')
        print("✅ Successfully connected to MongoDB Atlas!")
        
        db = client[MONGO_DB_NAME]
        
        # Create/Update Admin account
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
        print("\n--- FINAL STEP ---")
        print("1. Push this change to GitHub (I will do this for you).")
        print("2. Go to your Render/Vercel dashboard and ensure MONGO_URI there matches the one in .env.")
        print("3. Try logging in again.")

    except Exception as e:
        print(f"❌ CONNECTION FAILED: {e}")
        print("\nPossible reasons:")
        print("1. Your IP address is not whitelisted in MongoDB Atlas 'Network Access'.")
        print("2. The database user/password in the URI is incorrect.")
        print("3. The 'Cluster03' Hostname is incorrect.")

if __name__ == "__main__":
    setup()
