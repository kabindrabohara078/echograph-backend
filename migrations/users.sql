CREATE TABLE users (
    id SERIAL PRIMARY KEY,

    fname TEXT NOT NULL,

    lname TEXT,

    uname TEXT UNIQUE,

    email TEXT UNIQUE NOT NULL,

    display_name TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);