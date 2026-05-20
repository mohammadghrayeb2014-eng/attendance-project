import bcrypt
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["attendance_db"]

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
    print(f"User {username} has been reset with password: {password}")

if __name__ == "__main__":
    reset_user("admin", "admin123", "admin")
    reset_user("teacher", "teacher123", "teacher")
    reset_user("student", "student123", "student")
