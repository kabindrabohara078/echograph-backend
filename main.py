from fastapi import FastAPI
from database import conn 
from embedding import generate_embedding
from pydantic import BaseModel

app = FastAPI()

class MemoryInput(BaseModel):
    content: str

class searchInput(BaseModel):
    query: str



@app.get('/')
def root():
    return ({'message':'EchoGraph API running'})

@app.post('/memory')
def create_memory(memory: MemoryInput):
    embedding = generate_embedding(memory.content)

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO memories (content, embedding)
        VALUES (%s, %s)
        """,
        (memory.content, embedding)
    )

    conn.commit()

    return {
        "status": "memory stored"
    }

@app.post('/search')
def search_memory(search: searchInput):
    query_embedding = generate_embedding(search.query)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, content, embedding <-> %s::vector AS distance FROM memories ORDER BY distance LIMIT 5;
        """,
        (query_embedding, )
    )

    results = cursor.fetchall()

    memories = []

    for row in results:
        memories.append({
            "id": row[0],
            "content": row[1],
            "distance": row[2]
        })

        return {
            "results": memories
        }