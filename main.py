import os
import asyncio
from typing import Literal, Optional
from datetime import datetime, timedelta

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
from model.graph import auto_link_memory, extract_entities

from authentication import login, signup, google_auth_user

from hash_password import (
    create_access_token,
    decode_token,
    verify_password,
    hash_password
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
    node_life: Optional[int] = None
    lifespan_unit: Optional[str] = None # 'hours', 'days', 'weeks', 'months', 'years', 'permanent'
    lifespan_value: Optional[int] = None # numerical amount
    is_permanent: Optional[bool] = False
    ref_id: Optional[int] = None # for explicit deletion by ID
    linkable: Optional[bool] = True
    ref_link: Optional[int] = None


class SearchInput(BaseModel):
    query: str
    type: Optional[str] = None
    threshold: Optional[float] = None
    limit: Optional[int] = None


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


class UpdateProfileInput(BaseModel):
    name: Optional[str] = None
    fname: Optional[str] = None
    lname: Optional[str] = None


class ChangePasswordInput(BaseModel):
    current_password: str
    new_password: str


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():
    return {
        "message": "EchoGraph API Running"
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "EchoGraph Backend"
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
# PROFILE & ACCOUNT MANAGEMENT
# =========================================================
@app.get("/profile")
def get_user_profile(current_user: str = Depends(get_current_user)):
    user_id = int(current_user)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT u.id, u.fname, u.lname, u.email, u.display_name,
               (SELECT count(*) FROM memories_v2 WHERE user_id = u.id) as memory_count
        FROM users u
        WHERE u.id = %s
        """,
        (user_id,)
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    display_name = row[4] or f"{row[1]} {row[2]}".strip() or row[3].split('@')[0]
    return {
        "id": row[0],
        "fname": row[1],
        "lname": row[2],
        "email": row[3],
        "name": display_name,
        "memory_count": row[5] or 0
    }

@app.put("/profile")
def update_user_profile(
    payload: UpdateProfileInput,
    current_user: str = Depends(get_current_user)
):
    user_id = int(current_user)
    cursor = conn.cursor()

    fname = payload.fname or ""
    lname = payload.lname or ""
    display_name = payload.name

    if payload.name and not (payload.fname or payload.lname):
        parts = payload.name.strip().split(" ", 1)
        fname = parts[0]
        lname = parts[1] if len(parts) > 1 else ""
    elif not payload.name and (payload.fname or payload.lname):
        display_name = f"{fname} {lname}".strip()

    cursor.execute(
        """
        UPDATE users
        SET fname = %s, lname = %s, display_name = %s, updated_at = NOW()
        WHERE id = %s
        """,
        (fname, lname, display_name, user_id)
    )
    conn.commit()

    return {
        "status": "profile updated",
        "name": display_name or f"{fname} {lname}".strip(),
        "user_id": user_id
    }

@app.post("/change-password")
def change_user_password(
    payload: ChangePasswordInput,
    current_user: str = Depends(get_current_user)
):
    user_id = int(current_user)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT password_hash FROM user_auth WHERE user_id = %s
        """,
        (user_id,)
    )
    row = cursor.fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="User authentication record not found")

    if not verify_password(payload.current_password, row[0]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    new_hash = hash_password(payload.new_password)
    cursor.execute(
        """
        UPDATE user_auth
        SET password_hash = %s, updated_at = NOW()
        WHERE user_id = %s
        """,
        (new_hash, user_id)
    )
    conn.commit()

    return {
        "status": "password updated",
        "message": "Password updated successfully"
    }

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
        if memory.ref_id:
            cursor.execute(
                """
                DELETE FROM memories_v2
                WHERE user_id = %s AND ref_id = %s
                RETURNING ref_id, content;
                """,
                (user_id, memory.ref_id)
            )
            deleted_memory = cursor.fetchone()
        else:
            cursor.execute(
                """
                DELETE FROM memories_v2
                WHERE ref_id = (
                    SELECT ref_id
                    FROM memories_v2
                    WHERE
                        user_id = %s
                        AND (embedding <=> %s::vector) < 0.40
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
                "threshold": 0.40
            }

        return {
            "status": "memory deleted",
            "deleted_memory": {
                "ref_id": deleted_memory[0],
                "content": deleted_memory[1]
            }
        }

    # Determine Lifespan & State
    now_dt = datetime.utcnow()
    is_perm = (
        memory.is_permanent is True
        or (memory.lifespan_unit and memory.lifespan_unit.lower() == "permanent")
        or memory.node_life == -1
    )

    if is_perm:
        modified_state = "permanent"
        final_node_life = None
        expires_at = None
    else:
        # Calculate total hours based on unit and value
        unit = (memory.lifespan_unit or "days").lower().strip()
        val = memory.lifespan_value if memory.lifespan_value is not None else (memory.node_life or 91)
        try:
            val = int(val)
        except Exception:
            val = 91

        if unit in ["hour", "hours", "h"]:
            total_hours = max(1, val)
        elif unit in ["day", "days", "d"]:
            total_hours = max(1, val * 24)
        elif unit in ["week", "weeks", "w"]:
            total_hours = max(1, val * 7 * 24)
        elif unit in ["month", "months", "m"]:
            total_hours = max(1, val * 30 * 24)
        elif unit in ["year", "years", "y"]:
            total_hours = max(1, val * 365 * 24)
        else:
            total_hours = max(1, val * 24)

        modified_state = "active"
        final_node_life = total_hours
        expires_at = now_dt + timedelta(hours=total_hours)

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
            node_life,
            expires_at,
            linkable,
            ref_link
        )
        VALUES (
            %s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s, %s
        )
        RETURNING ref_id;
        """,
        (
            user_id,
            memory.context,
            modified_state,
            memory.type,
            memory.score,
            vector_str,
            now_dt,
            final_node_life,
            expires_at,
            1 if memory.linkable is not False else 0,
            memory.ref_link
        )
    )
    inserted_row = cursor.fetchone()
    new_ref_id = inserted_row[0] if inserted_row else cursor.lastrowid

    # Dynamic Memory Knowledge Graph Linking
    created_links = auto_link_memory(
        cursor=cursor,
        new_ref_id=new_ref_id,
        user_id=user_id,
        content=memory.context,
        embedding=embedding,
        linkable=(memory.linkable is not False)
    )
    conn.commit()

    return {
        "status": "memory stored",
        "user_id": user_id,
        "ref_id": new_ref_id,
        "content": memory.context,
        "type": memory.type,
        "importance": memory.score,
        "state": modified_state,
        "node_life": final_node_life,
        "expires_at": str(expires_at) if expires_at else None,
        "is_permanent": is_perm,
        "linkable": memory.linkable is not False,
        "linked_nodes_count": len(created_links),
        "linked_nodes": created_links
    }

# =========================================================
# REAL-TIME LIFESPAN CLEANUP ENGINE (60s Interval)
# =========================================================

def run_hourly_cleanup():
    """
    Automated lifespan cleanup engine:
    1. Normalizes permanent memories (ensures state='permanent', node_life=NULL).
    2. Identifies and removes memories whose lifespan or expires_at timestamp has passed.
    3. Updates remaining node_life hours for active temporary memories to match real elapsed time.
    Permanent memories are never deleted.
    """
    try:
        now_dt = datetime.utcnow()
        cursor = conn.cursor()

        # Step 1: Normalize permanent memories so node_life is never stored as confusing negative -1
        cursor.execute(
            """
            UPDATE memories_v2
            SET node_life = NULL,
                state = 'permanent'
            WHERE state = 'permanent' OR node_life = -1
            """
        )

        # Step 2: Fetch non-permanent candidates to check actual real-time expiration
        cursor.execute(
            """
            SELECT ref_id, node_life, initial_date, expires_at
            FROM memories_v2
            WHERE state != 'permanent' AND node_life IS NOT NULL
            """
        )
        candidates = cursor.fetchall()
        expired_ids = []
        updates = []

        for ref_id, node_life, init_date, exp_at in candidates:
            # Check if expires_at has passed
            if exp_at:
                try:
                    exp_dt = exp_at if isinstance(exp_at, datetime) else datetime.fromisoformat(str(exp_at))
                    if now_dt >= exp_dt:
                        expired_ids.append(ref_id)
                        continue
                    else:
                        rem_hours = max(1, int((exp_dt - now_dt).total_seconds() / 3600))
                        if rem_hours != node_life:
                            updates.append((rem_hours, ref_id))
                        continue
                except Exception:
                    pass

            # Check if initial_date + node_life has passed
            if init_date and node_life is not None:
                try:
                    init_dt = init_date if isinstance(init_date, datetime) else datetime.fromisoformat(str(init_date))
                    elapsed_hours = (now_dt - init_dt).total_seconds() / 3600
                    if node_life <= 0 or elapsed_hours >= node_life:
                        expired_ids.append(ref_id)
                        continue
                    else:
                        rem_hours = max(1, int(node_life - elapsed_hours))
                        if rem_hours != node_life:
                            updates.append((rem_hours, ref_id))
                except Exception:
                    pass

            if node_life is not None and node_life <= 0:
                expired_ids.append(ref_id)

        # Step 3: Delete expired memories
        if expired_ids:
            cursor.execute(
                """
                DELETE FROM memories_v2
                WHERE ref_id = ANY(%s)
                """,
                (expired_ids,)
            )

        # Purge any soft-deleted or marked expired memories
        cursor.execute(
            """
            DELETE FROM memories_v2
            WHERE type = 'delete' OR state IN ('deleted', 'expired')
            """
        )

        # Step 4: Update remaining hours for active nodes
        for rem_hours, ref_id in updates:
            cursor.execute(
                """
                UPDATE memories_v2
                SET node_life = %s, updated_at = %s
                WHERE ref_id = %s
                """,
                (rem_hours, now_dt, ref_id)
            )

        conn.commit()
        if expired_ids:
            print(f"[CLEANUP] Automatically removed {len(expired_ids)} expired memories.")
    except Exception as e:
        print("[CLEANUP ERROR]:", e)
        try:
            conn.rollback()
        except Exception:
            pass

cleanup_task_handle = None

async def hourly_cleanup_loop():
    """Periodically scans and self-cleans expired memories every 60 seconds."""
    while True:
        try:
            await asyncio.sleep(60)  # Check every 60 seconds (1 minute)
            run_hourly_cleanup()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print("Exception in cleanup loop:", e)
            await asyncio.sleep(10)

@app.on_event("startup")
async def startup_event():
    global cleanup_task_handle
    # Run once on startup so stale/expired nodes are cleaned immediately
    run_hourly_cleanup()
    cleanup_task_handle = asyncio.create_task(hourly_cleanup_loop())
    print("[STARTUP] Real-time memory lifespan scanner running (60s interval).")

@app.on_event("shutdown")
async def shutdown_event():
    global cleanup_task_handle
    if cleanup_task_handle:
        cleanup_task_handle.cancel()
        print("[SHUTDOWN] Memory lifespan scanner stopped.")

@app.post("/memory/cleanup")
def trigger_manual_cleanup(current_user: str = Depends(get_current_user)):
    """
    Manually triggers the 1-hour lifespan refresh scan:
    Decrements active lifespans by 1 hour and deletes expired records.
    """
    run_hourly_cleanup()
    return {
        "status": "success",
        "message": "Hourly lifespan refresh executed: 1 hour deducted and expired memories purged."
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
        now_dt = datetime.utcnow()
        hours_91_days = 91 * 24
        expires_at = now_dt + timedelta(hours=hours_91_days)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO memories_v2 (user_id, content, type, state, importance_score, access_ratio, embedding, node_life, expires_at, linkable)
            VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s, 1)
            RETURNING ref_id;
            """,
            (user_id, user_msg, "fact", "active", 1.0, 0.1, vector_str, hours_91_days, expires_at)
        )
        inserted = cursor.fetchone()
        new_ref_id = inserted[0] if inserted else cursor.lastrowid
        auto_link_memory(cursor, new_ref_id, user_id, user_msg, embedding, linkable=True)
        conn.commit()
        stored = True

    # 3. GENERATE AGENT RESPONSE (Present all relevant memories and linked graph nodes)
    if memories:
        top_facts = []
        for m in memories:
            rank_str = f" [Rank: {m['final_rank']:.2f}]" if m.get("final_rank") is not None else ""
            line = f"• [{m.get('type', 'fact').upper()}]{rank_str} {m['content']}"
            if m.get("linked_memories"):
                for lm in m["linked_memories"]:
                    rel = lm.get("relation", "connected")
                    line += f"\n  ↳ [CONNECTED GRAPH CONTEXT ({rel})]: {lm['content']}"
            top_facts.append(line)
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"[SERVER] Starting EchoGraph Backend on http://0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)