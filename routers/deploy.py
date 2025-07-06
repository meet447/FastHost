from fastapi import APIRouter, HTTPException, UploadFile, Form
from fastapi.responses import JSONResponse
import docker
import uuid
import zipfile
import os
import time
from pyngrok import ngrok
import git
from config import PROJECTS_DIRECTORY

router = APIRouter()
ngrok_url = {}

def find_file(filename, root):
    filename = filename.lower()
    for dirpath, _, files in os.walk(root):
        for file in files:
            if file.lower() == filename:
                return os.path.join(dirpath, file)
    return None

def deploy_project(project_path: str, app_name: str) -> JSONResponse:
    """
    Deploys a project from a given path.

    Args:
        project_path: The absolute path to the project directory.
        app_name: The name of the application.

    Returns:
        A JSONResponse with the deployment details or an error.
    """
    project_id = os.path.basename(project_path)
    image_name = f"{app_name.lower()}_{project_id[:8]}"
    container_name = image_name

    main_py = find_file("main.py", project_path)
    requirements_txt = find_file("requirements.txt", project_path)
    dockerfile = find_file("Dockerfile", project_path)

    missing_files = []
    if not main_py:
        missing_files.append("main.py")
    if not requirements_txt:
        missing_files.append("requirements.txt")
    if not dockerfile:
        missing_files.append("Dockerfile")

    if missing_files:
        raise HTTPException(
            status_code=400,
            detail=f"Project is missing required file(s): {', '.join(missing_files)} (case-insensitive)"
        )

    if os.path.dirname(dockerfile) != project_path:
        print(f"[DEBUG] Moving Dockerfile from {dockerfile} to project root")
        target_path = os.path.join(project_path, "Dockerfile")
        os.replace(dockerfile, target_path)
        dockerfile = target_path

    try:
        docker_client = docker.from_env()
        for c in docker_client.containers.list(all=True):
            if c.status in ["created", "exited"]:
                print(f"Removing leftover container {c.name} ({c.id})")
                c.remove(force=True)
                
        image, _ = docker_client.images.build(path=project_path, tag=image_name)

        container = docker_client.containers.run(
            image=image_name,
            ports={"8080/tcp": None},
            name=container_name,
            detach=True,
            mem_limit="512m",
            nano_cpus=1_000_000_000,
            read_only=True,
            tmpfs={"/tmp": ""},
            user="1001:1001"
        )

        time.sleep(2)

        port_info = docker_client.api.port(container.id, 8080)
        if not port_info:
            raise Exception("Port 8080 not exposed by container")
        port = port_info[0]['HostPort']

        tunnel = ngrok.connect(port, bind_tls=True)
        public_url = tunnel.public_url
        ngrok_url[container_name] = public_url

        return JSONResponse({
            "project_id": project_id,
            "container_name": container_name,
            "preview_url": public_url
        })

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@router.post("/project")
async def deploy_code(file: UploadFile, app_name: str = Form(...)):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are supported")
    
    project_id = str(uuid.uuid4())
    os.makedirs(PROJECTS_DIRECTORY, exist_ok=True)

    project_path = os.path.join(PROJECTS_DIRECTORY, project_id)
    os.makedirs(project_path, exist_ok=True)

    zip_path = os.path.join(project_path, file.filename)
    with open(zip_path, "wb") as f:
        f.write(await file.read())

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid zip file: {str(e)}")

    print(f"[DEBUG] Extracted files in: {project_path}")
    for dirpath, _, files in os.walk(project_path):
        for fname in files:
            print(" -", os.path.join(dirpath, fname))
    
    return deploy_project(project_path, app_name)

@router.post("/github")
async def deploy_github(repo_url: str = Form(...), app_name: str = Form(...)):
    project_id = str(uuid.uuid4())
    os.makedirs(PROJECTS_DIRECTORY, exist_ok=True)

    project_path = os.path.join(PROJECTS_DIRECTORY, project_id)

    try:
        git.Repo.clone_from(repo_url, project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to clone repository: {str(e)}")

    print(f"[DEBUG] Cloned repository to: {project_path}")
    for dirpath, _, files in os.walk(project_path):
        for fname in files:
            print(" -", os.path.join(dirpath, fname))

    return deploy_project(project_path, app_name)