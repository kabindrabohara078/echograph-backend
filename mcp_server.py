"""
EchoGraph Model Context Protocol (MCP) Server
Allows Claude Desktop (or any MCP client) to read and write episodic memory context directly.
"""
import os
import sys
import requests
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
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
        else:
            # Try to register first if user does not exist
            reg = requests.post(f"{API_URL}/register", json={
                "email": EMAIL,
                "password": PASSWORD,
                "firstname": "Claude",
                "lastname": "Desktop"
            })
            res = requests.post(f"{API_URL}/login", json={"email": EMAIL, "password": PASSWORD})
            if res.status_code == 200:
                token_cache = res.json().get("access_token")
                return token_cache
    except Exception as e:
        sys.stderr.write(f"Auth error: {str(e)}\n")
    return None

@mcp.tool()
def store_memory(
    context: str,
    category: str = "fact",
    importance: float = 1.0,
    lifespan: str = "91d"
) -> str:
    """
    Store a fact, preference, user statement, or decision into the long-term vector memory database.
    
    Args:
        context: The user details, preference, or fact to remember.
        category: Memory type (e.g. 'fact', 'preference', 'decision', 'goal').
        importance: Importance score between 0.0 and 1.0 (default: 1.0).
        lifespan: Expiration duration (e.g. 'permanent', '90d', '30d', '24h').
    """
    token = get_auth_token()
    if not token:
        return "Error: Could not authenticate with EchoGraph Server."

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "context": context,
            "type": category,
            "score": float(importance),
            "lifespan_unit": "permanent" if lifespan.lower() in ("permanent", "-1") else "days",
            "lifespan_value": 91
        }
        res = requests.post(f"{API_URL}/memory", headers=headers, json=payload)
        if res.status_code == 200:
            data = res.json()
            life_str = "Permanent" if data.get("is_permanent") or data.get("node_life") == -1 else f"{data.get('node_life')} hours remaining"
            expiry_str = data.get("expires_at") or "Never (Permanent)"
            return (
                f"Successfully stored memory into EchoGraph:\n"
                f"- Content: \"{context}\"\n"
                f"- Category: {category}\n"
                f"- Importance: {importance}\n"
                f"- Lifespan: {life_str} (Expires: {expiry_str})\n"
                f"- State: {data.get('state')}"
            )
        return f"Failed to store memory: {res.text}"
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def retrieve_memory(
    query: str,
    category: str = None,
    limit: int = 5,
    relevance_threshold: float = 0.85
) -> str:
    """
    Search and retrieve historical facts, preferences, or context related to the user query.
    
    Args:
        query: Search keywords or question to match context.
        category: Optional category filter (e.g. 'preference', 'fact'). Case-insensitive.
        limit: Maximum memories to recall (default: 5).
        relevance_threshold: Maximum cosine distance threshold (0.0 to 1.0). Lower is stricter. Default is 0.85.
    """
    token = get_auth_token()
    if not token:
        return "Error: Could not authenticate with EchoGraph Server."

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"query": query, "threshold": relevance_threshold}
        if category and category.lower() != "all":
            payload["type"] = category.strip().lower()
            
        res = requests.post(f"{API_URL}/search", headers=headers, json=payload)
        if res.status_code == 200:
            results = res.json().get("results", [])
            if not results:
                cat_info = f" in category '{category}'" if category else ""
                return f"No relevant memories found in EchoGraph for query: '{query}'{cat_info} (relevance threshold <= {relevance_threshold})."
            
            lines = [f"Retrieved {len(results)} relevant memories from EchoGraph (threshold <= {relevance_threshold}):"]
            for idx, item in enumerate(results[:limit], 1):
                life_str = "Permanent" if item.get("state") == "permanent" or item.get("node_life") == -1 else f"{item.get('node_life')}h remaining"
                expiry_str = item.get("expires_at") or "Never (Permanent)"
                rank_str = f"Rank: {item.get('final_rank', 0.0):.2f}"
                dist_str = f"Cosine Dist: {item.get('distance', 0.0):.3f}"
                imp_str = f"Importance: {item.get('importance_score', 1.0)}"
                lines.append(
                    f"{idx}. [{item.get('type', 'fact').upper()}] \"{item.get('content')}\"\n"
                    f"   ({rank_str} | {dist_str} | {imp_str} | Lifespan: {life_str} | Expires: {expiry_str})"
                )
            return "\n".join(lines)
        return f"Failed to retrieve memories: {res.text}"
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    # FastMCP uses standard input/output (stdio) transport to communicate with Claude Desktop
    mcp.run()
