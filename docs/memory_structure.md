# EchoGraph Memory Structure

## Overview

EchoGraph is a semantic memory system that stores, retrieves, and ranks memories using embeddings + structured metadata.

It is designed to behave like an adaptive long-term memory for AI systems.

---

# Core Concept

Each memory is:

* A piece of text (content)
* Converted into a vector (embedding)
* Stored with metadata
* Ranked dynamically during retrieval

---

# Memory Table Schema

## memories

```sql
CREATE TABLE memories (
    id SERIAL PRIMARY KEY,

    user_id INTEGER REFERENCES users(id),

    content TEXT NOT NULL,

    state TEXT NOT NULL CHECK (
        state IN ('active', 'archived', 'deleted')
    ),

    type TEXT NOT NULL CHECK (
        type IN ('fact', 'event', 'preference', 'decision', 'task')
    ),

    score FLOAT NOT NULL DEFAULT 1 CHECK (
        score >= 0 AND score <= 1
    ),

    access_count INTEGER NOT NULL DEFAULT 0,

    embedding VECTOR(384) NOT NULL,

    created_at TIMESTAMP DEFAULT NOW(),

    updated_at TIMESTAMP DEFAULT NOW(),

    last_accessed TIMESTAMP DEFAULT NOW(),

    expires_at TIMESTAMP
);
```

---

# Field Explanations

## id

Unique identifier for each memory.

---

## user_id

Links memory to a specific user.

Enables multi-user isolation.

---

## content

Raw memory text.

Example:

```
User switched from MongoDB to PostgreSQL
```

---

## state

Memory lifecycle state.

* active → usable memory
* archived → low priority memory
* deleted → logically removed

---

## type

Memory category.

* fact → stable knowledge
* event → happened in time
* preference → user likes/dislikes
* decision → explicit choices
* task → actionable item

---

## score

Importance value (0 to 1).

Used in ranking.

---

## access_count

Number of times memory was retrieved.

Represents usefulness.

---

## embedding

Vector representation of content.

Used for semantic search.

---

## created_at

When memory was created.

---

## updated_at

Last modification time.

---

## last_accessed

Last time memory was retrieved.

Used for recency scoring.

---

## expires_at

Optional expiration time for temporary memories.

---

# Retrieval System

EchoGraph uses hybrid ranking:

## Signals used

1. Semantic similarity (vector distance)
2. Importance score
3. Access frequency
4. Recency decay

---

# Final Ranking Formula

```text
final_score =
(1 / (1 + distance))
+ (0.25 * score)
+ (0.1 * log(1 + access_count))
+ (0.2 * exp(-λ * age))
```

Higher score = better memory match.

---

# Memory Lifecycle

## Insert

* embed text
* store vector + metadata

## Retrieve

* compute similarity
* apply ranking formula
* return top results

## Reinforcement

On access:

* increase access_count
* update last_accessed

## Decay

Over time:

* old memories lose ranking strength
* unless reinforced

---

# System Behavior

EchoGraph behaves like:

* long-term memory
* adaptive recall system
* semantic knowledge base

NOT just a database.

---

# Future Extensions

## Graph Memory

* memory relationships
* linked events
* causal chains

## AI Layer

* LLM-based memory extraction
* summarization
* compression

## Hybrid Memory

* local + cloud memory split

---

# Summary

EchoGraph =

Semantic Embeddings + Structured Metadata + Dynamic Ranking + Memory Lifecycle Management