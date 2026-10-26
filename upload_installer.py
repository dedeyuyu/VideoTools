# -*- coding: utf-8 -*-
import os
import requests
import sys

token = os.environ.get("GITHUB_TOKEN") or open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "github_token.txt"), encoding="utf-8").read().strip()
repo_owner = "dedeyuyu"
repo_name = "VideoTools"

installer_path = "output_installer/VideoTools_v1.5.16_Setup.exe"

headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json"
}

# Create release
release_payload = {
    "tag_name": "v1.5.16",
    "name": "VideoTools Release v1.5.16",
    "body": "### v1.5.16 更新内容\n- **合拍预览支持连续播放**：字幕卡片微调新增「▶ 播放 / ⏸ 暂停」，多路视频同步播放并实时叠加模板、卡片和水印；人物视频按倍速循环（仍为仅标记对齐，无需缓存），播放中可拖动时间轴跳转、边播边改卡片\n- **替换当前任务的视频**：「文案和微调」中可单独替换某组任务的主视频 / 人物视频1~4，文案、卡片、微调保留，时间线标记与素材列表同步更新，导出以替换后为准\n- **卡片预设管理面板**：搜索、多选批量删除、置顶/上移/下移/置底、拖拽排序、重命名、一键应用；内置预设也可删除并可恢复\n- **四列表格批量编辑**：标题文本 / 电话文本 / 标题预设 / 电话预设，每列支持清空与逐行粘贴，也支持从 Excel 直接粘贴多列；预设留空则不更改",
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
        f"{upload_url}?name=VideoTools_v1.5.16_Setup.exe",
        headers=headers_upload,
        data=f
    )

if upload_resp.status_code == 201:
    print("Asset uploaded successfully!")
else:
    print(f"Failed to upload asset: {upload_resp.status_code} {upload_resp.text}")

