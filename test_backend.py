import urllib.request
import json

BASE_URL = "http://localhost:8000"

def post_json(url, data, headers=None):
    if headers is None:
        headers = {}
    headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))

def get_json(url):
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode('utf-8'))

def test_api():
    print("1. Testing Root API...")
    status, res = get_json(f"{BASE_URL}/")
    print("Root response:", status, res)

    test_email = "testuser_rag@example.com"
    test_password = "password123"

    print("\n2. Testing Register...")
    reg_payload = {
        "firstname": "Test",
        "lastname": "User",
        "email": test_email,
        "password": test_password
    }
    status, res = post_json(f"{BASE_URL}/register", reg_payload)
    print("Register response:", status, res)

    print("\n3. Testing Login...")
    login_payload = {
        "email": test_email,
        "password": test_password
    }
    status, res = post_json(f"{BASE_URL}/login", login_payload)
    print("Login response:", status, res)
    token = res.get("access_token")

    if not token:
        print("Failed to obtain access token!")
        return

    headers = {
        "Authorization": f"Bearer {token}"
    }

    print("\n4. Testing Memory Creation (RAG Store)...")
    mem_payload = {
        "context": "User prefers dark mode theme and high contrast buttons in frontend applications.",
        "type": "preference",
        "score": 1.0,
        "node_life": 91
    }
    status, res = post_json(f"{BASE_URL}/memory", mem_payload, headers=headers)
    print("Memory creation response:", status, res)

    print("\n5. Testing Memory Vector Search (RAG Retrieve)...")
    search_payload = {
        "query": "What UI theme and button style does the user prefer?",
        "type": "preference"
    }
    status, res = post_json(f"{BASE_URL}/search", search_payload, headers=headers)
    print("Search response status:", status)
    print("Search results:\n", json.dumps(res, indent=2))

if __name__ == "__main__":
    test_api()
