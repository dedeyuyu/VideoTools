# -*- coding: utf-8 -*-
import os
import subprocess
import requests
import sys

token = os.environ.get("GITHUB_TOKEN") or open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "github_token.txt"), encoding="utf-8-sig").read().strip()
repo_owner = "dedeyuyu"
repo_name = "VideoTools"

installer_path = "output_installer/VideoTools_v1.5.20_Setup.exe"
asset_name = os.path.basename(installer_path)

headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json"
}

# Create release
release_payload = {
    "tag_name": "v1.5.20",
    "name": "VideoTools Release v1.5.20",
    "body": "### v1.5.20 更新内容\n- **🧩 自定义多板块视频模板生成器（最多支持 13 板块）**：新增「平行分屏 / 不平行与斜线 / 画中画 / 🛠️ 自定义生成版式」四大分类，内置六格、七格、九格、十格（上1+下九宫格）等模板；支持自由设置行数与每行格数、自由指定任意板块为主视频，第 1 步时间线自动显示对应数量的板块列表\n- **🧲 画布自由增删拆分方框 + 智能对齐辅助线**：支持自由添加方框、左右/上下拆分为2格、添加画中画小窗、删除方框；拖拽移动或缩放方框时提供青色智能对齐辅助线与自动吸附，支持一键对齐吸附铺满\n- **🅰 标题/卡片文字根据字数自动缩放字号**：支持设置自动缩放最大行数、最大字号上限与最小字号下限，根据文案字数自动缩放字号，使文字不超过指定行数且尽量铺满限定宽度（让末行字数更均匀，短文案不超过最大字号上限）\n- **🔄 合拍视频新增画面旋转**：支持在模板及逐任务微调中对任意板块视频进行 0° / 90° / 180° / 270° 旋转",
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
