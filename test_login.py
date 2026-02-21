import requests

url = "http://127.0.0.1:5001/api/login"
payload = {
    "username": "admin",
    "password": "wrongpassword"
}

try:
    res = requests.post(url, json=payload)
    print(f"Status: {res.status_code}")
    print(f"Response: {res.json()}")
except Exception as e:
    print(f"Error: {e}")
