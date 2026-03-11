from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv("school-portal/backend/.env")
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")

print(f"Connecting to: {MONGO_DB_NAME}...")

try:
    # Use standard client for Atlas (tlsAllowInvalidCertificates is a fallback for local env issues)
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    print("✅ SUCCESS: Connected to MongoDB Atlas!")
    
    db = client[MONGO_DB_NAME]
    users_count = db.users.count_documents({})
    print(f"✅ Data integrity: Found {users_count} users in the database.")
except Exception as e:
    print(f"❌ CONNECTION FAILED: {e}")
