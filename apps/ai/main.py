from fastapi import FastAPI

app = FastAPI(title="AI Service")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/recommend")
def recommend_stub(payload: dict):
    return {"recommendations": [], "input": payload}
