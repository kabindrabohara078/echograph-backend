CREATE TABLE user_auth (
    user_id INTEGER PRIMARY KEY
        REFERENCES users(id)
        ON DELETE CASCADE,

    email TEXT REFERENCES users(email),

    mobile_number TEXT UNIQUE,

    password_hash TEXT NOT NULL,

    email_verified BOOLEAN NOT NULL DEFAULT FALSE,

    mobile_verified BOOLEAN NULL DEFAULT FALSE,

    state TEXT NOT NULL DEFAULT 'active'
        CHECK (
            state IN (
                'active',
                'suspended',
                'deleted'
            )
        ),

    last_login TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);