from fastapi import APIRouter, HTTPException, UploadFile, Form
from fastapi.responses import JSONResponse
import docker
import uuid
import zipfile
import os
import time
from pyngrok import ngrok

router = APIRouter()

@router.post("/project")
async def deploy_code(file: UploadFile, app_name: str = Form(...)):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are supported")

    # Create a unique project folder under /projects/<project_id>
    project_id = str(uuid.uuid4())
    base_dir = os.path.dirname(os.path.abspath(__file__))  # /router/
    projects_dir = os.path.abspath(os.path.join(base_dir, "..", "projects"))
    os.makedirs(projects_dir, exist_ok=True)

    project_path = os.path.join(projects_dir, project_id)
    os.makedirs(project_path, exist_ok=True)

    # Save uploaded zip to that folder
    zip_path = os.path.join(project_path, file.filename)
    with open(zip_path, "wb") as f:
        f.write(await file.read())

    # Extract zip contents into the project folder
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # If all files are inside a single top-level directory, extract their contents directly
            members = zip_ref.namelist()
            top_level_dirs = set(m.split('/')[0] for m in members if '/' in m)
            if len(top_level_dirs) == 1 and all(m.startswith(list(top_level_dirs)[0] + '/') for m in members):
                for member in members:
                    target = os.path.join(project_path, os.path.relpath(member, list(top_level_dirs)[0]))
                    if member.endswith('/'):
                        os.makedirs(target, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with zip_ref.open(member) as source, open(target, "wb") as dest:
                            dest.write(source.read())
            else:
                zip_ref.extractall(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid zip file: {str(e)}")

    # Debug: Show all extracted files
    print(f"[DEBUG] Extracted files in: {project_path}")
    for dirpath, _, files in os.walk(project_path):
        for fname in files:
            print(" -", os.path.join(dirpath, fname))

    # Find required files inside the project folder (recursively)
    def find_file(filename, root):
        for dirpath, _, files in os.walk(root):
            if filename in files:
                return os.path.join(dirpath, filename)
        return None

    main_py = find_file("main.py", project_path)
    requirements_txt = find_file("requirements.txt", project_path)
    dockerfile = find_file("DockerFile", project_path)

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
            detail=f"Zip is missing required file(s): {', '.join(missing_files)} (at any level)"
        )

    # Build and run Docker container
    image_name = f"{app_name.lower()}_{project_id[:8]}"
    container_name = image_name

    try:
        docker_client = docker.from_env()
        image, _ = docker_client.images.build(path=project_path, tag=image_name)

        container = docker_client.containers.run(
            image=image_name,
            ports={"8080/tcp": None},
            name=container_name,
            detach=True,
            mem_limit="512m",
            nano_cpus=1_000_000_000,  # 1 CPU
            read_only=True,
            tmpfs={"/tmp": ""},
            user="1001:1001"
        )

        time.sleep(2)  # Give Docker time to assign port

        port_info = docker_client.api.port(container.id, 8080)
        if not port_info:
            raise Exception("Port 8080 not exposed by container")
        port = port_info[0]['HostPort']

        # Expose with ngrok
        tunnel = ngrok.connect(port, bind_tls=True)
        public_url = tunnel.public_url

        return JSONResponse({
            "project_id": project_id,
            "container_name": container_name,
            "preview_url": public_url
        })

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)