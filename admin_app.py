from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok", "message": "Admin panel is running"}

@app.get("/{path:path}")
async def catch_all():
    return {"status": "ok", "message": "Route not found, but server is alive"}