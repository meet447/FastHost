from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
import docker
import os
import uuid
import shutil
import zipfile
import time
from pyngrok import ngrok

app = FastAPI()
client = docker.from_env()

PROJECTS_DIR = "./projects"
os.makedirs(PROJECTS_DIR, exist_ok=True)

# Create Docker network if not exists
NETWORK_NAME = "fasthost-net"
try:
    client.networks.get(NETWORK_NAME)
except docker.errors.NotFound:
    client.networks.create(NETWORK_NAME)

@app.get("/")
def dashboard():
    containers = client.containers.list(all=True)
    html = """
    <html>
    <head>
        <title>FastHost Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4; }
            table { border-collapse: collapse; width: 100%; background: white; }
            th, td { border: 1px solid #ccc; padding: 10px; text-align: left; }
            th { background-color: #eee; }
            a { margin-right: 10px; text-decoration: none; color: #007BFF; }
        </style>
    </head>
    <body>
        <h1>🚀 FastHost Dashboard</h1>
        <table>
            <tr><th>Name</th><th>Status</th><th>Actions</th></tr>
    """
    for container in containers:
        html += f"<tr><td>{container.name}</td><td>{container.status}</td><td>"
        html += f"<a href='/logs/{container.name}' target='_blank'>Logs</a>"
        html += f"<a href='/start/{container.name}'>Start</a>"
        html += f"<a href='/pause/{container.name}'>Pause</a>"
        html += f"<a href='/stop/{container.name}'>Stop</a>"
        html += "</td></tr>"
    html += """
        </table>
    </body></html>
    """
    return HTMLResponse(content=html)

@app.post("/deploy")
async def deploy_code(file: UploadFile, app_name: str = Form(...)):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are supported")

    project_id = str(uuid.uuid4())
    project_path = os.path.join(PROJECTS_DIR, project_id)
    os.makedirs(project_path, exist_ok=True)

    zip_path = os.path.join(project_path, file.filename)
    with open(zip_path, "wb") as f:
        f.write(await file.read())

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid zip file: {str(e)}")

    if not (os.path.isfile(os.path.join(project_path, "main.py")) and
            os.path.isfile(os.path.join(project_path, "requirements.txt"))):
        raise HTTPException(status_code=400, detail="Zip must contain main.py and requirements.txt")

    shutil.copy("Dockerfile", project_path)

    image_name = f"{app_name.lower()}_{project_id[:8]}"
    container_name = image_name

    try:
        image, _ = client.images.build(path=project_path, tag=image_name)
        container = client.containers.run(
            image=image_name,
            ports={'8080/tcp': None},
            name=container_name,
            detach=True,
            mem_limit="512m",
            nano_cpus=1_000_000_000,  # 1 CPU
            read_only=True,
            tmpfs={"/tmp": ""},
            network=NETWORK_NAME,
            user="1001:1001"
        )

        time.sleep(2)
        port = client.api.port(container.id, 8080)[0]['HostPort']

        # Start ngrok tunnel with pyngrok
        tunnel = ngrok.connect(port, bind_tls=True)
        public_url = tunnel.public_url

        return JSONResponse({
            "project_id": project_id,
            "container_name": container_name,
            "preview_url": public_url
        })

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/logs/{container_name}")
def stream_logs(container_name: str):
    try:
        container = client.containers.get(container_name)
        logs = container.logs(tail=100).decode()
        return HTMLResponse(f"<pre>{logs}</pre>")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/start/{container_name}")
def start_container(container_name: str):
    try:
        container = client.containers.get(container_name)
        container.start()
        return JSONResponse({"status": "started"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/pause/{container_name}")
def pause_container(container_name: str):
    try:
        container = client.containers.get(container_name)
        container.pause()
        return JSONResponse({"status": "paused"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/stop/{container_name}")
def stop_container(container_name: str):
    try:
        container = client.containers.get(container_name)
        container.stop()
        container.remove(force=True)
        return JSONResponse({"status": "stopped and removed"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)