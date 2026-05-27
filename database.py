import os
import psycopg2 

from dotenv import load_dotenv 

load_dotenv()

# environment: local url
DATABASE_URL = os.getenv("DTABASE_URL")

# connecting database
conn = psycopg2.connect(DATABASE_URL)
# print('Database connected...')


cursor = conn.cursor()

