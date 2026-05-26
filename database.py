import os
import psycopg2 

from dotenv import load_dotenv 

load_dotenv()

DATABASE_URL = os.getenv('DTABASE_URL')

conn = psycopg2.connect(DATABASE_URL)

cursor = conn.cursor()

