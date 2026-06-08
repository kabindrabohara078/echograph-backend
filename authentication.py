from database import conn
from passlib.context import CryptContext

from fastapi import (
    FastAPI,
    HTTPException,
    Depends
)

pwd_context = CryptContext(
    schemes = ["bcrypt"],
    deprecated = "auto"
)

def hash_password(password : str):
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)


def login(user):

    print("Login test")
    print(user)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT user_id, password_hash FROM user_auth WHERE email= %s
        """,(user.email,)
    )

    row = cursor.fetchone()

    if row:
        hashed_password = row[1]

        if not verify_password(user.password, hashed_password):
            raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )
            return 0
    else:
        raise HTTPException(
            status_code=404,
            detail="User does not exist"
        )
        return 0
    
    return str(row[0])
    

def signup(user):

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM users WHERE email = %s
        """,(user.email,)
    )

    existing_user = cursor.fetchone()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="User already exists"
        )
        return 0
    else:
        cursor.execute(
            """
            INSERT INTO users(fname, lname, email)
            VALUES(%s, %s, %s)
            RETURNING id
            """, (user.firstname, user.lastname, user.email)
        )
        hash_pwd = hash_password(user.password)

        user_id = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO user_auth(user_id, email, password_hash) VALUES(%s,%s, %s)
            """, (user_id, user.email, hash_pwd)
        )
        conn.commit()
        return 1

