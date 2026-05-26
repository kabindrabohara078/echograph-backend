from fastapi import FastAPI
# from database import conn 
from embedding import generate_embedding

app = FastAPI()

@app.get('/')
def root():
    return ({'message':'EchoGraph API running'})

# @app.get('/test-db')
# def test_db():
#     return {'status':'Database connected'}

@app.get('/embed')
def embed():
    vector = generate_embedding("I like doing maths")

    return {
        "dimensions": len(vector),
        "sample": vector
    }