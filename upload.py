import os
import zipfile
import requests
import dotenv

# Load environment variables
dotenv.load_dotenv()

def zip_folder(source_dir, zip_path):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, start=source_dir)
                zipf.write(file_path, arcname)

def upload_zip(zip_path, app_name, server_url):
    with open(zip_path, 'rb') as f:
        files = {'file': (os.path.basename(zip_path), f, 'application/zip')}
        data = {'app_name': app_name}
        response = requests.post(f'{server_url}/deploy/project', files=files, data=data)

    if response.status_code == 200:
        print("✅ Deployed Successfully!")
        print(response.json())
    else:
        print("❌ Deployment Failed:")
        print(response.text)

if __name__ == "__main__":
    # Configuration
    folder_to_zip = "examples"               # Folder with main.py and requirements.txt
    zip_output = "project.zip"
    app_name = "maouapp"
    server_url = 'http://192.168.29.195:8000'  # Replace with your server URL

    print("📦 Zipping project...")
    zip_folder(folder_to_zip, zip_output)

    print("📤 Uploading...")
    upload_zip(zip_output, app_name, server_url)