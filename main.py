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
    "http://localhost:5173",
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

    email = decode_token(token)

    if email is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    return email


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
        "emotion"
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
    importance_score: float


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

    print("+++++++++++++++++++++++")
    print("Got a signup request")
    print("+++++++++++++++++++++++")

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

    # =====================================================
    # GET USER ID
    # =====================================================

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

    # =====================================================
    # CREATE TOKEN WITH USER ID
    # =====================================================

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
    # CURRENT USER IS USER ID FROM TOKEN
    # =====================================================

    user_id = int(current_user)

    embedding = generate_embedding(
        memory.context
    )

    cursor = conn.cursor()

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
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """,
    (
        user_id,
        memory.context,
        "active",
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
            id,
            content,
            type,
            importance_score,
            access_count,
            created_at,

            embedding <-> %s::vector AS distance,

            (
                (
                    1.0 /
                    (
                        1.0 +
                        (
                            embedding <-> %s::vector
                        )
                    )
                )

                + (0.25 * importance_score)

                + (
                    0.1 *
                    LN(1 + access_count)
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

    # =====================================================
    # FILTER DISTANCE
    # =====================================================

    memory_ids = [
        row[0]
        for row in results
        if row[6] <= 1
    ]

    # =====================================================
    # UPDATE ACCESS COUNT
    # =====================================================

    # if memory_ids:

    #     cursor.execute(
    #         """
    #         UPDATE memories_v2
    #         SET
    #             access_count = access_count + 1,
    #             last_accessed = NOW()
    #         WHERE id = ANY(%s)
    #         """,
    #         (memory_ids,)
    #     )

    #     conn.commit()

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
                "access_count": row[4],
                "created_at": row[5],
                "distance": row[6],
                "final_rank": row[7]
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