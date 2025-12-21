from fastapi import FastAPI

app = FastAPI(title="Clothing API")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/v1/catalog")
def catalog_stub():
    return {"items": [], "note": "stub"}
