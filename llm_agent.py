"""
EchoGraph LLM Integration Guide & Client Wrapper
Demonstrates how to connect EchoGraph to any LLM (OpenAI, Gemini, LangChain, or Ollama).
"""

import requests
import json

class EchoGraphMemoryClient:
    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url.rstrip("/")
        self.access_token = None

    def register_or_login(self, email: str = "agent_user@example.com", password: str = "securepassword123"):
        """Registers user if needed, then logs in to obtain JWT access token."""
        # 1. Try Registering
        reg_res = requests.post(f"{self.api_url}/register", json={
            "email": email,
            "password": password,
            "firstname": "AI",
            "lastname": "Agent"
        })
        
        # 2. Login
        login_res = requests.post(f"{self.api_url}/login", json={"email": email, "password": password})
        if login_res.status_code == 200:
            self.access_token = login_res.json().get("access_token")
            print(f"EchoGraph Login Successful for {email}")
            return True
        
        print(f"Authentication failed: {login_res.text}")
        return False

    def get_headers(self):
        if not self.access_token:
            raise ValueError("Client is not authenticated. Call register_or_login() first.")
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    def store_memory(self, context: str, memory_type: str = "fact", score: float = 1.0, node_life: int = 91):
        """
        Stores a fact, preference, decision, or temporary memory into EchoGraph.
        LLMs can call this via Tool / Function Calling when users state new facts.
        """
        payload = {
            "context": context,
            "type": memory_type,
            "score": score,
            "node_life": node_life
        }
        res = requests.post(f"{self.api_url}/memory", headers=self.get_headers(), json=payload)
        return res.json()

    def search_memory(self, query: str, memory_type: str = None):
        """
        Retrieves relevant context nodes based on semantic vector similarity and decay ranking.
        LLMs call this before generating a response to ground their answers in user facts.
        """
        payload = {"query": query}
        if memory_type:
            payload["type"] = memory_type
        
        res = requests.post(f"{self.api_url}/search", headers=self.get_headers(), json=payload)
        if res.status_code == 200:
            return res.json().get("results", [])
        return []

    def format_context_for_prompt(self, query: str) -> str:
        """
        Helper that fetches memories and formats them into a clean string ready for system prompts.
        """
        memories = self.search_memory(query)
        if not memories:
            return "No prior user context found."
        
        formatted_lines = []
        for idx, m in enumerate(memories, 1):
            formatted_lines.append(f"{idx}. [{m['type'].upper()}] {m['content']} (Rank: {m['final_rank']:.2f})")
        
        return "\n".join(formatted_lines)


# =====================================================================
# EXAMPLE: INTEGRATING WITH AN LLM (e.g. OpenAI / Gemini / LangChain)
# =====================================================================
if __name__ == "__main__":
    print("🤖 EchoGraph LLM Integration Demo\n")
    
    # 1. Initialize Memory Client
    memory = EchoGraphMemoryClient("http://localhost:8000")
    
    # Register/Login
    if memory.register_or_login():
        
        # 2. Store a new fact stated by user in conversation
        print("\n📥 Step 1: Agent stores a user preference...")
        store_res = memory.store_memory(
            context="User prefers dark mode UI and builds APIs using FastAPI with pgvector.",
            memory_type="preference"
        )
        print(f"Memory Store Response: {store_res}")
        
        # 3. Retrieve context before LLM generates a response
        user_query = "What framework and database should I use for my next project?"
        print(f"\n🔍 Step 2: Agent queries EchoGraph before prompting LLM for: '{user_query}'...")
        
        retrieved_context = memory.format_context_for_prompt(user_query)
        print("\n--- RETRIEVED CONTEXT FROM ECHOGRAPH ---")
        print(retrieved_context)
        print("----------------------------------------\n")
        
        # 4. Construct Final LLM Prompt
        system_prompt = f"""You are an intelligent AI assistant. Use the following retrieved user memories to personalize your answer:

<USER_MEMORY_CONTEXT>
{retrieved_context}
</USER_MEMORY_CONTEXT>
"""
        user_prompt = user_query
        
        print("💡 Final System Prompt sent to LLM:\n")
        print(system_prompt)
        print(f"User Message: {user_prompt}")
