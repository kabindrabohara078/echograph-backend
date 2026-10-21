import os
import re
import math
import json
import sqlite3
import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


# =========================================================
# SQLITE HELPER FUNCTIONS FOR OFFLINE RAG & RANKING
# =========================================================

def sqlite_cosine_dist(v1, v2):
    """Calculates cosine distance between two JSON array string vectors."""
    try:
        if isinstance(v1, str):
            v1 = json.loads(v1)
        if isinstance(v2, str):
            v2 = json.loads(v2)
        dot = sum(x * y for x, y in zip(v1, v2))
        na = math.sqrt(sum(x * x for x in v1))
        nb = math.sqrt(sum(x * x for x in v2))
        if na == 0 or nb == 0:
            return 1.0
        return max(0.0, 1.0 - (dot / (na * nb)))
    except Exception:
        return 1.0


def sqlite_epoch_diff(now_val, date_val):
    """Calculates time difference in seconds between two ISO datetimes for RAG decay."""
    try:
        if isinstance(now_val, str):
            dt_now = datetime.datetime.fromisoformat(now_val)
        else:
            dt_now = datetime.datetime.utcnow()

        if isinstance(date_val, str):
            dt_past = datetime.datetime.fromisoformat(date_val)
        else:
            dt_past = dt_now

        return max(0.0, (dt_now - dt_past).total_seconds())
    except Exception:
        return 0.0


# =========================================================
# SQLITE CURSOR & CONNECTION WRAPPERS
# =========================================================

class SQLiteCursorWrapper:
    def __init__(self, raw_cursor):
        self._cursor = raw_cursor

    def _translate_query(self, query: str) -> str:
        # 1. Translate vector cosine distance operator (<=>)
        q = re.sub(r'embedding\s*<=>\s*%s::vector', 'cosine_dist(embedding, %s)', query)
        q = re.sub(r'\(embedding\s*<=>\s*%s::vector\)', 'cosine_dist(embedding, %s)', q)

        # 2. Translate PostgreSQL time decay formula
        q = re.sub(
            r'EXTRACT\s*\(\s*EPOCH\s+FROM\s+\(\s*NOW\(\)\s*-\s*([a-zA-Z0-9_]+)\s*\)\s*\)',
            r'epoch_diff(NOW(), \1)',
            q,
            flags=re.IGNORECASE
        )

        # 3. Strip PostgreSQL typecast syntax
        q = re.sub(r'%s::vector', '%s', q)

        # 4. Replace %s placeholder with ? for SQLite
        q = q.replace('%s', '?')
        return q

    def execute(self, query, params=None):
        if params is None:
            trans_query = self._translate_query(query)
            return self._cursor.execute(trans_query)

        # Handle PostgreSQL ANY(%s) with python list/tuple
        clean_params = []
        q = query
        for p in params:
            if isinstance(p, (list, tuple)):
                if len(p) == 0:
                    q = re.sub(r'=\s*ANY\s*\(\s*%s\s*\)', 'IN (NULL)', q, count=1)
                else:
                    placeholders = ','.join(['%s'] * len(p))
                    q = re.sub(r'=\s*ANY\s*\(\s*%s\s*\)', f'IN ({placeholders})', q, count=1)
                    for item in p:
                        clean_params.append(item)
            elif isinstance(p, datetime.datetime):
                clean_params.append(p.strftime('%Y-%m-%d %H:%M:%S'))
            else:
                clean_params.append(p)

        trans_query = self._translate_query(q)
        return self._cursor.execute(trans_query, tuple(clean_params))

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchmany(self, size=None):
        return self._cursor.fetchmany(size)

    def close(self):
        return self._cursor.close()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class SQLiteConnectionWrapper:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = None
        self._init_db()

    def _get_raw_conn(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.create_function("cosine_dist", 2, sqlite_cosine_dist)
            self._conn.create_function("epoch_diff", 2, sqlite_epoch_diff)
            self._conn.create_function("LN", 1, lambda x: math.log(max(float(x), 1e-9)))
            self._conn.create_function("EXP", 1, lambda x: math.exp(min(float(x), 700)))
            self._conn.create_function("NOW", 0, lambda: datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
        return self._conn

    def _init_db(self):
        """Auto-initialize database tables in SQLite if they do not exist."""
        raw = self._get_raw_conn()
        cur = raw.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fname TEXT NOT NULL,
            lname TEXT,
            uname TEXT UNIQUE,
            email TEXT UNIQUE NOT NULL,
            display_name TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_auth (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            email TEXT REFERENCES users(email),
            mobile_number TEXT UNIQUE,
            password_hash TEXT,
            email_verified BOOLEAN NOT NULL DEFAULT 0,
            mobile_verified BOOLEAN DEFAULT 0,
            state TEXT NOT NULL DEFAULT 'active',
            last_login TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS memories_v2 (
            ref_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'active',
            type TEXT NOT NULL,
            importance_score REAL NOT NULL DEFAULT 1.0,
            access_ratio REAL NOT NULL DEFAULT 0.1,
            embedding TEXT NOT NULL,
            initial_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            linkable BOOLEAN NOT NULL DEFAULT 1,
            ref_link INTEGER REFERENCES memories_v2(ref_id),
            node_life INTEGER DEFAULT 91,
            expires_at TIMESTAMP,
            entities TEXT
        );

        CREATE TABLE IF NOT EXISTS memory_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_id INTEGER NOT NULL REFERENCES memories_v2(ref_id) ON DELETE CASCADE,
            target_id INTEGER NOT NULL REFERENCES memories_v2(ref_id) ON DELETE CASCADE,
            relation_type TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_id, target_id, relation_type)
        );

        CREATE INDEX IF NOT EXISTS idx_mem_links_user ON memory_links(user_id);
        CREATE INDEX IF NOT EXISTS idx_mem_links_src ON memory_links(source_id);
        CREATE INDEX IF NOT EXISTS idx_mem_links_tgt ON memory_links(target_id);
        """)
        raw.commit()

        # Safe migrations: ensure columns & tables exist on existing SQLite databases
        try:
            cur.execute("ALTER TABLE memories_v2 ADD COLUMN expires_at TIMESTAMP;")
            raw.commit()
        except Exception:
            pass

        try:
            cur.execute("ALTER TABLE memories_v2 ADD COLUMN entities TEXT;")
            raw.commit()
        except Exception:
            pass

        try:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS memory_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                source_id INTEGER NOT NULL REFERENCES memories_v2(ref_id) ON DELETE CASCADE,
                target_id INTEGER NOT NULL REFERENCES memories_v2(ref_id) ON DELETE CASCADE,
                relation_type TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_id, target_id, relation_type)
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_links_user ON memory_links(user_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_links_src ON memory_links(source_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_links_tgt ON memory_links(target_id);")
            raw.commit()
        except Exception:
            pass

        cur.close()

    def cursor(self, *args, **kwargs):
        raw_cur = self._get_raw_conn().cursor()
        return SQLiteCursorWrapper(raw_cur)

    def commit(self):
        return self._get_raw_conn().commit()

    def rollback(self):
        return self._get_raw_conn().rollback()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


# =========================================================
# POSTGRESQL CONNECTION WRAPPER (LIVE CLOUD)
# =========================================================

class PostgresConnectionWrapper:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self._conn = None

    def get_conn(self):
        import psycopg2
        if self._conn is None or self._conn.closed != 0:
            print("Connecting to Neon PostgreSQL database...")
            self._conn = psycopg2.connect(self.db_url)
            try:
                with self._conn.cursor() as mig_cur:
                    mig_cur.execute("ALTER TABLE memories_v2 ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP;")
                    mig_cur.execute("ALTER TABLE memories_v2 ADD COLUMN IF NOT EXISTS entities TEXT;")
                    mig_cur.execute("""
                    CREATE TABLE IF NOT EXISTS memory_links (
                        id BIGSERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        source_id BIGINT NOT NULL REFERENCES memories_v2(ref_id) ON DELETE CASCADE,
                        target_id BIGINT NOT NULL REFERENCES memories_v2(ref_id) ON DELETE CASCADE,
                        relation_type TEXT NOT NULL,
                        weight FLOAT NOT NULL DEFAULT 1.0,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        UNIQUE(source_id, target_id, relation_type)
                    );
                    CREATE INDEX IF NOT EXISTS idx_mem_links_user ON memory_links(user_id);
                    CREATE INDEX IF NOT EXISTS idx_mem_links_src ON memory_links(source_id);
                    CREATE INDEX IF NOT EXISTS idx_mem_links_tgt ON memory_links(target_id);
                    """)
                self._conn.commit()
            except Exception as mig_err:
                print("[POSTGRES MIGRATION NOTE]:", mig_err)
                try:
                    self._conn.rollback()
                except Exception:
                    pass
        else:
            try:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT 1;")
            except Exception as e:
                print(f"Database connection dropped/idle ({e}). Reconnecting to database...")
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = psycopg2.connect(self.db_url)
        return self._conn

    def cursor(self, *args, **kwargs):
        return self.get_conn().cursor(*args, **kwargs)

    def commit(self):
        return self.get_conn().commit()

    def rollback(self):
        return self.get_conn().rollback()

    def close(self):
        if self._conn and self._conn.closed == 0:
            self._conn.close()
            self._conn = None


# =========================================================
# ADAPTIVE INITIALIZATION
# =========================================================

is_postgres = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")

if is_postgres:
    print("[DATABASE] Remote PostgreSQL mode active (Live Cloud Database).")
    conn = PostgresConnectionWrapper(DATABASE_URL)
else:
    sqlite_path = "echograph_local.db"
    if DATABASE_URL.startswith("sqlite:///"):
        sqlite_path = DATABASE_URL.replace("sqlite:///", "")
    elif DATABASE_URL.startswith("sqlite://"):
        sqlite_path = DATABASE_URL.replace("sqlite://", "")

    if not os.path.isabs(sqlite_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        sqlite_path = os.path.join(base_dir, sqlite_path)

    print(f"[DATABASE] Local Offline SQLite mode active: {sqlite_path}")
    conn = SQLiteConnectionWrapper(sqlite_path)
