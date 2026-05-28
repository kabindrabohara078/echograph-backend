from fastapi import FastAPI
from typing import Literal
from database import conn 
# from embedding import generate_embedding
from pydantic import BaseModel, EmailStr
from authentication import login
from authentication import signup


# react frontend support
from fastapi.middleware.cors import CORSMiddleware



app = FastAPI()


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



class MemoryInput(BaseModel):
    content: str

    type: str
    score: float = 1

class searchInput(BaseModel):
    query: str
    type: Literal["fact", "event", "preference", 'decision', 'task']
    importance_score: float

class newUser(BaseModel):
    firstname: str
    lastname: str
    email: EmailStr
    password: str

class LoginUser(BaseModel):
    email: EmailStr
    password: str


@app.post('/register')
def add_new_user(user: newUser):

    print("+++++++++++++++++++++++")
    print("Got a signup request")
    print("++++++++++++++++++++++++++")

    signup_response = signup(user)

    if signup_response:
        return "Already exists"


    return "Added successfully"

@app.post('/login')
def login_user(user: LoginUser):

    login_response = login(user)

    if login_response == -1:
        return "Does not exist"
    elif login_response == False:
        return "Invalid Credentials"
    else:
        return "Good to have you back"




# memmory layer incrementer function
# @app.post('/memory')
# def create_memory(memory: MemoryInput):
#     embedding = generate_embedding(memory.content)

#     cursor = conn.cursor()

#     cursor.execute(
#         """
#         INSERT INTO memories (
#         content,
#         state,
#         type,
#         score,
#         embedding
#         )
#         VALUES (%s, %s, %s, %s, %s)
#         """,
#         (
#             memory.content,
#             "active",
#             memory.type,
#             memory.score,
#             embedding
        
#         )
#     )

#     conn.commit()

#     return {
#         "status": "memory stored"
#     }



# # memmory layer extractor function
# @app.post("/search")
# def search_memory(search: searchInput):

#     data = search.model_dump()

#     print(data)
#     print(type(data))

#     query_embedding = generate_embedding(search.query)

#     cursor = conn.cursor()


#     # extractor module
#     cursor.execute(
#         """
#         SELECT 
#             id,
#             content, 
#             type,
#             score,
#             access_count,
#             created_at,
#             embedding <-> %s::vector AS distance,

#             (
#                 (1.0 / (1.0 + (embedding <-> %s::vector)))

#                 + (0.25 * score)

#                 + (0.1 * LN(1 + access_count))

#                 + (

#                     0.2 * EXP(
#                         -0.000001 * 
#                         EXTRACT (
#                             EPOCH FROM (
#                                         now() - created_at
#                                         )
#                                 )
#                                 )
#                   )

#             ) AS final_rank

#         FROM memories

#         WHERE state = 'active' 

#         ORDER BY final_rank DESC

#         LIMIT 5;
#         """,
#         (query_embedding, query_embedding)
#     )

#     results = cursor.fetchall()

#     memory_ids = [[row[0], row[6]] for row in results]

#     print(results)


#     # memory_ids = [x for x in memory_ids if x[1] >= 1]


#     # testing module
#     print('#############################################################')
#     print(memory_ids)
#     print('#############################################################')
#     print('#############################################################')


#     memory_ids = [x for x in memory_ids if x[1] <= 1]

#     print(memory_ids)
#     print('#############################################################')


#     memory_ids = [row[0] for row in memory_ids]


#     if memory_ids:
#         cursor.execute(
#             """
#             UPDATE memories
#             SET 
#                 access_count = access_count + 1,
#                 last_accessed = NOW()
#             WHERE id = ANY(%s)
#             """,
#             (memory_ids, )
#         )
#     conn.commit()

#     memories = []

#     for row in results:
#         if row[0] in memory_ids:
#             memories.append({
#                 "id": row[0],
#                 "content": row[1],
#                 "type": row[2],
#                 "score": row[3],
#                 "access_count": row[4],
#                 "created_at": row[5],
#                 "distance": row[6],
#                 "final_rank": row[7]
#             })

#     if len(memories) == 0:
#         return {
#             "results": "No memory available with high confidence!"
#         }


#     return {
#             "results": data
#         }