import os
from typing import Literal
from datetime import datetime

from fastapi import (
    FastAPI,
    HTTPException,
    Depends
)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer

from pydantic import BaseModel, EmailStr

from database import conn
from embedding import generate_embedding

from authentication import login, signup

from hash_password import (
    create_access_token,
    decode_token
)


app = FastAPI()


# =========================================================
# CORS
# =========================================================

origins = [
    "http://localhost:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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
    token: str = Depends(oauth2_scheme)
):

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

    score: float = 1


class SearchInput(BaseModel):

    query: str

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
        "emotion"
    ]


class NewUser(BaseModel):
    firstname: str
    lastname: str
    email: EmailStr
    password: str


class LoginUser(BaseModel):
    email: EmailStr
    password: str


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

    signup_response = signup(user)

    if signup_response:

        raise HTTPException(
            status_code=409,
            detail="User already exists"
        )

    return {
        "message": "User added successfully"
    }


# =========================================================
# LOGIN
# =========================================================

@app.post("/login")
def login_user(user: LoginUser):

    login_response = login(user)

    if login_response == -1:

        raise HTTPException(
            status_code=404,
            detail="User does not exist"
        )

    elif login_response is False:

        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id
        FROM users
        WHERE email = %s
        """,
        (user.email,)
    )

    db_user = cursor.fetchone()

    if db_user is None:

        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    user_id = db_user[0]

    access_token = create_access_token({
        "sub": str(user_id)
    })

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


# =========================================================
# CREATE MEMORY
# =========================================================

@app.post("/memory")
def create_memory(
    memory: MemoryInput,
    current_user: str = Depends(get_current_user)
):

    # =====================================================
    # USER ID
    # =====================================================

    user_id = int(current_user)

    # =====================================================
    # GENERATE EMBEDDING
    # =====================================================

    embedding = generate_embedding(
        memory.context
    )

    cursor = conn.cursor()

    # =====================================================
    # DELETE MEMORY
    # =====================================================

    if memory.type == "delete":

        print("Deleting memory...")

        # DEBUG CLOSEST MATCHES
        cursor.execute(
        """
        SELECT
            ref_id,
            content,
            embedding <=> %s::vector AS distance

        FROM memories_v2

        WHERE
            state = 'active'
            AND user_id = %s

        ORDER BY distance ASC

        LIMIT 5
        """,
        (
            embedding,
            user_id
        )
        )

        debug_rows = cursor.fetchall()

        print("\n========== CLOSEST MEMORIES ==========")

        for row in debug_rows:
            print(row)

        print("======================================\n")

        # DELETE BEST MATCH
        cursor.execute(
        """
        DELETE FROM memories_v2

        WHERE ref_id = (

            SELECT ref_id

            FROM memories_v2

            WHERE
                state = 'active'
                AND user_id = %s
                AND (
                    embedding <=> %s::vector
                ) < 0.35

            ORDER BY (
                embedding <=> %s::vector
            ) ASC

            LIMIT 1
        )

        RETURNING
            ref_id,
            content;
        """,
        (
            user_id,
            embedding,
            embedding
        )
        )

        deleted_memory = cursor.fetchone()

        conn.commit()

        if deleted_memory is None:

            return {
                "status": "no matching memory found",
                "threshold": 0.35
            }

        return {
            "status": "memory deleted",
            "deleted_memory": {
                "ref_id": deleted_memory[0],
                "content": deleted_memory[1]
            }
        }

    # =====================================================
    # NORMAL MEMORY STORE
    # =====================================================

    modified_state = "active"

    cursor.execute(
    """
    INSERT INTO memories_v2 (

        user_id,
        content,
        state,
        type,
        importance_score,
        embedding,
        created_at,
        access_ratio

    )

    VALUES (
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s
    )
    """,
    (
        user_id,
        memory.context,
        modified_state,
        memory.type,
        memory.score,
        embedding,
        datetime.utcnow(),
        0
    )
    )

    conn.commit()

    return {
        "status": "memory stored",
        "user_id": user_id
    }


# =========================================================
# SEARCH MEMORY
# =========================================================

@app.post("/search")
def search_memory(
    search: SearchInput,
    current_user: str = Depends(get_current_user)
):

    user_id = int(current_user)

    query_embedding = generate_embedding(
        search.query
    )

    cursor = conn.cursor()

    cursor.execute(
    """
    SELECT

        ref_id,
        content,
        type,
        importance_score,
        access_ratio,
        created_at,

        embedding <=> %s::vector AS distance,

        (
            (
                1.0 /
                (
                    1.0 +
                    (
                        embedding <=> %s::vector
                    )
                )
            )

            + (0.25 * importance_score)

            + (
                0.1 *
                LN(1 + access_ratio)
            )

            + (
                0.2 *
                EXP(
                    -0.000001 *
                    EXTRACT(
                        EPOCH FROM (
                            NOW() - created_at
                        )
                    )
                )
            )

        ) AS final_rank

    FROM memories_v2

    WHERE
        state = 'active'
        AND user_id = %s

    ORDER BY final_rank DESC

    LIMIT 5
    """,
    (
        query_embedding,
        query_embedding,
        user_id
    )
    )

    results = cursor.fetchall()

    print("\n=========== SEARCH RESULTS ===========")

    for row in results:
        print(row)

    print("======================================\n")

    # =====================================================
    # FILTER DISTANCE
    # =====================================================

    memory_ids = [
        row[0]
        for row in results
        if row[6] < 0.5
    ]

    # =====================================================
    # UPDATE ACCESS RATIO
    # =====================================================

    if memory_ids:

        cursor.execute(
        """
        UPDATE memories_v2

        SET
            access_ratio = access_ratio + 1,
            last_accessed = NOW()

        WHERE ref_id = ANY(%s)
        """,
        (memory_ids,)
        )

        conn.commit()

    # =====================================================
    # FORMAT RESULTS
    # =====================================================

    memories = []

    for row in results:

        if row[0] in memory_ids:

            memories.append({

                "id": row[0],
                "content": row[1],
                "type": row[2],
                "importance_score": row[3],
                "access_ratio": row[4],
                "created_at": row[5],
                "distance": float(row[6]),
                "final_rank": float(row[7])

            })

    # =====================================================
    # NO RESULTS
    # =====================================================

    if len(memories) == 0:

        return {
            "results": [],
            "message": "No memory available with high confidence"
        }

    # =====================================================
    # SUCCESS
    # =====================================================

    return {
        "results": memories,
        "count": len(memories),
        "user_id": user_id
    }