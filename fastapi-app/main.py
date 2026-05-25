from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pathlib import Path

app = FastAPI(title="FastAPI App")


@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(content=html_path.read_text(), status_code=200)


@app.get("/api/status")
async def status():
    return {"message": "Server is running", "status": "ok"}


@app.get("/api/hello")
async def hello(name: str = "World"):
    return {"message": f"Hello, {name}!"}
