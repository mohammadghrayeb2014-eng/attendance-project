from pymongo import MongoClient
import os
from dotenv import load_dotenv

def test(uri, name):
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        print(f"✅ SUCCESS: {name}")
        return True
    except Exception as e:
        # Check if it's auth error
        if "Authentication failed" in str(e) or "bad auth" in str(e):
             print(f"❌ AUTH FAILED: {name}")
        else:
             print(f"❌ ERROR: {name} - {e}")
        return False

tests = [
    # Cluster 03 (User Provided)
    ("mongodb+srv://attendance_db:mohammadgh2000@cluster03.xelztiz.mongodb.net/?appName=Cluster03", "Cluster03-attendance_db-USER"),
    ("mongodb+srv://attendance_db:jdk344hj@cluster03.xelztiz.mongodb.net/?appName=Cluster03", "Cluster03-attendance_db-old"),
    ("mongodb+srv://Admin:mohammadgh2000@cluster03.xelztiz.mongodb.net/?appName=Cluster03", "Cluster03-Admin-new"),
    ("mongodb+srv://Admin:ghraib2014@cluster03.xelztiz.mongodb.net/?appName=Cluster03", "Cluster03-Admin-old"),

    # Cluster 0 (from fix_cloud.py)
    ("mongodb+srv://Admin:mohammadgh2000@cluster0.e9v82ox.mongodb.net/?appName=Cluster0", "Cluster0-Admin-new"),
    ("mongodb+srv://Admin:ghraib2014@cluster0.e9v82ox.mongodb.net/?appName=Cluster0", "Cluster0-Admin-old"),
    ("mongodb+srv://attendance_db:mohammadgh2000@cluster0.e9v82ox.mongodb.net/?appName=Cluster0", "Cluster0-attendance_db-new"),
    ("mongodb+srv://attendance_db:jdk344hj@cluster0.e9v82ox.mongodb.net/?appName=Cluster0", "Cluster0-attendance_db-old"),
]

for uri, name in tests:
    test(uri, name)
