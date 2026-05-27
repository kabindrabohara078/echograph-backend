from fastapi import FastAPI
from database import conn 
from embedding import generate_embedding
from pydantic import BaseModel

app = FastAPI()

class MemoryInput(BaseModel):
    content: str
    type: str
    score: float = 1

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
        INSERT INTO memories (
        content,
        state,
        type,
        score,
        embedding
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            memory.content,
            "active",
            memory.type,
            memory.score,
            embedding
        
        )
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
        SELECT 
            id,
            content, 
            type,
            score,
            access_count,
            created_at,
            embedding <-> %s::vector AS distance 
        FROM memories
        WHERE state = 'active' 
        ORDER BY distance 
        LIMIT 3;
        """,
        (query_embedding, )
    )

    results = cursor.fetchall()

    memory_ids = [[row[0], row[6]] for row in results]


    


    # memory_ids = [x for x in memory_ids if x[1] >= 1]

    print('#############################################################')
    print(memory_ids)
    print('#############################################################')
    print('#############################################################')


    memory_ids = [x for x in memory_ids if x[1] <= 1]

    print(memory_ids)
    print('#############################################################')



    # memory_ids = memory_ids[-1:1:-1]

    memory_ids = [row[0] for row in memory_ids]


    if memory_ids:
        cursor.execute(
            """
            UPDATE memories
            SET 
                access_count = access_count + 1,
                last_accessed = NOW()
            WHERE id = ANY(%s)
            """,
            (memory_ids, )
        )
    conn.commit()

    memories = []

    for row in results:
        if row[0] in memory_ids:
            memories.append({
                "id": row[0],
                "content": row[1],
                "type": row[2],
                "score": row[3],
                "access_count": row[4],
                "created_at": row[5],
                "distance": row[6]
            })

    if len(memories) == 0:
        return {
            "results": "No memory available with high confidence!"
        }

    return {
            "results": memories
        }