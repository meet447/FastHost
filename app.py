from fastapi import FastAPI
import docker
import dotenv
from routers.deploy import router as deploy_router
from routers.controls import router as controls_router
from routers.logs import router as logs_router

# Load environment variables
dotenv.load_dotenv()

app = FastAPI()
app.include_router(controls_router, prefix="/controls")
app.include_router(logs_router, prefix="/logs")
app.include_router(deploy_router, prefix="/deploy")

client = docker.from_env()

@app.get("/")
def dashboard():
    containers = client.containers.list(all=True)
    return containers


