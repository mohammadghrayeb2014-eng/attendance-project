import bcrypt
from pymongo import MongoClient
import os

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["attendance_db"]
users_col = db["users"]

def reset_all_passwords():
    new_password = "123"
    pw_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    
    # Update all users to have '123' as password
    result = users_col.update_many(
        {}, 
        {"$set": {"password_hash": pw_hash}}
    )
    
    print(f"Successfully reset {result.modified_count} user passwords to '123'")
    print(f"You can now login as 'admin' with password '123'")

if __name__ == "__main__":
    reset_all_passwords()
