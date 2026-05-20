import bcrypt
import sys
from pymongo import MongoClient

# YOUR CLOUD SECRETS
CLOUD_URI = "mongodb+srv://Admin:ghraib2014@cluster0.e9v82ox.mongodb.net/?appName=Cluster0"
DB_NAME = "attendance_db"

def fix():
    try:
        print("Connecting to MongoDB Atlas (SSL Bypass Mode)...")
        # tlsAllowInvalidCertificates=True skips the SSL handshake error
        client = MongoClient(CLOUD_URI, serverSelectionTimeoutMS=5000, tlsAllowInvalidCertificates=True)
        db = client[DB_NAME]
        
        # Test connection
        client.admin.command('ping')
        print("✅ Connected successfully!")

        username = "admin"
        password = "admin123"
        
        print(f"Securing account: {username}...")
        # Hash the password correctly
        pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # Update or Insert the user
        result = db.users.update_one(
            {"username": username},
            {"$set": {
                "password_hash": pw_hash,
                "role": "admin",
                "name": "Administrator"
            }},
            upsert=True
        )
        
        if result.upserted_id:
            print(f"🚀 SUCCESS! Created NEW admin account.")
        else:
            print(f"🚀 SUCCESS! Updated existing admin account.")
            
        print("\n--- NEXT STEPS ---")
        print("1. Go to: https://attendance-project-final.vercel.app")
        print(f"2. Use Username: {username}")
        print(f"3. Use Password: {password}")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    fix()
