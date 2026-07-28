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
    print("Login attempt for:", user.email)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT u.id, ua.password_hash, u.fname, u.lname
        FROM user_auth ua
        JOIN users u ON ua.user_id = u.id
        WHERE ua.email = %s
        """, (user.email,)
    )

    row = cursor.fetchone()

    if row:
        hashed_password = row[1]

        if not verify_password(user.password, hashed_password):
            raise HTTPException(
                status_code=401,
                detail="Invalid credentials"
            )

        user_name = f"{row[2]} {row[3]}".strip() if row[2] else user.email.split("@")[0]
        return {
            "user_id": str(row[0]),
            "name": user_name,
            "email": user.email
        }
    else:
        raise HTTPException(
            status_code=404,
            detail="User does not exist"
        )


def signup(user):
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM users WHERE email = %s
        """, (user.email,)
    )

    existing_user = cursor.fetchone()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="User already exists"
        )
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


def google_auth_user(email: str, name: str = ""):
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, fname, lname FROM users WHERE email = %s
        """, (email,)
    )

    row = cursor.fetchone()

    if row:
        fetched_name = f"{row[1]} {row[2]}".strip() if row[1] else (name or email.split("@")[0])
        return str(row[0]), fetched_name

    fname = name.split()[0] if name else email.split("@")[0]
    lname = " ".join(name.split()[1:]) if name and len(name.split()) > 1 else ""

    cursor.execute(
        """
        INSERT INTO users(fname, lname, email)
        VALUES(%s, %s, %s)
        RETURNING id
        """, (fname, lname, email)
    )

    user_id = cursor.fetchone()[0]

    cursor.execute(
        """
        INSERT INTO user_auth(user_id, email, password_hash, email_verified)
        VALUES(%s, %s, NULL, TRUE)
        """, (user_id, email)
    )
    conn.commit()

    full_name = f"{fname} {lname}".strip() or email.split("@")[0]
    return str(user_id), full_name
