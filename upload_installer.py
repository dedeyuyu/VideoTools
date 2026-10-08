import os
import requests
import sys

token = "REMOVED_TOKEN"
repo_owner = "dedeyuyu"
repo_name = "VideoTools"

installer_path = "output_installer/VideoTools_v1.5.6_Setup.exe"

headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json"
}

# Create release
release_payload = {
    "tag_name": "v1.5.6",
    "name": "VideoTools Release v1.5.6",
    "body": "打包的独立安装包。其他人可以直接下载安装，无需配置 Python 环境即可直接运行本软件。",
    "draft": False,
    "prerelease": False
}
print("Creating release...")
resp = requests.post(f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases", headers=headers, json=release_payload)
if resp.status_code != 201:
    print(f"Failed: {resp.status_code} {resp.text}")
    rels = requests.get(f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases", headers=headers).json()
    if len(rels) > 0:
        release_id = rels[0]["id"]
        upload_url = rels[0]["upload_url"].split("{")[0]
        print(f"Using existing release {release_id}")
    else:
        sys.exit(1)
else:
    release_data = resp.json()
    upload_url = release_data["upload_url"].split("{")[0]
    print("Release created.")

print(f"Uploading {installer_path}...")
headers_upload = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json",
    "Content-Type": "application/octet-stream"
}

with open(installer_path, "rb") as f:
    upload_resp = requests.post(
        f"{upload_url}?name=VideoTools_v1.5.6_Setup.exe",
        headers=headers_upload,
        data=f
    )

if upload_resp.status_code == 201:
    print("Asset uploaded successfully!")
else:
    print(f"Failed to upload asset: {upload_resp.status_code} {upload_resp.text}")
