from fastapi import APIRouter, HTTPException, UploadFile, Form
from fastapi.responses import JSONResponse, HTMLResponse
import docker
import uuid
from docker import client
import zipfile
import os
import shutil
import time
from pyngrok import ngrok

PROJECTS_DIR = "./projects"
os.makedirs(PROJECTS_DIR, exist_ok=True)

router =  APIRouter()

@router.post("/project")
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
                os.path.isfile(os.path.join(project_path, "requirements.txt")) and
                os.path.isfile(os.path.join(project_path, "Dockerfile"))):
            raise HTTPException(status_code=400, detail="Zip must contain main.py, requirements.txt, and Dockerfile")

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