"""
Test Script for Hybrid AI Chat Endpoint (/chat)
"""
import requests

API_URL = "http://localhost:8000"

# 1. Login to get JWT Token
login_res = requests.post(f"{API_URL}/login", json={"email": "agent_user@example.com", "password": "securepassword123"})
if login_res.status_code != 200:
    # Register if needed
    requests.post(f"{API_URL}/register", json={"email": "agent_user@example.com", "password": "securepassword123", "firstname": "AI", "lastname": "Agent"})
    login_res = requests.post(f"{API_URL}/login", json={"email": "agent_user@example.com", "password": "securepassword123"})

token = login_res.json()["access_token"]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

print("==================================================")
print("TEST 1: User states a new fact")
print("==================================================")
msg1 = "My favorite database is PostgreSQL with pgvector for AI applications."
res1 = requests.post(f"{API_URL}/chat", headers=headers, json={"message": msg1})
print("User:", msg1)
print("Response:", res1.json())

print("\n==================================================")
print("TEST 2: User asks a question (Retrieves context!)")
print("==================================================")
msg2 = "What database do I prefer for my AI projects?"
res2 = requests.post(f"{API_URL}/chat", headers=headers, json={"message": msg2})
print("User:", msg2)
print("Response:", res2.json())
print("==================================================")
