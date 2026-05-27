from fastapi import FastAPI
from database import conn 
from embedding import generate_embedding
from pydantic import BaseModel

app = FastAPI()

class MemoryInput(BaseModel):
    content: str

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
