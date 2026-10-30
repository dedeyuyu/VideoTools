# -*- coding: utf-8 -*-
import os
import requests
import sys

token = os.environ.get("GITHUB_TOKEN") or open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "github_token.txt"), encoding="utf-8").read().strip()
repo_owner = "dedeyuyu"
repo_name = "VideoTools"

installer_path = "output_installer/VideoTools_v1.5.17_Setup.exe"

headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json"
}

# Create release
release_payload = {
    "tag_name": "v1.5.17",
    "name": "VideoTools Release v1.5.17",
    "body": "### v1.5.17 更新内容\n- **多画幅比例支持（9:16 / 3:4 / 1:1 / 4:3 / 16:9）**：四个步骤页顶栏同步切换视频尺寸，720P / 1080P / 2K / 4K 导出分辨率随比例自动联动，所有分屏模板、斜线模板、卡片与水印自动自适应画幅并防露黑边\n- **斜线分屏排版**：新增 4 套斜线分屏内置模板（左低右高 / 左高右低 × 主上人下 / 人上主下），支持多边形斜向裁剪、画布直接拖拽斜线两端控制点与精确调整左/右端点高度\n- **笔刷裂纹文字与底条特效**：新增笔刷裂纹、折纸褶皱、复古斑驳纹理与 3 款笔刷双色内置预设\n- **预设管理与接缝分隔线升级**：新增板块接缝带色分隔线（可调颜色与宽度）、预设名称一键导出到 Excel、非模态预设管理窗口支持边切换任务边搜索应用，排版参数区支持滚动浏览",
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
        f"{upload_url}?name=VideoTools_v1.5.17_Setup.exe",
        headers=headers_upload,
        data=f
    )

if upload_resp.status_code == 201:
    print("Asset uploaded successfully!")
else:
    print(f"Failed to upload asset: {upload_resp.status_code} {upload_resp.text}")

