# -*- coding: utf-8 -*-
import os
import subprocess
import requests
import sys

token = os.environ.get("GITHUB_TOKEN") or open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "github_token.txt"), encoding="utf-8-sig").read().strip()
repo_owner = "dedeyuyu"
repo_name = "VideoTools"

installer_path = "output_installer/VideoTools_v1.5.19_Setup.exe"
asset_name = os.path.basename(installer_path)

headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json"
}

# Create release
release_payload = {
    "tag_name": "v1.5.19",
    "name": "VideoTools Release v1.5.19",
    "body": "### v1.5.19 更新内容\n- **☁️ 谷歌云端下载支持文件夹链接**：支持直接粘贴 Google Drive 文件夹分享链接，自动解析并批量下载文件夹内的所有视频文件\n- **🔢 自定义命名自动加序号**：下载云盘文件夹时，自动按用户填写的自定义命名追加 `+01`、`+02`、`+03` 等序号进行区分（未填自定义命名时自动使用原文件名+序号）\n- **📊 文件夹子任务进度展示**：实时显示文件夹内第 X/N 个视频的下载进度与日志明细",
    "draft": False,
    "prerelease": False
}
print("Creating release...")
resp = requests.post(f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases", headers=headers, json=release_payload)
if resp.status_code != 201:
    print(f"Note: {resp.status_code} {resp.text}")
    rel = requests.get(f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/tags/{release_payload['tag_name']}", headers=headers).json()
    if "id" in rel:
        release_id = rel["id"]
        upload_url = rel["upload_url"].split("{")[0]
        print(f"Using existing release {release_id}")
        for a in rel.get("assets", []):
            if a.get("name") == asset_name or a.get("state") != "uploaded":
                requests.delete(f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/assets/{a['id']}", headers=headers)
    else:
        sys.exit(1)
else:
    release_data = resp.json()
    upload_url = release_data["upload_url"].split("{")[0]
    print("Release created.")

print(f"Uploading {installer_path}...")
cmd = [
    "curl.exe", "-sS", "--fail-with-body",
    "--retry", "3", "--retry-delay", "3",
    "-X", "POST",
    "-H", f"Authorization: token {token}",
    "-H", "Accept: application/vnd.github.v3+json",
    "-H", "Content-Type: application/octet-stream",
    "--data-binary", f"@{installer_path}",
    f"{upload_url}?name={asset_name}"
]
r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
if r.returncode == 0 and '"state":"uploaded"' in r.stdout.replace(" ", ""):
    print("Asset uploaded successfully!")
else:
    print(f"Failed to upload asset: {r.returncode} {r.stderr} {r.stdout[:300]}")
    sys.exit(1)
