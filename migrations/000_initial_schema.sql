CREATE TABLE memories_v2 (

    ref_id BIGSERIAL PRIMARY KEY,

    user_id INTEGER NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE,

    content TEXT NOT NULL,

    state TEXT NOT NULL DEFAULT 'active'
    CHECK (
        state IN (
            'active',
            'archived',
            'deleted'
        )
    ),

    type TEXT NOT NULL
    CHECK (
        type IN (
            'fact',
            'event',
            'preference',
            'decision',
            'task',
            'goal',
            'relationship',
            'profile',
            'conversation',
            'observation',
            'knowledge',
            'plan',
            'reminder',
            'feedback',
            'emotion'
        )
    ),

    importance_score FLOAT NOT NULL DEFAULT 1
    CHECK (
        importance_score >= 0
        AND importance_score <= 1
    ),

    access_ratio NUMERIC(20,3)
    NOT NULL DEFAULT 0.1,

    embedding VECTOR(384)
    NOT NULL,

    created_at TIMESTAMP
    NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMP
    NOT NULL DEFAULT NOW(),

    last_accessed TIMESTAMP
    NOT NULL DEFAULT NOW(),

    linkable BOOLEAN
    NOT NULL DEFAULT FALSE,

    ref_link BIGINT
    REFERENCES memories_v2(ref_id),

    expires_at TIMESTAMP
);