import pandas as pd
from pymongo import MongoClient
from pathlib import Path
import os

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["attendance_db"]

def migrate_attendance():
    master_path = Path("output/attendance/master_attendance.csv")
    if not master_path.exists():
        print("No master_attendance.csv found to migrate.")
        return

    df = pd.read_csv(master_path)
    if df.empty:
        print("master_attendance.csv is empty.")
        return

    # In MongoDB, we'll store each date session as a document in 'attendance_sessions' 
    # OR we can keep the existing 'attendance' collection format which seems to be:
    # { "class_id": ..., "subject_id": ..., "date": ..., "records": [ {"name": ..., "status": ...}, ... ] }
    
    # The master_attendance.csv is a pivot table: name, date1, date2, ...
    # Let's convert it back to a list of sessions if possible, or just store it as is.
    # Actually, the user wants "whole project on mongodb", so let's stick to the 'attendance' collection schema.
    
    date_cols = [col for col in df.columns if col != 'name']
    
    for date in date_cols:
        records = []
        for _, row in df.iterrows():
            records.append({
                "name": row['name'],
                "status": "Present" if row[date] == "YES" else "Absent"
            })
        
        # Check if this session already exists in DB
        if not db.attendance.find_one({"date": date}):
            db.attendance.insert_one({
                "class_id": 1, # Default or dummy
                "subject_id": 1, # Default or dummy
                "teacher_username": "admin",
                "date": date,
                "records": records
            })
            print(f"Migrated session for date: {date}")
        else:
            print(f"Session for date {date} already exists in MongoDB, skipping.")

if __name__ == "__main__":
    migrate_attendance()
