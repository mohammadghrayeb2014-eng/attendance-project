import json
from pymongo import MongoClient

# Load the selected users
with open('data/users_mongo_seed.json', 'r', encoding='utf-8') as f:
    users = json.load(f)

# Connect to MongoDB
client = MongoClient('mongodb://localhost:27017')
db = client['attendance_db']
users_col = db['users']

# Remove all users and insert only the selected ones
users_col.delete_many({})
users_col.insert_many(users)

print('Seeded MongoDB with admin, two teachers, and one student.')
