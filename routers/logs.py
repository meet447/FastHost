from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import docker

router = APIRouter()

docker_client = docker.from_env()

@router.get("/fetch/{container_name}")
def stream_logs(container_name: str):
    try:
        container = docker_client.containers.get(container_name)
        return StreamingResponse(container.logs(stream=True, follow=True), media_type="text/event-stream")
    except Exception as e:
        return StreamingResponse(f"Error: {str(e)}", media_type="text/event-stream")
