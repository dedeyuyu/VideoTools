# -*- coding: utf-8 -*-
import os
import requests
import sys

token = os.environ.get("GITHUB_TOKEN") or open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "github_token.txt"), encoding="utf-8").read().strip()
repo_owner = "dedeyuyu"
repo_name = "VideoTools"

installer_path = "output_installer/VideoTools_v1.5.18_Setup.exe"

headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json"
}

# Create release
release_payload = {
    "tag_name": "v1.5.18",
    "name": "VideoTools Release v1.5.18",
    "body": "### v1.5.18 更新内容\n- **新增「🔄 视频批量转码」工具页**：支持批量拖入多个视频或文件夹，一键将视频转换为全软件通用的标准兼容格式（H.264 `yuv420p` + AAC + 恒定帧率 CFR + FastStart），解决在其他剪辑软件或平台中无法导入/无法导出的问题\n- **多种转码模式与硬件加速**：内置标准兼容修复、高清无损画质（CRF 15）、轻量压缩（CRF 24）、极速重封装四种模式，支持 GPU 硬件加速自动检测与 CPU 自动回退，支持无音轨视频自动补充静音轨\n- **原名保持输出**：自由选择导出目录，转码后文件自动保持原视频文件名命名",
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
        f"{upload_url}?name=VideoTools_v1.5.18_Setup.exe",
        headers=headers_upload,
        data=f
    )

if upload_resp.status_code == 201:
    print("Asset uploaded successfully!")
else:
    print(f"Failed to upload asset: {upload_resp.status_code} {upload_resp.text}")

