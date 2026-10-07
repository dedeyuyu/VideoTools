import requests
import json
import sys
import subprocess

token = "REMOVED_TOKEN"
repo_name = "VideoTools"

headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json"
}

# 1. Create the repository
print("Creating repository...")
resp = requests.post(
    "https://api.github.com/user/repos",
    headers=headers,
    json={"name": repo_name, "private": False, "description": "VideoTools Desktop Application"}
)
if resp.status_code in [201, 422]: # 422 usually means it already exists
    print("Repository created or already exists.")
else:
    print(f"Failed to create repo: {resp.status_code} {resp.text}")
    sys.exit(1)

# 2. Add remote and push
print("Adding remote and pushing...")
remote_url = f"https://oauth2:{token}@github.com/dedeyuyu/{repo_name}.git"

subprocess.run(["git", "remote", "remove", "dedeyuyu"], capture_output=True)
subprocess.run(["git", "remote", "add", "dedeyuyu", remote_url])
res = subprocess.run(["git", "push", "-u", "dedeyuyu", "main", "--force"])
if res.returncode != 0:
    # try master
    res = subprocess.run(["git", "push", "-u", "dedeyuyu", "master", "--force"])
    
print("Push finished!")
