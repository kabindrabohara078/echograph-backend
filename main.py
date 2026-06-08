import os
from typing import Literal
from datetime import datetime

from fastapi import (
    FastAPI,
    Depends
)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer

from pydantic import BaseModel, EmailStr

from database import conn
# from embedding import generate_embedding
# from model.search import retrieve_context

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

    score: float
    node_life: int


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

    if signup(user):
        return {
            "message": "User added successfully"
        }




# =========================================================
# LOGIN
# =========================================================
@app.post("/login")
def login_user(user: LoginUser):

    user_id = login(user)

    if user_id:

        access_token = create_access_token({
            "sub": user_id
        })
        return {
            "access_token": access_token,
            "token_type": "bearer"
        }



# =========================================================
# CREATE MEMORY
# =========================================================

# @app.post("/memory")
# def create_memory(
#     memory: MemoryInput,
#     current_user: str = Depends(get_current_user)
# ):

#     # =====================================================
#     # USER ID
#     # =====================================================

#     user_id = int(current_user)


#     print("+++++++++++++++++++++Memory json+++++++++++++++++++++++")
#     print(memory)

#     # =====================================================
#     # GENERATE EMBEDDING
#     # =====================================================

#     embedding = generate_embedding(
#         memory.context
#     )

#     cursor = conn.cursor()

#     # =====================================================
#     # DELETE MEMORY
#     # =====================================================

#     if memory.type == "delete":

#         print("Deleting memory...")

#         # DEBUG CLOSEST MATCHES
#         cursor.execute(
#         """
#         SELECT
#             ref_id,
#             content,
#             embedding <=> %s::vector AS distance

#         FROM memories_v2

#         WHERE
#             state = 'active'
#             AND user_id = %s

#         ORDER BY distance ASC

#         LIMIT 3
#         """,
#         (
#             embedding,
#             user_id
#         )
#         )

#         debug_rows = cursor.fetchall()

#         print("\n========== CLOSEST MEMORIES ==========")

#         for row in debug_rows:
#             print(row)

#         print("======================================\n")

#         # DELETE BEST MATCH
#         cursor.execute(
#         """
#         DELETE FROM memories_v2

#         WHERE ref_id = (

#             SELECT ref_id

#             FROM memories_v2

#             WHERE
#                 state = 'active'
#                 AND user_id = %s
#                 AND (
#                     embedding <=> %s::vector
#                 ) < 0.30

#             ORDER BY (
#                 embedding <=> %s::vector
#             ) ASC

#             LIMIT 1
#         )

#         RETURNING
#             ref_id,
#             content;
#         """,
#         (
#             user_id,
#             embedding,
#             embedding
#         )
#         )

#         deleted_memory = cursor.fetchone()

#         conn.commit()

#         if deleted_memory is None:

#             return {
#                 "status": "no matching memory found",
#                 "threshold": 0.30
#             }

#         return {
#             "status": "memory deleted",
#             "deleted_memory": {
#                 "ref_id": deleted_memory[0],
#                 "content": deleted_memory[1]
#             }
#         }

#     # =====================================================
#     # NORMAL MEMORY STORE
#     # =====================================================


#     if memory.type in ['fact', 'goal']:
#         modified_state = "permanent"
#     elif memory.type in ['preference', 'decision', 'relationship', 'profile', 'feedback']:
#         modified_state = "active"
#     else:
#         modified_state = "temporary"
    
#     node_life = 91
#     if modified_state == "temporary":
#         node_life = memory.node_life

    
#     cursor.execute(
#     """
#     INSERT INTO memories_v2 (

#         user_id,
#         content,
#         state,
#         type,
#         importance_score,
#         embedding,
#         initial_date,
#         node_life
#     )

#     VALUES (
#         %s,
#         %s,
#         %s,
#         %s,
#         %s,
#         %s,
#         %s,
#         %s
#     )
#     """,
#     (
#         user_id,
#         memory.context,
#         modified_state,
#         memory.type,
#         memory.score,
#         embedding,
#         datetime.utcnow(),
#         node_life
#     )
#     )

#     conn.commit()

#     return {
#         "status": "memory stored",
#         "user_id": user_id
#     }


# # =========================================================
# # SEARCH MEMORY
# # =========================================================
# @app.post("/search")
# def search_memory(
#     search: SearchInput,
#     current_user: str = Depends(get_current_user)):

#     retrieve_context(current_user, search)