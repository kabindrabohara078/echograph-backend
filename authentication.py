from database import conn
from passlib.context import CryptContext



pwd_context = CryptContext(
    schemes = ["bcrypt"],
    deprecated = "auto"
)

def hash_password(password : str):
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)



def login(user):

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM users WHERE email = %s
        """,(user.email,)
    )

    existing_user = cursor.fetchone()

    if existing_user:
        cursor.execute(
            """
            SELECT password_hash FROM user_auth WHERE email = %s
            """, (user.email)
        )

        cursor.commit()

        hashed_password = cursor.fetchone()
        return verify_password(user.password, hashed_password)
    else:
        return -1





# fname
# lname
# email
# password

def signup(user):

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM users WHERE email = %s
        """,(user.email,)
    )

    existing_user = cursor.fetchone()

    if existing_user:
        return "User already Exists"

       
    else:
        cursor.execute(
            """
            INSERT INTO users(fname, lname, email) VALUES(%s, %s, %s)
            """, (user.fname, user.lname, user.email)

        )
        print('++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
        print(user.password)
        print('++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')

        hash_pwd = hash_password(user.password)
        
        cursor.execute(
            """
            INSERT INTO user_auth(email, password_hash) VALUES(%s, %s)
            """, (user.email, hash_pwd)
        )

        cursor.commit()

    return 0






