# 🎬 视频集成工具箱 (VideoTools)

一款基于 PyQt6 的中文桌面视频/图片处理工具箱，集成多种实用功能。

## ✨ 功能模块

| 模块 | 功能 |
|------|------|
| 🚀 视频合并与转场 | 多段视频合并、添加转场特效 |
| ✨ 图片合并成视频 | 将图片序列合成为视频 |
| 🎨 处理版权图片 | 人脸检测遮脸（马赛克/模糊等）+ 大头图裁剪，支持手动标记区域 |
| 🖼️ 图片批量裁剪 | 批量裁剪图片 |
| 🎞️ 多片段合成 | 多片段视频合成 |
| 📥 YouTube下载 | 使用 yt-dlp 下载 YouTube 视频 |
| 📸 链接截图 | 网页/链接自动截图 |
| ☁️ 云盘下载 | 云盘文件下载 |

## 🛠️ 环境要求

- Python 3.10 ~ 3.12
- Windows 10/11

## 📦 安装依赖

```bash
pip install -r requirements.txt
```

> **注意**：mediapipe 需要固定版本 `0.10.21`，其他版本可能与 Python 3.12 不兼容。

## 🚀 运行

```bash
python main/main.py
```

## 📋 额外组件（需单独安装）

以下组件需通过软件内「📦 下载必要组件」安装：

- **FFmpeg** — 视频处理核心，[ffmpeg.org](https://ffmpeg.org/download.html)

## 📁 项目结构

```
VideoTools/
├── main/               # 主入口 & 主窗口
│   └── main.py
├── UI/                 # 各功能模块 UI
│   ├── ui_copyright_processor.py
│   ├── ui_ffmpeg_downloader_mgr.py
│   └── ...
├── image_worker/       # 图片处理后端
│   └── copyright_worker.py
├── video_worker/       # 视频处理后端
├── requirements.txt
└── README.md
```

## 📄 许可证

MIT License
