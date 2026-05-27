CREATE TABLE memories_v2 (
    id SERIAL PRIMARY KEY,

    content TEXT NOT NULL,

    state TEXT NOT NULL DEFAULT 'active'
    CHECK 
    (
        state IN (
            'active',
            'archived',
            'deleted'
        ) 
    ),

    type TEXT NOT NULL CHECK (
        type IN (
            'fact',
            'event',
            'preference',
            'decision',
            'task'
        )
    ),

    importance_score FLOAT NOT NULL DEFAULT 1 CHECK (
        importance_score >= 0 AND importance_score <= 1
    ),

    access_count INTEGER NOT NULL DEFAULT 0,

    embedding VECTOR(384) NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    last_accessed TIMESTAMP NOT NULL DEFAULT NOW(),

    linkable BOOLEAN NOT NULL DEFAULT FALSE,

    ref_link INTEGER REFERENCES memories(id),

    expires_at TIMESTAMP
);