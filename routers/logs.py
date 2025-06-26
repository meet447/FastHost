from fastapi import APIRouter
from fastapi.responses import JSONResponse, HTMLResponse
import docker
from docker import client

router = APIRouter()

@router.get("/fetch/{container_name}")
def stream_logs(container_name: str):
    try:
        container = client.containers.get(container_name)
        logs = container.logs(tail=100).decode()
        return HTMLResponse(f"<pre>{logs}</pre>")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
