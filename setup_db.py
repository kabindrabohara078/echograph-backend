import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def init_db():
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    print("Enabling vector extension...")
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Check if existing 'users' table has 'id' as UUID (old schema incompatible with serial id)
    cursor.execute("""
        SELECT data_type FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'id';
    """)
    row = cursor.fetchone()
    if row and row[0] == 'uuid':
        print("Existing 'users' table uses UUID. Dropping incompatible old schema...")
        cursor.execute("DROP TABLE IF EXISTS memories_v2 CASCADE;")
        cursor.execute("DROP TABLE IF EXISTS user_auth CASCADE;")
        cursor.execute("DROP TABLE IF EXISTS users CASCADE;")

    print("Creating 'users' table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        fname TEXT NOT NULL,
        lname TEXT,
        uname TEXT UNIQUE,
        email TEXT UNIQUE NOT NULL,
        display_name TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """)

    print("Creating 'user_auth' table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_auth (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        email TEXT REFERENCES users(email),
        mobile_number TEXT UNIQUE,
        password_hash TEXT,
        email_verified BOOLEAN NOT NULL DEFAULT FALSE,
        mobile_verified BOOLEAN NULL DEFAULT FALSE,
        state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'suspended', 'deleted')),
        last_login TIMESTAMP,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """)

    print("Creating 'memories_v2' table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS memories_v2 (
        ref_id BIGSERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('permanent', 'temporary', 'active', 'archive')),
        type TEXT NOT NULL CHECK (
            type IN (
                'fact', 'event', 'preference', 'decision', 'task', 'goal', 
                'relationship', 'profile', 'conversation', 'observation', 
                'knowledge', 'plan', 'reminder', 'feedback', 'emotion', 'delete'
            )
        ),
        importance_score FLOAT NOT NULL DEFAULT 1 CHECK (importance_score >= 0 AND importance_score <= 1),
        access_ratio NUMERIC(20,3) NOT NULL DEFAULT 0.1,
        embedding VECTOR(384) NOT NULL,
        initial_date TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
        last_accessed TIMESTAMP NOT NULL DEFAULT NOW(),
        linkable BOOLEAN NOT NULL DEFAULT FALSE,
        ref_link BIGINT REFERENCES memories_v2(ref_id),
        node_life INTEGER NOT NULL DEFAULT 91
    );
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("Database schema successfully initialized!")

if __name__ == "__main__":
    init_db()
