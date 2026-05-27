from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/test")
async def test(request: Request):
    data = await request.json()
    print(data)
    return {"received": data}