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


    print(user)

    cursor.execute(
        """
        SELECT password_hash FROM user_auth WHERE email= %s
        """,(user.email,)
    )

    row = cursor.fetchone()

    print('++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
    print(row)

    if not row:
        return -1


    hashed_password = row[0]

    print(hashed_password)

    if verify_password(user.password, hashed_password) == False:
        return 0
    
    return True
   





# firstname
# lastname
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
            INSERT INTO users(fname, lname, email)
            VALUES(%s, %s, %s)
            RETURNING id
            """, (user.firstname, user.lastname, user.email)

        )

        user_id = cursor.fetchone()[0]

        hash_pwd = hash_password(user.password)
        print('++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++') #password hash test
        print(hash_pwd)
        print('++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')

        cursor.execute(
            """
            INSERT INTO user_auth(user_id, email, password_hash) VALUES(%s,%s, %s)
            """, (user_id, user.email, hash_pwd)
        )

        conn.commit()

    return 0






