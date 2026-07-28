import os
from typing import Literal, Optional
from datetime import datetime

from fastapi import (
    FastAPI,
    Depends,
    HTTPException
)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer

from pydantic import BaseModel, EmailStr
from jose import jwt

from database import conn
from embedding import generate_embedding
from model.search import retrieve_context

from authentication import login, signup, google_auth_user

from hash_password import (
    create_access_token,
    decode_token
)


app = FastAPI(title="EchoGraph RAG Memory API")


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# AUTH
# =========================================================

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="login"
)


def get_current_user(
    token: str = Depends(oauth2_scheme)):

    user_id = decode_token(token)

    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    return user_id



# =========================================================
# MODELS
# =========================================================

class MemoryInput(BaseModel):
    context: str
    type: Literal[
        "fact",
        "event",
        "preference",
        "decision",
        "task",
        "goal",
        "relationship",
        "profile",
        "conversation",
        "observation",
        "knowledge",
        "plan",
        "reminder",
        "feedback",
        "emotion",
        "delete"
    ]
    score: float = 1.0
    node_life: int = 91


class SearchInput(BaseModel):
    query: str
    type: Optional[str] = "fact"


class NewUser(BaseModel):
    firstname: str
    lastname: str
    email: EmailStr
    password: str


class LoginUser(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthInput(BaseModel):
    credential: str


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():
    return {
        "message": "EchoGraph API Running"
    }

# =========================================================
# REGISTER
# =========================================================
@app.post("/register")
def add_new_user(user: NewUser):
    if signup(user):
        return {
            "message": "User added successfully"
        }

# =========================================================
# LOGIN
# =========================================================
@app.post("/login")
def login_user(user: LoginUser):
    res = login(user)
    if res:
        access_token = create_access_token({
            "sub": res["user_id"]
        })
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "name": res["name"],
            "email": res["email"]
        }

# =========================================================
# GOOGLE AUTH
# =========================================================
@app.post("/google-auth")
def google_auth(payload: GoogleAuthInput):
    try:
        claims = jwt.get_unverified_claims(payload.credential)
        email = claims.get("email")
        name = claims.get("name", "")

        if not email:
            raise HTTPException(status_code=400, detail="Invalid Google token claims: missing email")

        user_id, user_name = google_auth_user(email, name)
        access_token = create_access_token({"sub": user_id})

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "email": email,
            "name": user_name
        }
    except Exception as e:
        print("Google auth exception:", e)
        raise HTTPException(status_code=400, detail=f"Google authentication failed: {str(e)}")

# =========================================================
# CREATE MEMORY
# =========================================================
@app.post("/memory")
def create_memory(
    memory: MemoryInput,
    current_user: str = Depends(get_current_user)
):
    user_id = int(current_user)
    print("+++++++++++++++++++++ Memory Input +++++++++++++++++++++++")
    print(memory)

    embedding = generate_embedding(memory.context)
    vector_str = f"[{','.join(map(str, embedding))}]"

    cursor = conn.cursor()

    if memory.type == "delete":
        print("Deleting memory...")
        cursor.execute(
            """
            DELETE FROM memories_v2
            WHERE ref_id = (
                SELECT ref_id
                FROM memories_v2
                WHERE
                    state IN ('active', 'permanent', 'temporary')
                    AND user_id = %s
                    AND (embedding <=> %s::vector) < 0.30
                ORDER BY (embedding <=> %s::vector) ASC
                LIMIT 1
            )
            RETURNING ref_id, content;
            """,
            (user_id, vector_str, vector_str)
        )
        deleted_memory = cursor.fetchone()
        conn.commit()

        if deleted_memory is None:
            return {
                "status": "no matching memory found",
                "threshold": 0.30
            }

        return {
            "status": "memory deleted",
            "deleted_memory": {
                "ref_id": deleted_memory[0],
                "content": deleted_memory[1]
            }
        }

    # Normal Memory Store
    if memory.type in ['fact', 'goal']:
        modified_state = "permanent"
    elif memory.type in ['preference', 'decision', 'relationship', 'profile', 'feedback']:
        modified_state = "active"
    else:
        modified_state = "temporary"

    node_life = 91
    if modified_state == "temporary":
        node_life = memory.node_life

    cursor.execute(
        """
        INSERT INTO memories_v2 (
            user_id,
            content,
            state,
            type,
            importance_score,
            embedding,
            initial_date,
            node_life
        )
        VALUES (
            %s, %s, %s, %s, %s, %s::vector, %s, %s
        )
        """,
        (
            user_id,
            memory.context,
            modified_state,
            memory.type,
            memory.score,
            vector_str,
            datetime.utcnow(),
            node_life
        )
    )

    conn.commit()

    return {
        "status": "memory stored",
        "user_id": user_id
    }

class ChatInput(BaseModel):
    message: str

# =========================================================
# SEARCH MEMORY
# =========================================================
@app.post("/search")
def search_memory(
    search: SearchInput,
    current_user: str = Depends(get_current_user)
):
    return retrieve_context(current_user, search)

# =========================================================
# HYBRID AI CHAT AGENT (AUTO-RETRIEVE + AUTO-STORE)
# =========================================================
@app.post("/chat")
def chat_agent(
    payload: ChatInput,
    current_user: str = Depends(get_current_user)
):
    user_id = int(current_user)
    user_msg = payload.message.strip()

    # 1. RETRIEVE: Auto-fetch relevant user context
    search_obj = SearchInput(query=user_msg)
    retrieval_res = retrieve_context(current_user, search_obj)
    memories = retrieval_res.get("results", [])

    # 2. AUTO-STORE: If message contains statement/fact (not a direct query), auto-store to memory
    stored = False
    if len(user_msg) > 12 and not user_msg.rstrip().endswith("?"):
        embedding = generate_embedding(user_msg)
        vector_str = f"[{','.join(map(str, embedding))}]"
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO memories_v2 (user_id, content, type, state, importance_score, access_ratio, embedding, node_life)
            VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s)
            """,
            (user_id, user_msg, "fact", "active", 1.0, 0.1, vector_str, 91)
        )
        conn.commit()
        stored = True

    # 3. GENERATE AGENT RESPONSE
    if memories:
        top_facts = [f"• {m['content']}" for m in memories[:3]]
        context_str = "\n".join(top_facts)
        reply = f"Here is what I recalled from your EchoGraph persistent memory:\n{context_str}\n\nHow can I assist you with this context?"
    else:
        reply = f"I've saved your statement into your EchoGraph memory bank! You can ask me questions about it anytime."

    return {
        "reply": reply,
        "memories_retrieved": memories,
        "new_memory_stored": stored,
        "user_id": user_id
    }