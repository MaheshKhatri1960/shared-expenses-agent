"""
Fix wrong date on NOBLE PLUS transaction
Run: python fix_date.py
"""
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from urllib.parse import quote_plus
from bson import ObjectId

# Set your password here
PASSWORD = "bahutpaisa"  # ← Replace with your actual password

uri = f"mongodb+srv://mahesh:{quote_plus(PASSWORD)}@cluster0.0qjbym8.mongodb.net/?appName=Cluster0"
client = MongoClient(uri, server_api=ServerApi("1"))
db = client["household_expenses"]

result = db.transactions.update_one(
    {"_id": ObjectId("6a2823d02ecbda8e4c639b92")},
    {"$set": {
        "transaction_date": "2026-06-08",
        "vendor_bill_date": "2026-06-08"
    }}
)

print(f"Updated: {result.modified_count} record")

# Verify
doc = db.transactions.find_one({"_id": ObjectId("6a2823d02ecbda8e4c639b92")}, {"transaction_date": 1, "vendor_bill_date": 1, "vendor": 1})
print(f"Verified: {doc}")

client.close()
