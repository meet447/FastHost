from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
import docker
from docker import client

router = APIRouter()

@router.get("/start/{container_name}")
def start_container(container_name: str):
    try:
        container = client.containers.get(container_name)
        container.unpause()
        return JSONResponse({"status": "started"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/pause/{container_name}")
def pause_container(container_name: str):
    try:
        container = client.containers.get(container_name)
        container.pause()
        return JSONResponse({"status": "paused"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/stop/{container_name}")
def stop_container(container_name: str):
    try:
        container = client.containers.get(container_name)
        container.stop()
        container.remove(force=True)
        return JSONResponse({"status": "stopped and removed"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)