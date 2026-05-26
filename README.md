# EchoGraph

Hybrid memory architecture for AI systems.

EchoGraph combines structured event storage with semantic retrieval to build scalable long-term memory for LLMs, AI agents, and context-aware applications.

---

## Overview

Modern AI systems struggle with persistent memory, contextual continuity, and efficient retrieval of past interactions.

EchoGraph is designed to solve this by combining:

- Structured memory storage
- Semantic vector retrieval
- Context-aware memory linking
- Hybrid search pipelines
- Long-term conversational memory

The system stores precise factual events while using embeddings to retrieve semantically related context.

---

## Core Idea

EchoGraph separates memory into two layers:

### Structured Memory
Stores exact information and metadata.

Examples:
- Events
- Decisions
- User actions
- Timestamps
- Relationships
- Tags

### Semantic Memory
Uses embeddings to retrieve related memories based on meaning rather than exact wording.

This hybrid architecture enables:
- Accurate retrieval
- Context continuity
- Related memory expansion
- Better reasoning for AI systems

---

## Features

- Hybrid structured + semantic memory
- Vector similarity search
- Metadata filtering
- Long-term context retrieval
- Memory relationship graphs
- Scalable retrieval pipeline
- AI-agent compatible architecture
- PostgreSQL + pgvector support
- Modular backend design

---

## Planned Architecture

```text
User Input
    ↓
Event Extraction
    ↓
Structured Storage (PostgreSQL)
    ↓
Embedding Generation
    ↓
Vector Storage (pgvector)
    ↓
Hybrid Retrieval Engine
    ↓
Context Builder
    ↓
LLM / Agent Response
```

---

## Tech Stack

### Backend
- Node.js
- TypeScript

### Database
- PostgreSQL
- pgvector

### API
- FastAPI

### Embeddings
- OpenAI Embeddings (planned)
- sentence-transformers (planned)

---

## Use Cases

- AI assistants
- Long-term conversational agents
- Memory systems for LLMs
- Semantic search systems
- Context-aware applications
- Agent orchestration platforms

---

## Project Goals

- Build scalable AI memory infrastructure
- Improve contextual retrieval quality
- Combine exact factual storage with semantic understanding
- Create reusable memory tooling for AI systems

---

## Status

Currently in active development.

---

## Vision

EchoGraph aims to become a flexible memory layer for intelligent systems by combining structured knowledge with semantic understanding.

---

## License

MIT License
