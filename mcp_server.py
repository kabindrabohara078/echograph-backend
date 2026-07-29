"""
EchoGraph Model Context Protocol (MCP) Server
Allows Claude Desktop (or any MCP client) to read and write episodic memory context directly.
"""
import os
import sys
import requests
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("EchoGraph")

# EchoGraph configuration (default to local instance)
API_URL = os.getenv("ECHOGRAPH_API_URL", "http://localhost:8000").rstrip("/")
EMAIL = os.getenv("ECHOGRAPH_EMAIL", "agent_user@example.com")
PASSWORD = os.getenv("ECHOGRAPH_PASSWORD", "securepassword123")

token_cache = None


def get_auth_token():
    """Retrieves or renews the JWT authentication token."""
    global token_cache
    if token_cache:
        return token_cache

    try:
        res = requests.post(f"{API_URL}/login", json={"email": EMAIL, "password": PASSWORD})
        if res.status_code == 200:
            token_cache = res.json().get("access_token")
            return token_cache

        sys.stderr.write(f"Login failed ({res.status_code}): {res.text}\n")

        # Try to register first if user does not exist
        reg = requests.post(f"{API_URL}/register", json={
            "email": EMAIL,
            "password": PASSWORD,
            "firstname": "Claude",
            "lastname": "Desktop"
        })
        if reg.status_code not in (200, 201):
            sys.stderr.write(f"Register failed ({reg.status_code}): {reg.text}\n")
            return None

        res = requests.post(f"{API_URL}/login", json={"email": EMAIL, "password": PASSWORD})
        if res.status_code == 200:
            token_cache = res.json().get("access_token")
            return token_cache
        sys.stderr.write(f"Login after register failed ({res.status_code}): {res.text}\n")
    except Exception as e:
        sys.stderr.write(f"Auth error: {str(e)}\n")
    return None


@mcp.tool()
def auth() -> str:
    """
    Authenticate with the EchoGraph server — logs in if the account exists,
    registers it otherwise. Returns the result so you can debug credential issues.
    """
    global token_cache
    token_cache = None  # force a fresh attempt
    token = get_auth_token()
    if token:
        return f"Authenticated successfully. Token: {token[:12]}..."
    return "Authentication failed. Check stderr logs for the specific error (wrong credentials, unreachable server, or unexpected response shape)."


@mcp.tool()
def store_memory(context: str, category: str = "fact") -> str:
    """
    Store a fact, preference, user statement, or decision into the long-term vector memory database.

    Args:
        context: The user details, preference, or fact to remember.
        category: Memory type (e.g. 'fact', 'preference', 'decision', 'goal').
    """
    token = get_auth_token()
    if not token:
        return "Error: Could not authenticate with EchoGraph Server."

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "context": context,
            "type": category,
            "score": 1.0,
            "node_life": 91
        }
        res = requests.post(f"{API_URL}/memory", headers=headers, json=payload)
        if res.status_code == 200:
            return f"Successfully stored memory: '{context}' (Category: {category})"
        return f"Failed to store memory: {res.text}"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def retrieve_memory(query: str, category: str = None) -> str:
    """
    Search and retrieve historical facts, preferences, or context related to the user query.

    Args:
        query: Search keywords or question to match context.
        category: Optional category filter (e.g. 'preference', 'fact').
    """
    token = get_auth_token()
    if not token:
        return "Error: Could not authenticate with EchoGraph Server."

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"query": query}
        if category:
            payload["type"] = category

        res = requests.post(f"{API_URL}/search", headers=headers, json=payload)
        if res.status_code == 200:
            results = res.json().get("results", [])
            if not results:
                return "No matching memories found."

            lines = []
            for item in results:
                lines.append(f"- [{item['type'].upper()}] {item['content']} (Cosine Distance: {item['distance']:.3f}, Rank: {item['final_rank']:.2f})")
            return "\n".join(lines)
        return f"Failed to retrieve memories: {res.text}"
    except Exception as e:
        return f"Error: {str(e)}"


if __name__ == "__main__":
    # FastMCP uses standard input/output (stdio) transport to communicate with Claude Desktop
    mcp.run()