from fastapi import FastAPI, UploadFile, Form, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import docker
import os, uuid, shutil, zipfile, time

app = FastAPI()
client = docker.from_env()

# CORS support
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files for dashboard
app.mount("/static", StaticFiles(directory="static"), name="static")

PROJECTS_DIR = "./projects"
os.makedirs(PROJECTS_DIR, exist_ok=True)

@app.get("/")
def dashboard():
    containers = client.containers.list(all=True)
    html = """
    <html>
    <head>
        <title>FastHost Dashboard</title>
        <style>
            body { font-family: sans-serif; padding: 20px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { padding: 8px; border: 1px solid #ccc; text-align: left; }
            th { background: #f4f4f4; }
            button { padding: 5px 10px; margin-right: 5px; }
        </style>
    </head>
    <body>
        <h1>🚀 FastHost Dashboard</h1>
        <table>
            <tr>
                <th>Name</th><th>Status</th><th>Port</th><th>Actions</th>
            </tr>
    """
    for c in containers:
        ports = client.api.port(c.id, 8080)
        port = ports[0]['HostPort'] if ports else "-"
        html += f"""
        <tr>
            <td>{c.name}</td>
            <td>{c.status}</td>
            <td>{port}</td>
            <td>
                <a href='/logs/{c.name}' target='_blank'>Logs</a>
                <form style='display:inline' action='/stop/{c.name}' method='post'><button>Stop</button></form>
                <form style='display:inline' action='/pause/{c.name}' method='post'><button>Pause</button></form>
                <form style='display:inline' action='/start/{c.name}' method='post'><button>Start</button></form>
            </td>
        </tr>
        """
    html += "</table></body></html>"
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

    # Extract zip
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
            detach=True
        )

        time.sleep(1)
        port = client.api.port(container.id, 8080)[0]['HostPort']
        return JSONResponse({
            "project_id": project_id,
            "container_name": container_name,
            "preview_url": f"http://localhost:{port}"
        })

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/projects")
def list_projects():
    containers = client.containers.list(all=True)
    result = []
    for c in containers:
        ports = client.api.port(c.id, 8080)
        port = ports[0]['HostPort'] if ports else None
        result.append({
            "name": c.name,
            "status": c.status,
            "port": port,
            "url": f"http://localhost:{port}" if port else None
        })
    return result

@app.post("/stop/{container_name}")
def stop_container(container_name: str):
    try:
        container = client.containers.get(container_name)
        container.stop()
        container.remove()
        return {"status": "stopped", "container": container_name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/pause/{container_name}")
def pause_container(container_name: str):
    try:
        container = client.containers.get(container_name)
        container.pause()
        return {"status": "paused", "container": container_name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/start/{container_name}")
def start_container(container_name: str):
    try:
        container = client.containers.get(container_name)
        container.unpause()
        return {"status": "started", "container": container_name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/logs/{container_name}")
def stream_logs(container_name: str):
    try:
        container = client.containers.get(container_name)
        log_stream = container.logs(stream=True, follow=True)

        def event_generator():
            for line in log_stream:
                yield f"data: {line.decode()}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))