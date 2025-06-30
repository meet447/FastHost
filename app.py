from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
import docker
import dotenv
from routers.deploy import router as deploy_router, ngrok_url
from routers.controls import router as controls_router
from routers.logs import router as logs_router

# Load environment variables
dotenv.load_dotenv()

app = FastAPI()
app.include_router(controls_router, prefix="/controls")
app.include_router(logs_router, prefix="/logs")
app.include_router(deploy_router, prefix="/deploy")

client = docker.from_env()
templates = Jinja2Templates(directory="templates")

@app.get("/")
def dashboard(request: Request):
    containers = client.containers.list(all=True)
    container_list = [
        {
            "id": container.id,
            "name": container.name,
            "status": container.status,
            "image": container.image.tags,
            "url": ngrok_url.get(container.name)
        }
        for container in containers
    ]
    return templates.TemplateResponse("dashboard.html", {"request": request, "containers": container_list, "ngrok_url": ngrok_url})


