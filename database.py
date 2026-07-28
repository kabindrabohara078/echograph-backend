import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

class AutoReconnectConnection:
    def __init__(self, db_url):
        self.db_url = db_url
        self._conn = None

    def get_conn(self):
        if self._conn is None or self._conn.closed != 0:
            print("Connecting to Neon PostgreSQL database...")
            self._conn = psycopg2.connect(self.db_url)
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

conn = AutoReconnectConnection(DATABASE_URL)
print("Auto-reconnecting database manager initialized...")
