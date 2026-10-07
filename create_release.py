import os
import sys
import shutil
import requests
import json
import time

token = "REMOVED_TOKEN"
repo_owner = "dedeyuyu"
repo_name = "VideoTools"

# 1. Zip the '打包' folder
pack_dir = "打包"
zip_path = "VideoTools.zip"

print(f"Checking if {pack_dir} exists...")
while not os.path.exists(pack_dir) or not os.path.exists(os.path.join(pack_dir, "VideoTools.exe")):
    time.sleep(5)
    
print("Zipping the application...")
if os.path.exists(zip_path):
    os.remove(zip_path)
shutil.make_archive("VideoTools", 'zip', pack_dir)
print(f"Created {zip_path} ({os.path.getsize(zip_path)/1024/1024:.2f} MB)")

# Wait for git push to finish (we can assume if the repo has code, it's good, but let's wait a bit)
print("Creating GitHub Release...")
headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json"
}

# Create release
release_payload = {
    "tag_name": "v1.0.0",
    "name": "VideoTools Release v1.0.0",
    "body": "Packaged Windows Executable for VideoTools. Download the zip, extract, and run VideoTools.exe.",
    "draft": False,
    "prerelease": False
}
resp = requests.post(f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases", headers=headers, json=release_payload)
if resp.status_code != 201:
    print(f"Failed to create release: {resp.status_code} {resp.text}")
    # try to get existing release
    rels = requests.get(f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases", headers=headers).json()
    if len(rels) > 0:
        release_id = rels[0]["id"]
        upload_url = rels[0]["upload_url"].split("{")[0]
        print(f"Using existing release {release_id}")
    else:
        sys.exit(1)
else:
    release_data = resp.json()
    release_id = release_data["id"]
    upload_url = release_data["upload_url"].split("{")[0]
    print(f"Release created with ID {release_id}")

# Upload asset
print("Uploading asset...")
headers_upload = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json",
    "Content-Type": "application/zip"
}

with open(zip_path, "rb") as f:
    upload_resp = requests.post(
        f"{upload_url}?name=VideoTools.zip",
        headers=headers_upload,
        data=f
    )

if upload_resp.status_code == 201:
    print("Asset uploaded successfully!")
else:
    print(f"Failed to upload asset: {upload_resp.status_code} {upload_resp.text}")
