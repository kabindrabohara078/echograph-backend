# 🧠 EchoGraph Backend

EchoGraph is an AI memory system built using FastAPI, PostgreSQL, and pgvector. It stores, retrieves, and ranks memories using semantic embeddings combined with structured metadata and adaptive scoring.

It acts as a long-term memory layer for AI systems.

---

# 🚀 Overview

EchoGraph enables:

- Storing structured memories
- Semantic search using embeddings
- Hybrid ranking (similarity + metadata signals)
- Memory lifecycle management
- Multi-user support via user_id

---

# 🧱 Tech Stack

- FastAPI
- PostgreSQL
- pgvector
- sentence-transformers
- Python

---

# 🗄️ Memory Schema (Core Table)

Each memory contains:

- id → unique identifier
- user_id → owner of memory
- content → memory text
- type → fact | event | preference | decision | task
- state → active | archived | deleted
- score → importance (0–1)
- access_count → usage frequency
- embedding → vector representation
- created_at → creation time
- updated_at → last update
- last_accessed → last retrieval
- expires_at → optional expiry

---

# 🔌 API Endpoints

## POST /memory

Stores a new memory.

### Request

```json
{
  "content": "User switched from MongoDB to PostgreSQL",
  "type": "decision",
  "score": 0.9
}
```

### Response

```json
{
  "message": "Memory stored successfully"
}
```

---

## POST /search

Search memories using semantic + ranking system.

### Request

```json
{
  "query": "What database does the user prefer?"
}
```

### Response

```json
[
  {
    "content": "User switched from MongoDB to PostgreSQL",
    "score": 0.92
  }
]
```

---

# 🧠 Ranking System

```text
final_score =
(1 / (1 + vector_distance))
+ (0.25 × score)
+ (0.1 × log(1 + access_count))
+ (0.2 × exp(-λ × age))
```

---

# ⚙️ Setup Instructions

Install dependencies:

```bash
pip install -r requirements.txt
```

Enable pgvector:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Run server:

```bash
uvicorn main:app --reload
```

Default local backend:

```text
http://localhost:8000
```

Swagger docs:

```text
http://localhost:8000/docs
```

---

# 🌍 Environment Variables

```env
DATABASE_URL=postgresql://user:password@localhost:5432/echograph
```

---

# 📈 Project Status

MVP completed.

Current capabilities:

- semantic memory storage
- vector similarity retrieval
- adaptive ranking system
- memory lifecycle management
- FastAPI + PostgreSQL + pgvector architecture

EchoGraph is currently evolving into a full AI memory platform.
