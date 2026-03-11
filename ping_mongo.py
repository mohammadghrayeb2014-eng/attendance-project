from pymongo import MongoClient
import certifi

uri = "mongodb+srv://attendance_db:jdk344hj@cluster03.xelztiz.mongodb.net/?appName=Cluster03"
try:
    client = MongoClient(uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print("PING SUCCESSFUL")
except Exception as e:
    print(f"PING FAILED: {e}")
